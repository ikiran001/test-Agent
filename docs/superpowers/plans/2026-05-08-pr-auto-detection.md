# PR Auto-Detection Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `python -m jira_qa_agent SOFT-186005` work without a `--pr` flag by auto-detecting the linked Bitbucket PR from the Jira ticket.

**Architecture:** Three-stage discovery — (1) `--pr` flag manual override, (2) Jira remote links API, (3) regex scan of ticket description and comment text. A numbered picker is shown when multiple PRs are found. All new logic is isolated into two small helpers (`_discover_pr_ref` and `_pick_pr`) inside `cli.py`, plus one new method on `JiraClient` and two new module-level helpers in `bitbucket_pr.py`.

**Tech Stack:** Python 3.11+, httpx, existing regex patterns in `bitbucket_pr.py`, pytest

---

## File Map

| File | Change |
|------|--------|
| `jira_qa_agent/jira_client.py` | Add `get_remote_links()` method |
| `jira_qa_agent/bitbucket_pr.py` | Add `extract_pr_refs_from_remote_links()` and `extract_pr_refs_from_text()` |
| `jira_qa_agent/cli.py` | Add `_pick_pr()` and `_discover_pr_ref()`; update `main()` to call them |
| `tests/__init__.py` | Create (empty — marks tests as a package) |
| `tests/test_bitbucket_pr.py` | Unit tests for new helpers in `bitbucket_pr.py` |
| `tests/test_cli_discovery.py` | Unit tests for `_pick_pr` and `_discover_pr_ref` |

---

## Task 1: Test infrastructure setup

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/test_bitbucket_pr.py`

- [ ] **Step 1: Create the tests package**

```bash
mkdir -p tests && touch tests/__init__.py
```

- [ ] **Step 2: Install pytest**

```bash
pip install pytest
```

- [ ] **Step 3: Write failing tests for `extract_pr_refs_from_text`**

Create `tests/test_bitbucket_pr.py`:

```python
from __future__ import annotations

import pytest

from jira_qa_agent.bitbucket_pr import PRRef, extract_pr_refs_from_text


def test_extract_single_dc_url_from_text():
    text = "See https://stash.example.com/projects/NDP/repos/nd-mfe/pull-requests/42 for details"
    refs = extract_pr_refs_from_text(text)
    assert len(refs) == 1
    assert refs[0] == PRRef(
        kind="dc",
        project_or_workspace="NDP",
        repo_slug="nd-mfe",
        pr_id=42,
        dc_base_url="https://stash.example.com",
    )


def test_extract_single_cloud_url_from_text():
    text = "PR: https://bitbucket.org/myworkspace/my-repo/pull-requests/7"
    refs = extract_pr_refs_from_text(text)
    assert len(refs) == 1
    assert refs[0] == PRRef(
        kind="cloud",
        project_or_workspace="myworkspace",
        repo_slug="my-repo",
        pr_id=7,
        dc_base_url=None,
    )


def test_extract_short_ref_with_server_url():
    text = "Fix for NDP/nd-mfe#100"
    refs = extract_pr_refs_from_text(text, server_base_url="https://stash.example.com")
    assert len(refs) == 1
    assert refs[0] == PRRef(
        kind="dc",
        project_or_workspace="NDP",
        repo_slug="nd-mfe",
        pr_id=100,
        dc_base_url="https://stash.example.com",
    )


def test_extract_deduplicates_same_pr():
    text = (
        "See https://stash.example.com/projects/NDP/repos/nd-mfe/pull-requests/42 "
        "and also https://stash.example.com/projects/NDP/repos/nd-mfe/pull-requests/42"
    )
    refs = extract_pr_refs_from_text(text)
    assert len(refs) == 1


def test_extract_multiple_different_prs():
    text = (
        "https://stash.example.com/projects/NDP/repos/nd-mfe/pull-requests/1 "
        "https://stash.example.com/projects/NDP/repos/nd-mfe/pull-requests/2"
    )
    refs = extract_pr_refs_from_text(text)
    assert len(refs) == 2


def test_extract_returns_empty_for_no_match():
    text = "Nothing here"
    refs = extract_pr_refs_from_text(text)
    assert refs == []
```

- [ ] **Step 4: Write failing tests for `extract_pr_refs_from_remote_links`**

Append to `tests/test_bitbucket_pr.py`:

```python
from jira_qa_agent.bitbucket_pr import extract_pr_refs_from_remote_links


