from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI

from jira_qa_agent.adf import adf_doc_from_sections, plain_text_from_adf
from jira_qa_agent.analyze import build_test_report, sections_from_markdown
from jira_qa_agent.bitbucket_pr import (
    PRRef,
    extract_pr_refs_from_remote_links,
    extract_pr_refs_from_text,
    fetch_pr_diff_cloud,
    fetch_pr_diff_dc,
    parse_pr_ref,
)
from jira_qa_agent.config import Settings, load_settings
from jira_qa_agent.jira_client import JiraClient

_DIVIDER = "=" * 70


def _load_dotenv() -> None:
    here = Path(__file__).resolve()
    candidates = [
        here.parents[1] / "docs/superpowers/specs/.env",
        Path.cwd() / "docs/superpowers/specs/.env",
        Path.cwd() / ".env",
    ]
    for p in candidates:
        if p.is_file():
            load_dotenv(p, override=True)
            return
    load_dotenv(override=True)


def _fetch_bb_diff(settings: Settings, ref: PRRef) -> str:
    auth_kw = dict(
        username=settings.bitbucket_username,
        password=settings.bitbucket_app_password,
        bearer_token=settings.bitbucket_access_token,
    )
    if ref.kind == "dc":
        base = ref.dc_base_url
        if not base:
            raise SystemExit(
                "Bitbucket DC PR missing server URL; set BITBUCKET_SERVER_URL or use a full stash URL."
            )
        return fetch_pr_diff_dc(
            base,
            ref.project_or_workspace,
            ref.repo_slug,
            ref.pr_id,
            settings.max_diff_chars,
            **auth_kw,
        )
    return fetch_pr_diff_cloud(
        ref.project_or_workspace,
        ref.repo_slug,
        ref.pr_id,
        settings.max_diff_chars,
        **auth_kw,
    )


def _pick_prs(refs: list[PRRef]) -> list[PRRef]:
    """Print a numbered menu and return the user's chosen PRRefs.

    Supports single selection (1), comma-separated (1,3), or 'all'.
    """
    print(f"\nFound {len(refs)} PRs linked to this ticket:")
    for i, r in enumerate(refs, 1):
        base = f"  ({r.dc_base_url})" if r.kind == "dc" else "  (bitbucket.org)"
        print(f"  [{i}]  {r.kind}  {r.project_or_workspace} / {r.repo_slug}  #{r.pr_id}{base}")
    print()
    while True:
        try:
            raw = input(
                f"Select PR(s) to analyse — single number, comma-separated (e.g. 1,3), "
                f"or 'all' [1-{len(refs)}, default 1]: "
            ).strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(0)
        if raw == "":
            return [refs[0]]
        if raw.lower() in ("all", "a"):
            return list(refs)
        parts = [p.strip() for p in raw.split(",")]
        chosen: list[PRRef] = []
        valid = True
        for p in parts:
            if p.isdigit() and 1 <= int(p) <= len(refs):
                r = refs[int(p) - 1]
                if r not in chosen:
                    chosen.append(r)
            else:
                print(f"  '{p}' is not valid — enter numbers between 1 and {len(refs)}.")
                valid = False
                break
        if valid and chosen:
            return chosen


# Keep old name as alias so existing callers that import _pick_pr still work
def _pick_pr(refs: list[PRRef]) -> PRRef:
    """Single-selection wrapper kept for backward compatibility with tests."""
    return _pick_prs(refs)[0]


def _discover_pr_ref(
    pr_arg: str | None,
    blob: str,
    jc: JiraClient,
    issue_key: str,
    issue_id: str,
    settings: Settings,
) -> list[PRRef]:
    """
    Three-stage PR discovery:
      1. --pr flag (manual, highest priority)
      2. Jira dev-status API (the Development panel) + remote links API
      3. Regex scan of ticket text (description + comments)
    Returns a list of PRRefs (prompts user to pick when multiple found).
    Exits with a clear message if nothing is found.
    """
    server_url = settings.bitbucket_server_base_url

    # Stage 1: manual override
    if pr_arg:
        ref = parse_pr_ref(pr_arg, server_base_url=server_url)
        if ref is None:
            raise SystemExit(
                f"Could not parse --pr value: {pr_arg!r}\n"
                "Expected formats: PROJECT/repo#123 (DC), workspace/repo#123 (Cloud), or a full pull-request URL."
            )
        return [ref]

    # Stage 2: Jira dev-status API (Development panel) + remote links
    print(f"Looking for linked PRs on {issue_key} via Jira Development panel...")
    dev_urls = jc.get_dev_status_prs(issue_id)
    refs = [r for u in dev_urls for r in [parse_pr_ref(u, server_base_url=server_url)] if r]

    if not refs:
        links = jc.get_remote_links(issue_key)
        refs = extract_pr_refs_from_remote_links(links, server_base_url=server_url)

    # Stage 3: text scan fallback
    if not refs:
        print("No linked PRs found — scanning ticket text for PR references...")
        refs = extract_pr_refs_from_text(blob, server_base_url=server_url)

    if not refs:
        raise SystemExit(
            f"No Bitbucket PR found on {issue_key}.\n"
            "Use --pr PROJECT/repo#123 (DC) or workspace/repo#123 (Cloud) to specify one manually."
        )

    if len(refs) == 1:
        r = refs[0]
        loc = (
            f"{r.dc_base_url}/projects/{r.project_or_workspace}/repos/{r.repo_slug}/pull-requests/{r.pr_id}"
            if r.kind == "dc"
            else f"bitbucket.org/{r.project_or_workspace}/{r.repo_slug}#{r.pr_id}"
        )
        print(f"Auto-detected PR: {loc} — proceeding...")
        return [r]

    return _pick_prs(refs)


