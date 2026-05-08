from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from jira_qa_agent.bitbucket_pr import PRRef
from jira_qa_agent.cli import _discover_pr_ref, _pick_pr


_DC_PR_1 = PRRef(kind="dc", project_or_workspace="NDP", repo_slug="nd-mfe", pr_id=1, dc_base_url="https://stash.x.com")
_DC_PR_2 = PRRef(kind="dc", project_or_workspace="NDP", repo_slug="nd-api", pr_id=2, dc_base_url="https://stash.x.com")


def _make_settings(server_url="https://stash.x.com"):
    s = MagicMock()
    s.bitbucket_server_base_url = server_url
    return s


# --- _pick_pr tests ---

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


# --- _discover_pr_ref: Stage 1 (--pr flag) ---

def test_discover_uses_pr_arg_directly():
    settings = _make_settings()
    jc = MagicMock()
    result = _discover_pr_ref("NDP/nd-mfe#42", "some blob", jc, "SOFT-1", settings)
    assert result.pr_id == 42
    assert result.kind == "dc"
    jc.get_remote_links.assert_not_called()


def test_discover_exits_on_unparseable_pr_arg():
    settings = _make_settings(server_url=None)
    jc = MagicMock()
    with pytest.raises(SystemExit, match="Could not parse"):
        _discover_pr_ref("not-a-pr-ref", "blob", jc, "SOFT-1", settings)


# --- _discover_pr_ref: Stage 2 (remote links) ---

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


# --- _discover_pr_ref: Stage 3 (text scan fallback) ---

def test_discover_falls_back_to_text_scan():
    settings = _make_settings()
    jc = MagicMock()
    jc.get_remote_links.return_value = []
    blob = "See https://stash.x.com/projects/NDP/repos/nd-mfe/pull-requests/77 for context"
    result = _discover_pr_ref(None, blob, jc, "SOFT-1", settings)
    assert result.pr_id == 77


# --- _discover_pr_ref: no PR found ---

def test_discover_exits_when_nothing_found():
    settings = _make_settings(server_url=None)
    jc = MagicMock()
    jc.get_remote_links.return_value = []
    with pytest.raises(SystemExit, match="No Bitbucket PR found"):
        _discover_pr_ref(None, "no links here", jc, "SOFT-1", settings)