def test_remote_links_extracts_dc_pr_url():
    links = [
        {
            "object": {
                "url": "https://stash.example.com/projects/NDP/repos/nd-mfe/pull-requests/42",
                "title": "PR #42",
            }
        }
    ]
    refs = extract_pr_refs_from_remote_links(links)
    assert len(refs) == 1
    assert refs[0].pr_id == 42
    assert refs[0].kind == "dc"


def test_remote_links_skips_non_pr_urls():
    links = [
        {"object": {"url": "https://stash.example.com/projects/NDP/repos/nd-mfe/browse", "title": "Repo"}},
        {"object": {"url": "https://github.com/org/repo/pull/1", "title": "GitHub PR"}},
    ]
    refs = extract_pr_refs_from_remote_links(links)
    assert refs == []


def test_remote_links_deduplicates():
    link = {
        "object": {
            "url": "https://stash.example.com/projects/NDP/repos/nd-mfe/pull-requests/42",
            "title": "PR #42",
        }
    }
    refs = extract_pr_refs_from_remote_links([link, link])
    assert len(refs) == 1


def test_remote_links_handles_missing_object_key():
    links = [{"globalId": "something", "id": 1}]
    refs = extract_pr_refs_from_remote_links(links)
    assert refs == []
```

- [ ] **Step 5: Run tests to verify they fail**

```bash
cd "/Users/kiran.jadhav/Test Agent/test-Agent"
PYTHONPATH=. pytest tests/test_bitbucket_pr.py -v 2>&1 | head -30
```

Expected: `ImportError` or `AttributeError` — `extract_pr_refs_from_text` and `extract_pr_refs_from_remote_links` do not exist yet.

- [ ] **Step 6: Commit the test file**

```bash
git add tests/__init__.py tests/test_bitbucket_pr.py
git commit -m "test: add failing tests for PR ref extraction helpers"
```

---

## Task 2: Add `extract_pr_refs_from_text` and `extract_pr_refs_from_remote_links` to `bitbucket_pr.py`

**Files:**
- Modify: `jira_qa_agent/bitbucket_pr.py` (after line 87, before `_bb_http_client`)

- [ ] **Step 1: Add the deduplication helper and `extract_pr_refs_from_text`**

Open `jira_qa_agent/bitbucket_pr.py` and insert the following block **after** the `parse_pr_ref` function (after line 87) and **before** `_bb_http_client`:

```python
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
```

- [ ] **Step 2: Run the tests — they should pass**

```bash
cd "/Users/kiran.jadhav/Test Agent/test-Agent"
PYTHONPATH=. pytest tests/test_bitbucket_pr.py -v
```

Expected output: all 10 tests PASS.

- [ ] **Step 3: Commit**

```bash
git add jira_qa_agent/bitbucket_pr.py
git commit -m "feat: add extract_pr_refs_from_text and extract_pr_refs_from_remote_links"
```

---

## Task 3: Add `get_remote_links` to `JiraClient`

**Files:**
- Modify: `jira_qa_agent/jira_client.py`

- [ ] **Step 1: Add the method**

Open `jira_qa_agent/jira_client.py` and append the following method inside the `JiraClient` class, after `get_comments`:

```python
    def get_remote_links(self, key: str) -> list[dict]:
        """
        Returns all remote links on a Jira issue.
        The Bitbucket app adds a remote link for every PR it associates with the ticket.
        Returns an empty list (not an error) if the endpoint returns 404 or 403.
        """
        with httpx.Client(auth=self._auth, timeout=60.0) as c:
            r = c.get(f"{self._base}/issue/{key}/remotelink")
            if r.status_code in (403, 404):
                return []
            r.raise_for_status()
            return list(r.json() or [])
```

- [ ] **Step 2: Verify no import errors**

```bash
cd "/Users/kiran.jadhav/Test Agent/test-Agent"
PYTHONPATH=. python3 -c "from jira_qa_agent.jira_client import JiraClient; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run existing tests to confirm nothing broke**

```bash
PYTHONPATH=. pytest tests/test_bitbucket_pr.py -v
```

Expected: all 10 tests still PASS.

- [ ] **Step 4: Commit**

```bash
git add jira_qa_agent/jira_client.py
git commit -m "feat: add JiraClient.get_remote_links for PR auto-detection"
```

---

## Task 4: Add `_pick_pr` and `_discover_pr_ref` to `cli.py`, update `main()`

**Files:**
- Modify: `jira_qa_agent/cli.py`

- [ ] **Step 1: Update the imports at the top of `cli.py`**

The current import block for `bitbucket_pr` looks like:

```python
from jira_qa_agent.bitbucket_pr import (
    PRRef,
    fetch_pr_diff_cloud,
    fetch_pr_diff_dc,
    parse_pr_ref,
)
```

