# Jira Ticket QA Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend this repo’s Python agent setup so a workflow can (1) authenticate to Jira with your API token, (2) load a ticket’s description and comments, (3) resolve and fetch the linked PR code diff (GitHub first), (4) use an LLM to derive structured manual/automation-oriented test cases from ticket context + diff, and (5) post the test-case report as a new Jira comment.

**Architecture:** Keep browser automation (`mcp_use_basic_part_1.py` + Playwright MCP) separate from this workflow. Add a **CLI-driven pipeline** (`scripts/jira_qa_agent/`) that uses HTTP APIs (Jira REST v3, GitHub REST) plus **LangChain `ChatOpenAI`** for analysis—same LLM pattern as the existing script. Jira comment posting uses Atlassian Document Format (ADF) via REST v3 for Cloud compatibility. Git integration starts with **GitHub** (token + owner/repo/PR from issue links or CLI overrides); add an abstraction so GitLab can be plugged in later without rewriting Jira/LLM pieces.

**Tech Stack:** Python 3.11+, `httpx` (async-capable sync client), `python-dotenv`, `langchain-openai`, optional `jira` package OR raw REST with ADF helpers; GitHub REST `pulls` + `pulls/{sha}` diff endpoint.

**Mini-spec (requirements baked into this plan):**

| Requirement | Decision |
|-------------|----------|
| Auth | Jira: email + API token (Cloud) or PAT + user email per Atlassian docs |
| Ticket scope | Single issue key per run (`PROJ-123`) |
| PR source | Priority 1: explicit `--github-pr owner/repo#123`; Priority 2: parse ticket description/comments for `owner/repo#number` or GitHub URLs; Priority 3: optional future Jira Development Information API |
| Output | Markdown-ish sections posted as ADF paragraph/list nodes in Jira |
| Safety | No secrets in prompts beyond what’s needed; truncate huge diffs with configurable max chars |

---

## File map

| Path | Responsibility |
|------|----------------|
| `jira_qa_agent/__init__.py` | Package marker (repository root package—set `PYTHONPATH=.` or editable install) |
| `jira_qa_agent/config.py` | Env vars: `JIRA_HOST`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `GITHUB_TOKEN`, `OPENAI_*`, limits |
| `jira_qa_agent/jira_client.py` | Fetch issue fields, comments; post ADF comment |
| `jira_qa_agent/adf.py` | Build Atlassian Document Format JSON from plain sections |
| `jira_qa_agent/github_pr.py` | Fetch PR metadata + patch/diff text |
| `jira_qa_agent/analyze.py` | LangChain prompt → structured test case document |
| `jira_qa_agent/cli.py` | argparse: issue key, optional `--pr`, `--dry-run` |
| `jira_qa_agent/__main__.py` | `python -m jira_qa_agent` entry |
| `docs/superpowers/specs/.env.example` | Document new variables |
| `docs/superpowers/specs/requirements.txt` | Add `httpx`, versions pinned loosely |

**Optional later:** `jira_qa_agent/git_integration/gitlab.py` — not in initial scope.

---

### Task 1: Dependencies and environment template

**Files:**
- Modify: `docs/superpowers/specs/requirements.txt`
- Modify: `docs/superpowers/specs/.env.example`

- [ ] **Step 1: Append runtime deps**

Add lines:

```
httpx>=0.27.0
```

(`langchain-openai`, `python-dotenv` already present.)

- [ ] **Step 2: Extend `.env.example` with Jira/Git placeholders**

Append (comments explain Cloud classic auth):

```
# Jira Cloud — API token from id.atlassian.com; use account email as username
JIRA_HOST=https://your-domain.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=

# GitHub — classic PAT with repo scope for private repos
GITHUB_TOKEN=

# Optional: OpenAI (reuse existing OPENAI_MODEL / OPENAI_API_KEY)
JIRA_QA_MAX_DIFF_CHARS=120000
```

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/requirements.txt docs/superpowers/specs/.env.example
git commit -m "chore: add jira_qa_agent httpx and env template"
```

---

### Task 2: Config module

**Files:**
- Create: `jira_qa_agent/config.py`
- Create: `jira_qa_agent/__init__.py` (empty)

- [ ] **Step 1: Create `config.py`**

```python
import os
from dataclasses import dataclass

@dataclass(frozen=True)
class Settings:
    jira_host: str
    jira_email: str
    jira_token: str
    github_token: str
    openai_model: str
    max_diff_chars: int

