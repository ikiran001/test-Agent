from __future__ import annotations

import re
from typing import Literal, NamedTuple

import httpx

# --- Bitbucket Cloud (bitbucket.org) ---
_BB_CLOUD_REF = re.compile(
    r"(?:https?://)?(?:www\.)?bitbucket\.org/(?P<ws>[\w.-]+)/(?P<repo>[\w.-]+)(?:/pull-requests/|#)(?P<num>\d+)",
    re.I,
)

# --- Bitbucket Data Center / Server (e.g. stash.company.com) ---
_BB_DC_REF = re.compile(
    r"(?P<base>https?://[\w.-]+)/projects/(?P<proj>[\w.-]+)/repos/(?P<repo>[\w.-]+)/pull-requests/(?P<num>\d+)",
    re.I,
)

# Short form: projectOrWorkspace/repo-slug#42 (meaning depends on BITBUCKET_SERVER_URL — see parse_pr_ref)
_BB_SHORT = re.compile(
    r"(?<![\w/])(?P<ws>[\w.-]+)/(?P<repo>[\w.-]+)#(?P<num>\d+)\b",
    re.I,
)


class PRRef(NamedTuple):
    """Resolved PR location for Cloud or Bitbucket Server/Data Center."""

    kind: Literal["cloud", "dc"]
    project_or_workspace: str
    repo_slug: str
    pr_id: int
    # DC only: base URL like https://stash.example.com (no trailing slash). Cloud ignores.
    dc_base_url: str | None


def parse_pr_ref(text: str, *, server_base_url: str | None = None) -> PRRef | None:
    """
    Resolve PR reference from ticket text or --pr.

    - Full DC URL: https://stash.example.com/projects/PROJ/repos/my-repo/pull-requests/123
    - Full Cloud URL: https://bitbucket.org/workspace/repo/pull-requests/123
    - Short form KEY/repo#num: if BITBUCKET_SERVER_URL is set → DC project/repo; else Cloud workspace/repo.
    """
    base_from_env = (server_base_url or "").strip().rstrip("/") or None

    m = _BB_DC_REF.search(text)
    if m:
        return PRRef(
            kind="dc",
            project_or_workspace=m.group("proj"),
            repo_slug=m.group("repo"),
            pr_id=int(m.group("num")),
            dc_base_url=m.group("base").rstrip("/"),
        )

    m = _BB_CLOUD_REF.search(text)
    if m:
        return PRRef(
            kind="cloud",
            project_or_workspace=m.group("ws"),
            repo_slug=m.group("repo"),
            pr_id=int(m.group("num")),
            dc_base_url=None,
        )

    m = _BB_SHORT.search(text)
    if not m:
        return None

    ws, repo, num = m.group("ws"), m.group("repo"), int(m.group("num"))
    if base_from_env:
        return PRRef(
            kind="dc",
            project_or_workspace=ws,
            repo_slug=repo,
            pr_id=num,
            dc_base_url=base_from_env,
        )
    return PRRef(
        kind="cloud",
        project_or_workspace=ws,
        repo_slug=repo,
        pr_id=num,
        dc_base_url=None,
    )


def _dedup(refs: list[PRRef]) -> list[PRRef]:
    """Remove duplicate PRRefs keeping first occurrence, keyed on (project, repo, pr_id)."""
    seen: set[tuple[str, str, int]] = set()
    out: list[PRRef] = []
    for r in refs:
        key = (r.project_or_workspace, r.repo_slug, r.pr_id)
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def extract_pr_refs_from_text(
    text: str,
    *,
    server_base_url: str | None = None,
) -> list[PRRef]:
    """
    Scan free-form text for all Bitbucket PR references and return deduplicated PRRef list.
    Tries DC full URL, Cloud full URL, and short-form PROJECT/repo#N patterns.
    """
    refs: list[PRRef] = []
    for m in _BB_DC_REF.finditer(text):
        refs.append(
            PRRef(
                kind="dc",
                project_or_workspace=m.group("proj"),
                repo_slug=m.group("repo"),
                pr_id=int(m.group("num")),
                dc_base_url=m.group("base").rstrip("/"),
            )
        )
    for m in _BB_CLOUD_REF.finditer(text):
        refs.append(
            PRRef(
                kind="cloud",
                project_or_workspace=m.group("ws"),
                repo_slug=m.group("repo"),
                pr_id=int(m.group("num")),
                dc_base_url=None,
            )
        )
    base = (server_base_url or "").strip().rstrip("/") or None
    for m in _BB_SHORT.finditer(text):
        ws, repo, num = m.group("ws"), m.group("repo"), int(m.group("num"))
        refs.append(
            PRRef(
                kind="dc" if base else "cloud",
                project_or_workspace=ws,
                repo_slug=repo,
                pr_id=num,
                dc_base_url=base,
            )
        )
    return _dedup(refs)