def _review_loop(
    issue_key: str,
    summary: str,
    bundle: str,
    llm: ChatOpenAI,
    issue_type: str,
    no_confirm: bool,
) -> str:
    """
    Generate the test report, print it, ask the user if it looks good.
    If the user provides feedback, regenerate with that feedback appended.
    Returns the final approved report markdown.
    """
    report_md = build_test_report(llm, bundle, issue_type=issue_type)

    while True:
        print()
        print(_DIVIDER)
        print(f"  GENERATED TEST REPORT — {issue_key}: {summary}")
        print(f"  Issue type: {issue_type or 'Unknown (using default prompt)'}")
        print(_DIVIDER)
        print(report_md)
        print(_DIVIDER)
        print()

        if no_confirm:
            return report_md

        print("Is this report good? Options:")
        print("  [y]  Yes — post this to Jira")
        print("  [n]  No  — discard, do not post")
        print("  [feedback text] — type your changes/requests and press Enter to regenerate")
        print()

        try:
            answer = input("Your answer: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(0)

        if answer.lower() in ("y", "yes"):
            return report_md

        if answer.lower() in ("n", "no", ""):
            print("Report discarded. Nothing posted to Jira.")
            sys.exit(0)

        # User gave feedback — regenerate with it
        print()
        print("Regenerating with your feedback...")
        feedback_bundle = (
            bundle
            + f"\n\n---\nUser feedback on previous report (please revise accordingly):\n{answer}\n"
            + f"\nPrevious report (revise this):\n{report_md}\n"
        )
        report_md = build_test_report(llm, feedback_bundle, issue_type=issue_type)


def main(argv: list[str] | None = None) -> None:
    _load_dotenv()
    p = argparse.ArgumentParser(
        description=(
            "Jira ticket + Bitbucket PR diff → LLM test cases → "
            "interactive review → Jira comment"
        )
    )
    p.add_argument("issue_key", help="e.g. PROJ-123")
    p.add_argument(
        "--pr",
        help=(
            "PR ref: Cloud workspace/repo#123; DC PROJECT/repo#123 if BITBUCKET_SERVER_URL is set; "
            "or full URL (bitbucket.org or stash .../projects/.../pull-requests/n)"
        ),
    )
    p.add_argument(
        "--yes",
        action="store_true",
        help="Skip interactive review and post directly to Jira without asking",
    )
    args = p.parse_args(argv)

    settings = load_settings()
    jc = JiraClient(settings.jira_host, settings.jira_email, settings.jira_token)

    print(f"Fetching Jira ticket {args.issue_key}...")
    issue = jc.get_issue(args.issue_key)
    fields = issue.get("fields") or {}
    summary = str(fields.get("summary") or "")
    issue_type = str((fields.get("issuetype") or {}).get("name") or "")
    desc = fields.get("description")
    desc_text = plain_text_from_adf(desc) if isinstance(desc, dict) else str(desc or "")

    comments = jc.get_comments(args.issue_key)
    comment_lines: list[str] = []
    for cm in comments:
        body = cm.get("body") or {}
        author = (cm.get("author") or {}).get("displayName", "?")
        comment_lines.append(f"{author}: {plain_text_from_adf(body)}")

    blob_parts = [summary, desc_text, *comment_lines]
    if args.pr:
        blob_parts.append(args.pr)
    blob = "\n".join(blob_parts)

    selected_refs = _discover_pr_ref(args.pr, blob, jc, args.issue_key, issue["id"], settings)

    pr_sections: list[str] = []
    pr_labels: list[str] = []
    for ref in selected_refs:
        loc = (
            f"{ref.dc_base_url}/projects/{ref.project_or_workspace}"
            f"/repos/{ref.repo_slug}/pull-requests/{ref.pr_id}"
            if ref.kind == "dc"
            else f"{ref.project_or_workspace}/{ref.repo_slug}#{ref.pr_id} (Cloud)"
        )
        print(f"Fetching PR diff from Bitbucket ({ref.kind}): {loc} ...")
        diff = _fetch_bb_diff(settings, ref)
        print(f"  Diff fetched ({len(diff):,} chars).")
        pr_sections.append(f"Bitbucket PR ({ref.kind}) {loc}\nDiff:\n{diff}")
        pr_labels.append(loc)

    print("Running LLM analysis...")

    bundle = f"""JIRA {args.issue_key}
Summary: {summary}

Description:
{desc_text}

Comments:
{chr(10).join(comment_lines)}

{chr(10).join(pr_sections)}
"""

    llm = ChatOpenAI(model=settings.openai_model, temperature=0)
    report_md = _review_loop(args.issue_key, summary, bundle, llm, issue_type, no_confirm=args.yes)

    # Build ADF and post
    sections = sections_from_markdown(report_md)
    pr_list = ", ".join(pr_labels)
    preamble = (
        "Automation note",
        f"Generated from {len(selected_refs)} Bitbucket PR(s) via jira_qa_agent: {pr_list}",
    )
    adf = adf_doc_from_sections([preamble, *sections])
    jc.add_comment(args.issue_key, adf)
    print(f"\nPosted test plan comment on {args.issue_key}.")