def load_settings() -> Settings:
    host = (os.environ.get("JIRA_HOST") or "").rstrip("/")
    if not host:
        raise SystemExit("JIRA_HOST is required")
    return Settings(
        jira_host=host,
        jira_email=(os.environ.get("JIRA_EMAIL") or "").strip() or _exit("JIRA_EMAIL"),
        jira_token=(os.environ.get("JIRA_API_TOKEN") or "").strip() or _exit("JIRA_API_TOKEN"),
        github_token=(os.environ.get("GITHUB_TOKEN") or "").strip() or _exit("GITHUB_TOKEN"),
        openai_model=(os.environ.get("OPENAI_MODEL") or "gpt-4.1").strip(),
        max_diff_chars=int(os.environ.get("JIRA_QA_MAX_DIFF_CHARS", "120000")),
    )

def _exit(name: str) -> str:
    raise SystemExit(f"{name} is required")
```

- [ ] **Step 2: Commit**

```bash
git add jira_qa_agent/config.py jira_qa_agent/__init__.py
git commit -m "feat(jira_qa): add settings loader"
```

---

### Task 3: ADF builder for Jira Cloud comments

**Files:**
- Create: `jira_qa_agent/adf.py`

- [ ] **Step 1: Implement minimal ADF document**

Jira REST v3 expects `body` as ADF. Provide builders for heading + paragraph + bullet list.

```python
from __future__ import annotations

def adf_doc_from_sections(sections: list[tuple[str, str]]) -> dict:
    """sections: (heading_text, body_paragraphs_markdownish_plain_text)"""
    content: list = []
    for title, body in sections:
        content.append({
            "type": "heading",
            "attrs": {"level": 2},
            "content": [{"type": "text", "text": title}],
        })
        for line in body.strip().splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("- "):
                content.append({
                    "type": "bulletList",
                    "content": [{
                        "type": "listItem",
                        "content": [{
                            "type": "paragraph",
                            "content": [{"type": "text", "text": line[2:]}],
                        }],
                    }],
                })
            else:
                content.append({
                    "type": "paragraph",
                    "content": [{"type": "text", "text": line}],
                })
    return {"type": "doc", "version": 1, "content": content}
```

- [ ] **Step 2: Commit**

```bash
git add jira_qa_agent/adf.py
git commit -m "feat(jira_qa): Atlassian ADF helper for comments"
```

---

### Task 4: Jira client — fetch issue and post comment

**Files:**
- Create: `jira_qa_agent/jira_client.py`

- [ ] **Step 1: Implement client**

Use `httpx` with Basic auth: email + API token (Jira Cloud).

```python
from __future__ import annotations

import httpx

class JiraClient:
    def __init__(self, host: str, email: str, api_token: str) -> None:
        self._base = f"{host.rstrip('/')}/rest/api/3"
        self._auth = (email, api_token)

    def get_issue(self, key: str) -> dict:
        with httpx.Client(auth=self._auth, timeout=60.0) as c:
            r = c.get(f"{self._base}/issue/{key}", params={"expand": "renderedFields"})
            r.raise_for_status()
            return r.json()

    def get_comments(self, key: str) -> list[dict]:
        with httpx.Client(auth=self._auth, timeout=60.0) as c:
            r = c.get(f"{self._base}/issue/{key}/comment")
            r.raise_for_status()
            return r.json().get("comments", [])

    def add_comment(self, key: str, adf_body: dict) -> dict:
        payload = {"body": adf_body}
        with httpx.Client(auth=self._auth, timeout=60.0) as c:
            r = c.post(f"{self._base}/issue/{key}/comment", json=payload)
            r.raise_for_status()
            return r.json()
```

- [ ] **Step 2: Helper to flatten description**

Extract `fields.summary`, `fields.description` (ADF—optional walker later), `fields.description` string fallback: for Phase 1, pass raw JSON summary + stringify description content via simple extraction or use `renderedFields` if expand worked.

**Note:** If `description` is ADF, add a tiny recursive text extractor in `adf.py` (`plain_text_from_adf(adf: dict) -> str`) for the LLM context—implement in same task.

```python
def plain_text_from_adf(node: dict | list | str | None) -> str:
    if node is None:
        return ""
    if isinstance(node, str):
        return node
    if isinstance(node, list):
        return "\n".join(plain_text_from_adf(x) for x in node)
    if isinstance(node, dict):
        if node.get("text"):
            return str(node["text"])
        parts = []
        for child in node.get("content") or []:
            parts.append(plain_text_from_adf(child))
        return "\n".join(parts)
    return ""
```

- [ ] **Step 3: Commit**

```bash
git add jira_qa_agent/jira_client.py jira_qa_agent/adf.py
git commit -m "feat(jira_qa): Jira REST client and ADF text extraction"
```

---

### Task 5: GitHub PR diff fetcher

**Files:**
- Create: `jira_qa_agent/github_pr.py`

- [ ] **Step 1: Parse `owner/repo#123` or full GitHub URL**

