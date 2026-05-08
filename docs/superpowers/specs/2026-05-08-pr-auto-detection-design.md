# Design: Automatic PR Detection for Jira QA Agent

**Date:** 2026-05-08  
**Status:** Approved  
**Goal:** Eliminate the need to manually supply `--pr PROJECT/repo#123` on every run.

---

## Problem

The agent currently requires the user to look up and type the Bitbucket PR reference
manually every time (`--pr CL/huapi#1425`). This is friction — the Jira ticket already
links to the PR via the Development panel, and the PR URL is often in the ticket body or
comments too.

---

## Solution: Three-Stage PR Discovery (Approach C)

Try three sources in priority order. Stop as soon as at least one PR is found.

```
Stage 1 — Manual override      --pr flag (user provides PR reference explicitly)
Stage 2 — Jira remote links    GET /rest/api/3/issue/{key}/remotelink
Stage 3 — Text scan            Regex over ticket description + comment bodies
```

`--pr` is still supported as an escape hatch for power users or edge cases.

---

## Stage Detail

### Stage 1: `--pr` flag (unchanged)

If `--pr` is passed, parse it immediately with the existing `parse_pr_ref()` and skip
stages 2 and 3 entirely. Behaviour is identical to the current agent.

### Stage 2: Jira Remote Links API

Call `GET /rest/api/3/issue/{key}/remotelink` (same Basic-auth credentials already in use).

The Bitbucket Jira app adds a remote link for every PR it links to a ticket. Each link
object looks like:

```json
{
  "object": {
    "url": "https://stash.company.com/projects/NDP/repos/nd-mfe-sites/browse",
    "title": "PR #2384 - Add cPanel logo"
  }
}
```

Filter for entries whose `object.url` contains `bitbucket` or `stash`, then pass each
URL through the existing `parse_pr_ref()`. Deduplicate by `(project, repo, pr_id)`.

### Stage 3: Text scan

If Stage 2 returns nothing, scan the concatenated ticket description and all comment
bodies using the three regex patterns already defined in `bitbucket_pr.py`:

- `_BB_CLOUD_REF` — `bitbucket.org/workspace/repo/pull-requests/N`
- `_BB_DC_REF` — `stash.company.com/projects/PROJ/repos/repo/pull-requests/N`
- `_BB_SHORT` — `PROJECT/repo#N` (short form)

Deduplicate and return the list.

---

## Multiple PR Handling

If discovery returns more than one PR, print a numbered menu and let the user pick:

```
Found 2 PRs linked to SOFT-186005:
  [1]  dc  NDP / nd-mfe-sites   #2384   (stash.newfold.com)
  [2]  dc  NDP / nd-mfe-api     #991    (stash.newfold.com)
Pick a PR to analyse [1-2] (default 1):
```

The user types a number (or presses Enter to accept the first). The chosen `PRRef` is
used for the rest of the run — diff fetch, LLM analysis, Jira comment — exactly as today.

If exactly one PR is found, print a confirmation line and proceed without prompting:

```
Auto-detected PR: NDP/nd-mfe-sites#2384 (dc) — proceeding...
```

If no PR is found after all three stages, exit with a clear message:

```
No Bitbucket PR found on SOFT-186005.
Use --pr PROJECT/repo#123 (DC) or workspace/repo#123 (Cloud) to specify one manually.
```

---

## File Changes

### `jira_qa_agent/jira_client.py`

Add one method:

```python
def get_remote_links(self, issue_key: str) -> list[dict]:
    """
    Returns remote links attached to the Jira issue.
    The Bitbucket app adds a remote link for every linked PR.
    """
    r = self._client.get(f"/rest/api/3/issue/{issue_key}/remotelink")
    r.raise_for_status()
    return r.json()  # list of remote link objects
```

### `jira_qa_agent/bitbucket_pr.py`

Add one new public helper at module level (no class needed):

```python
def extract_pr_refs_from_remote_links(
    links: list[dict],
    *,
    server_base_url: str | None = None,
) -> list[PRRef]:
    """
    Given the raw list from the Jira remote-links API, return deduplicated PRRef objects
    for any Bitbucket URLs found.
    """
```

Implementation:
1. For each link, pull `link.get("object", {}).get("url", "")`.
2. Skip if URL does not contain `bitbucket` or `stash`.
3. Call `parse_pr_ref(url, server_base_url=server_base_url)`.
4. Collect non-None results, deduplicate on `(project_or_workspace, repo_slug, pr_id)`.

The existing `extract_pr_refs_from_text` function (Stage 3) is already implicit in the
current code — pull it out into a named helper with the same signature for clarity:

```python
def extract_pr_refs_from_text(
    text: str,
    *,
    server_base_url: str | None = None,
) -> list[PRRef]:
    """Scan free-form text for Bitbucket PR references."""
```

### `jira_qa_agent/cli.py`

Replace the current `--pr`-or-fail block in `main()` with the three-stage discovery
function `_discover_pr_ref()` and a `_pick_pr()` selector:

```python
def _discover_pr_ref(
    pr_arg: str | None,
    blob: str,
    jc: JiraClient,
    issue_key: str,
    settings: Settings,
) -> PRRef:
    """
    Run the three-stage PR discovery and return a single PRRef.
    Exits with a clear message if nothing is found.
    """

def _pick_pr(refs: list[PRRef]) -> PRRef:
    """Print a numbered menu and return the user's choice."""
```

No other files change.

---

## Error Handling

| Situation | Behaviour |
|-----------|-----------|
| Remote links API returns 404 | Treat as empty list, fall through to Stage 3 |
| Remote links API returns 401/403 | Print warning, fall through to Stage 3 |
| URL in remote link is a non-PR Bitbucket URL (e.g. repo browse) | `parse_pr_ref` returns None → skipped silently |
| No PR found after all 3 stages | `SystemExit` with instructions to use `--pr` |
| User picks invalid number at menu | Re-prompt until valid |

---

## Backward Compatibility

- `--pr` still works exactly as before — no behaviour change for existing scripts.
- The `BITBUCKET_SERVER_URL` env var is still required for DC short-form refs.
- No new environment variables are needed.
- No new dependencies are needed.

---

## Success Criteria

1. Running `python -m jira_qa_agent SOFT-186005` (no `--pr`) finds the linked PR
   automatically and proceeds to generate the test report.
2. When two PRs are linked, the numbered picker appears and the chosen PR is used.
3. `--pr` still overrides discovery and works as before.
4. If no PR is found, a clear actionable error message is shown.