Replace it with:

```python
from jira_qa_agent.bitbucket_pr import (
    PRRef,
    extract_pr_refs_from_remote_links,
    extract_pr_refs_from_text,
    fetch_pr_diff_cloud,
    fetch_pr_diff_dc,
    parse_pr_ref,
)
```

- [ ] **Step 2: Add `_pick_pr` after the `_fetch_bb_diff` function (after line 64)**

Insert this function between `_fetch_bb_diff` and `_review_loop`:

```python
def _pick_pr(refs: list[PRRef]) -> PRRef:
    """Print a numbered menu and return the user's chosen PRRef."""
    print(f"\nFound {len(refs)} PRs:")
    for i, r in enumerate(refs, 1):
        base = f"  ({r.dc_base_url})" if r.kind == "dc" else "  (bitbucket.org)"
        print(f"  [{i}]  {r.kind}  {r.project_or_workspace} / {r.repo_slug}  #{r.pr_id}{base}")
    while True:
        try:
            raw = input(f"Pick a PR to analyse [1-{len(refs)}] (default 1): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(0)
        if raw == "":
            return refs[0]
        if raw.isdigit() and 1 <= int(raw) <= len(refs):
            return refs[int(raw) - 1]
        print(f"Please enter a number between 1 and {len(refs)}.")
```

- [ ] **Step 3: Add `_discover_pr_ref` after `_pick_pr`**

Insert this function immediately after `_pick_pr`:

```python
def _discover_pr_ref(
    pr_arg: str | None,
    blob: str,
    jc: JiraClient,
    issue_key: str,
    settings: Settings,
) -> PRRef:
    """
    Three-stage PR discovery:
      1. --pr flag (manual, highest priority)
      2. Jira remote links API
      3. Regex scan of ticket text (description + comments)
    Returns a single PRRef (prompts user if multiple found).
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
        return ref

    # Stage 2: Jira remote links
    print(f"Looking for linked PRs on {issue_key} via Jira remote links...")
    links = jc.get_remote_links(issue_key)
    refs = extract_pr_refs_from_remote_links(links, server_base_url=server_url)

    # Stage 3: text scan fallback
    if not refs:
        print("No remote links found — scanning ticket text for PR references...")
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
        return r

    return _pick_pr(refs)
```

- [ ] **Step 4: Replace the PR parsing block inside `main()`**

In `main()`, find and **replace** this block (lines 163–177 in the current file):

```python
    blob_parts = [summary, desc_text, *comment_lines]
    if args.pr:
        blob_parts.append(args.pr)
    blob = "\n".join(blob_parts)

    parsed = (
        parse_pr_ref(args.pr, server_base_url=settings.bitbucket_server_base_url)
        if args.pr
        else parse_pr_ref(blob, server_base_url=settings.bitbucket_server_base_url)
    )
    if not parsed:
        raise SystemExit(
            "Could not find a Bitbucket PR reference. Pass --pr with "
            "PROJECT/repo#123 (DC), workspace/repo#123 (Cloud), or a full pull-request URL."
        )
```

With:

```python
    blob_parts = [summary, desc_text, *comment_lines]
    if args.pr:
        blob_parts.append(args.pr)
    blob = "\n".join(blob_parts)

    parsed = _discover_pr_ref(args.pr, blob, jc, args.issue_key, settings)
```

- [ ] **Step 5: Verify the module loads cleanly**

```bash
cd "/Users/kiran.jadhav/Test Agent/test-Agent"
PYTHONPATH=. python3 -c "from jira_qa_agent.cli import main; print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Run all tests**

```bash
PYTHONPATH=. pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add jira_qa_agent/cli.py
git commit -m "feat: auto-detect Bitbucket PR from Jira remote links and ticket text"
```

---

## Task 5: Write CLI discovery unit tests

**Files:**
- Create: `tests/test_cli_discovery.py`

- [ ] **Step 1: Write tests for `_pick_pr`**

Create `tests/test_cli_discovery.py`:

```python
from __future__ import annotations

from io import StringIO
from unittest.mock import patch

import pytest

from jira_qa_agent.bitbucket_pr import PRRef
from jira_qa_agent.cli import _pick_pr


_DC_PR_1 = PRRef(kind="dc", project_or_workspace="NDP", repo_slug="nd-mfe", pr_id=1, dc_base_url="https://stash.x.com")
_DC_PR_2 = PRRef(kind="dc", project_or_workspace="NDP", repo_slug="nd-api", pr_id=2, dc_base_url="https://stash.x.com")