```python
from __future__ import annotations

import re
import httpx

_PR_REF = re.compile(
    r"(?:https?://github\.com/)?(?P<owner>[\w.-]+)/(?P<repo>[\w.-]+)(?:#|/pull/)(?P<num>\d+)",
    re.I,
)

def parse_pr_ref(text: str) -> tuple[str, str, int] | None:
    m = _PR_REF.search(text)
    if not m:
        return None
    return m.group("owner"), m.group("repo"), int(m.group("num"))

def fetch_pr_diff(token: str, owner: str, repo: str, number: int, max_chars: int) -> str:
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github.diff",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"
    with httpx.Client(timeout=120.0) as c:
        r = c.get(url, headers=headers)
        r.raise_for_status()
        diff = r.text
    if len(diff) > max_chars:
        return diff[:max_chars] + "\n\n[diff truncated]\n"
    return diff
```

- [ ] **Step 2: Commit**

```bash
git add jira_qa_agent/github_pr.py
git commit -m "feat(jira_qa): GitHub PR diff fetch"
```

---

### Task 6: LLM analysis — test case report

**Files:**
- Create: `jira_qa_agent/analyze.py`

- [ ] **Step 1: Build prompt and call ChatOpenAI**

Input bundle: ticket summary, description text, concatenated comment bodies (author + created), PR diff.

Output: structured sections string matching what `adf_doc_from_sections` expects.

```python
from __future__ import annotations

from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

SYSTEM = """You are a senior QA engineer. Given a Jira ticket and a pull request diff, propose \
test cases that validate the change and regression risks. Output plain text in exactly these sections \
(use the headings as lines starting with ## so the parser can split):

## Summary
## Preconditions / data
## Automated test ideas (API/UI as applicable)
## Manual exploratory scenarios
## Edge cases & negatives
## Risks / unknowns

Be specific; reference files or symbols from the diff when relevant. If diff is missing or empty, \
infer only from ticket text and state assumptions explicitly."""

def build_test_report(llm: ChatOpenAI, bundle: str) -> str:
    resp = llm.invoke([
        SystemMessage(content=SYSTEM),
        HumanMessage(content=bundle),
    ])
    return resp.content if isinstance(resp.content, str) else str(resp.content)
```

- [ ] **Step 2: Split LLM output into ADF sections**

Post-process: split on `## ` lines into `(title, body)` tuples for `adf_doc_from_sections`.

```python
def sections_from_markdown(headed_text: str) -> list[tuple[str, str]]:
    blocks = headed_text.split("\n## ")
    out: list[tuple[str, str]] = []
    for i, block in enumerate(blocks):
        block = block.strip()
        if not block:
            continue
        if i == 0 and not block.startswith("##"):
            title, _, body = block.partition("\n")
            title = title.replace("##", "").strip()
        else:
            title, _, body = block.partition("\n")
            title = title.strip()
        out.append((title, body))
    return out
```

Refine edge cases for first block without `##` — engineer should add unit test.

- [ ] **Step 3: Commit**

```bash
git add jira_qa_agent/analyze.py
git commit -m "feat(jira_qa): LLM test-case report generator"
```

---

### Task 7: CLI wiring

**Files:**
- Create: `jira_qa_agent/cli.py`
- Create: `jira_qa_agent/__main__.py`

- [ ] **Step 1: Implement `cli.py`**

```python
from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from jira_qa_agent.config import load_settings
from jira_qa_agent.jira_client import JiraClient
from jira_qa_agent.adf import adf_doc_from_sections, plain_text_from_adf
from jira_qa_agent.github_pr import parse_pr_ref, fetch_pr_diff
from jira_qa_agent.analyze import build_test_report, sections_from_markdown
from langchain_openai import ChatOpenAI

def main(argv: list[str] | None = None) -> None:
    # Repo root = parent of package dir `jira_qa_agent/`
    load_dotenv(Path(__file__).resolve().parents[1] / "docs/superpowers/specs/.env")
    p = argparse.ArgumentParser(description="Jira ticket → PR diff → test cases → Jira comment")
    p.add_argument("issue_key", help="e.g. PROJ-123")
    p.add_argument("--pr", help="owner/repo#123 or GitHub PR URL")
    p.add_argument("--dry-run", action="store_true", help="Print report only; do not post")
    args = p.parse_args(argv)

    settings = load_settings()
    jc = JiraClient(settings.jira_host, settings.jira_email, settings.jira_token)
    issue = jc.get_issue(args.issue_key)
    fields = issue.get("fields") or {}
    summary = fields.get("summary") or ""
    desc = fields.get("description")
    desc_text = plain_text_from_adf(desc) if isinstance(desc, dict) else str(desc or "")

    comments = jc.get_comments(args.issue_key)
    comment_lines = []
    for cm in comments:
        body = cm.get("body") or {}
        author = (cm.get("author") or {}).get("displayName", "?")
        comment_lines.append(f"{author}: {plain_text_from_adf(body)}")

    pr_ref = args.pr
    if not pr_ref:
        blob = "\n".join([summary, desc_text, *comment_lines])
        parsed = parse_pr_ref(blob)
        if not parsed:
            raise SystemExit("Could not find GitHub PR reference; pass --pr owner/repo#123")
        owner, repo, num = parsed
    else:
        parsed = parse_pr_ref(args.pr)
        if not parsed:
            raise SystemExit("Invalid --pr format; use owner/repo#123")
        owner, repo, num = parsed

    diff = fetch_pr_diff(settings.github_token, owner, repo, num, settings.max_diff_chars)

    bundle = f"""JIRA {args.issue_key}
Summary: {summary}

Description:
{desc_text}

Comments:
{chr(10).join(comment_lines)}

PR {owner}/{repo}#{num} diff:
{diff}
"""

    llm = ChatOpenAI(model=settings.openai_model, temperature=0)
    report_md = build_test_report(llm, bundle)
    sections = sections_from_markdown(report_md)
    preamble = ("Automation note", f"Generated from PR {owner}/{repo}#{num} via jira_qa_agent.")
    adf = adf_doc_from_sections([preamble, *sections])

    if args.dry_run:
        print(report_md)
        return

    jc.add_comment(args.issue_key, adf)
    print(f"Posted test plan comment on {args.issue_key}")

if __name__ == "__main__":
    main()
```