def extract_pr_refs_from_remote_links(
    links: list[dict],
    *,
    server_base_url: str | None = None,
) -> list[PRRef]:
    """
    Given the raw list from the Jira remote-links API, return deduplicated PRRef objects
    for any Bitbucket PR URLs found. Non-Bitbucket links and non-PR Bitbucket URLs are
    skipped silently.
    """
    refs: list[PRRef] = []
    for link in links:
        url = (link.get("object") or {}).get("url") or ""
        if not url:
            continue
        if "bitbucket" not in url.lower() and "stash" not in url.lower():
            continue
        ref = parse_pr_ref(url, server_base_url=server_base_url)
        if ref is not None:
            refs.append(ref)
    return _dedup(refs)


def _bb_http_client(
    *,
    username: str | None,
    password: str | None,
    bearer_token: str | None,
) -> dict:
    headers: dict[str, str] = {}
    if bearer_token:
        headers["Authorization"] = f"Bearer {bearer_token}"
    kw: dict = {"timeout": 120.0, "headers": headers}
    if username is not None and password is not None and not bearer_token:
        kw["auth"] = (username, password)
    return kw


def fetch_pr_diff_cloud(
    workspace: str,
    repo_slug: str,
    pr_id: int,
    max_chars: int,
    *,
    username: str | None = None,
    password: str | None = None,
    bearer_token: str | None = None,
) -> str:
    """Bitbucket Cloud: GET api.bitbucket.org/.../pullrequests/{id}/diff"""
    url = (
        f"https://api.bitbucket.org/2.0/repositories/{workspace}/{repo_slug}"
        f"/pullrequests/{pr_id}/diff"
    )
    with httpx.Client(**_bb_http_client(username=username, password=password, bearer_token=bearer_token)) as c:
        r = c.get(url)
        r.raise_for_status()
        diff = r.text
    return _truncate(diff, max_chars)


def fetch_pr_diff_dc(
    base_url: str,
    project_key: str,
    repo_slug: str,
    pr_id: int,
    max_chars: int,
    *,
    username: str | None = None,
    password: str | None = None,
    bearer_token: str | None = None,
) -> str:
    """
    Bitbucket Data Center / Server: unified diff text.

    GET /rest/api/latest/projects/{projectKey}/repos/{repositorySlug}/pull-requests/{id}/diff
    Note: /patch returns 404 on many Stash versions; /diff is reliable.
    """
    root = base_url.rstrip("/")
    url = (
        f"{root}/rest/api/latest/projects/{project_key}/repos/{repo_slug}"
        f"/pull-requests/{pr_id}/diff"
    )
    kw = _bb_http_client(username=username, password=password, bearer_token=bearer_token)
    headers = dict(kw.get("headers") or {})
    headers.setdefault("Accept", "text/plain,*/*;q=0.8")
    kw["headers"] = headers
    with httpx.Client(**kw) as c:
        r = c.get(url)
        r.raise_for_status()
        diff = r.text
    return _truncate(diff, max_chars)


def _truncate(diff: str, max_chars: int) -> str:
    if len(diff) > max_chars:
        return diff[:max_chars] + "\n\n[diff truncated]\n"
    return diff


def fetch_pr_diff(
    workspace: str,
    repo_slug: str,
    pr_id: int,
    max_chars: int,
    *,
    username: str | None = None,
    password: str | None = None,
    bearer_token: str | None = None,
) -> str:
    """Backward-compatible alias: Cloud only."""
    return fetch_pr_diff_cloud(
        workspace,
        repo_slug,
        pr_id,
        max_chars,
        username=username,
        password=password,
        bearer_token=bearer_token,
    )