def test_pick_pr_default_selects_first(capsys):
    with patch("builtins.input", return_value=""):
        result = _pick_pr([_DC_PR_1, _DC_PR_2])
    assert result == _DC_PR_1


def test_pick_pr_selects_second(capsys):
    with patch("builtins.input", return_value="2"):
        result = _pick_pr([_DC_PR_1, _DC_PR_2])
    assert result == _DC_PR_2


def test_pick_pr_invalid_then_valid(capsys):
    with patch("builtins.input", side_effect=["0", "5", "1"]):
        result = _pick_pr([_DC_PR_1, _DC_PR_2])
    assert result == _DC_PR_1
```

- [ ] **Step 2: Write tests for `_discover_pr_ref` — manual `--pr` stage**

Append to `tests/test_cli_discovery.py`:

```python
from unittest.mock import MagicMock

from jira_qa_agent.cli import _discover_pr_ref


def _make_settings(server_url="https://stash.x.com"):
    s = MagicMock()
    s.bitbucket_server_base_url = server_url
    return s


def test_discover_uses_pr_arg_directly():
    settings = _make_settings()
    jc = MagicMock()
    result = _discover_pr_ref(
        "NDP/nd-mfe#42", "some blob", jc, "SOFT-1", settings
    )
    assert result.pr_id == 42
    assert result.kind == "dc"
    jc.get_remote_links.assert_not_called()


def test_discover_exits_on_unparseable_pr_arg():
    settings = _make_settings(server_url=None)
    jc = MagicMock()
    with pytest.raises(SystemExit, match="Could not parse"):
        _discover_pr_ref("not-a-pr-ref", "blob", jc, "SOFT-1", settings)
```

- [ ] **Step 3: Write tests for `_discover_pr_ref` — remote links stage**

Append to `tests/test_cli_discovery.py`:

```python
def test_discover_uses_remote_links():
    settings = _make_settings()
    jc = MagicMock()
    jc.get_remote_links.return_value = [
        {
            "object": {
                "url": "https://stash.x.com/projects/NDP/repos/nd-mfe/pull-requests/99",
                "title": "PR #99",
            }
        }
    ]
    result = _discover_pr_ref(None, "no pr refs here", jc, "SOFT-1", settings)
    assert result.pr_id == 99


def test_discover_falls_back_to_text_scan():
    settings = _make_settings()
    jc = MagicMock()
    jc.get_remote_links.return_value = []
    blob = "See https://stash.x.com/projects/NDP/repos/nd-mfe/pull-requests/77 for context"
    result = _discover_pr_ref(None, blob, jc, "SOFT-1", settings)
    assert result.pr_id == 77


def test_discover_exits_when_nothing_found():
    settings = _make_settings(server_url=None)
    jc = MagicMock()
    jc.get_remote_links.return_value = []
    with pytest.raises(SystemExit, match="No Bitbucket PR found"):
        _discover_pr_ref(None, "no links here", jc, "SOFT-1", settings)
```

- [ ] **Step 4: Run all tests**

```bash
cd "/Users/kiran.jadhav/Test Agent/test-Agent"
PYTHONPATH=. pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/test_cli_discovery.py
git commit -m "test: add unit tests for PR auto-detection discovery logic"
```

---

## Task 6: Smoke-test the full agent end-to-end

**This task has no automated test — it verifies the real integration.**

- [ ] **Step 1: Run the agent with only a ticket ID (no `--pr`)**

```bash
cd "/Users/kiran.jadhav/Test Agent/test-Agent"
PYTHONPATH=. python3 -m jira_qa_agent SOFT-186005
```

Expected console output (order may vary):
```
Fetching Jira ticket SOFT-186005...
Looking for linked PRs on SOFT-186005 via Jira remote links...
Auto-detected PR: stash.newfold.com/projects/NDP/repos/nd-mfe-sites/pull-requests/2384 — proceeding...
Fetching PR diff from Bitbucket (dc): ...
Diff fetched (...). Running LLM analysis...
[test report printed here]
Is this report good? ...
```

If remote links returns nothing, you should instead see:
```
No remote links found — scanning ticket text for PR references...
Auto-detected PR: ...
```

- [ ] **Step 2: Verify `--pr` override still works**

```bash
PYTHONPATH=. python3 -m jira_qa_agent SOFT-186005 --pr NDP/nd-mfe-sites#2384
```

Expected: agent uses the provided PR directly, no discovery messages printed.

- [ ] **Step 3: Final commit if any fixups were needed**

```bash
git add -A && git commit -m "fix: smoke-test fixups for PR auto-detection"
```

(Skip this step if no changes were needed.)