Run from repository root with `PYTHONPATH=.` (documented in Task 8).

- [ ] **Step 2: `__main__.py`**

```python
from jira_qa_agent.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Commit**

```bash
git add jira_qa_agent/
git commit -m "feat(jira_qa): CLI to analyze ticket and post comment"
```

---

### Task 8: Manual verification runbook

**Files:**
- Create: `docs/superpowers/specs/jira_qa_agent-readme.txt` (short runbook)

- [ ] **Step 1: Document commands**

```
PYTHONPATH=. python -m jira_qa_agent PROJ-123 --dry-run
PYTHONPATH=. python -m jira_qa_agent PROJ-123 --pr myorg/repo#45
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/jira_qa_agent-readme.txt
git commit -m "docs: jira_qa_agent runbook"
```

---

### Task 9: Optional bridge — env flag on existing Playwright agent

**Files:**
- Modify: `docs/superpowers/specs/mcp_use_basic_part_1.py`

**Only if product owner wants one entrypoint:**

- [ ] **Step 1:** Add `USE_JIRA_QA=1` branch at start of `main()` that subprocesses `python -m jira_qa_agent` with `JIRA_ISSUE_KEY` from env and exits—keeps concerns separated.

```python
if os.environ.get("USE_JIRA_QA", "").strip() == "1":
    import sys
    key = os.environ.get("JIRA_ISSUE_KEY", "").strip()
    if not key:
        raise SystemExit("USE_JIRA_QA=1 requires JIRA_ISSUE_KEY")
    subprocess.run([sys.executable, "-m", "jira_qa_agent", key], check=True)
    return
```

Place `jira_qa_agent` on PYTHONPATH via installing editable package or document wrapper shell script instead—**YAGNI unless requested**.

---

## Spec coverage check

| Requirement | Task |
|-------------|------|
| Jira API token auth | Task 2–4 |
| Description + comments | Task 4 + 7 |
| PR diff | Task 5–7 |
| LLM test cases | Task 6 |
| Jira comment report | Task 3–4 + 7 |
| Not pure rule-based | Task 6 LLM |

**Gap:** Jira Server/Data Center uses PAT differently—document “Cloud only v1” in readme unless extended.

## Self-review (plan)

- Task 7 import/path issue explicitly corrected by relocating package to `jira_qa_agent/` at repo root.
- ADF bullet parsing is naive—acceptable for v1; engineer may refine.

---

## Brainstorming follow-through

A formal dated design doc (`docs/superpowers/specs/2026-05-08-jira-qa-agent-design.md`) was **not** created separately to save duplication; this plan’s **Mini-spec** + **Architecture** sections serve that role until you ask for a standalone design file.

---

**Plan complete and saved to** `docs/superpowers/plans/2026-05-08-jira-ticket-qa-agent.md`.

**Deprecation note:** The Cursor `/write-plan` command is deprecated; use the **writing-plans** skill (this workflow) for future plans.

**Execution options:**

1. **Subagent-driven (recommended)** — Dispatch a fresh subagent per task with review between tasks (`superpowers:subagent-driven-development`).

2. **Inline execution** — Run tasks in this session with checkpoints (`superpowers:executing-plans`).

**Which approach do you want?**

**One decision needed before coding:** Is **GitHub** the correct PR host for your team (vs GitLab / Bitbucket)? The plan assumes GitHub first; say if we should swap Task 5 for GitLab merge request API instead.
