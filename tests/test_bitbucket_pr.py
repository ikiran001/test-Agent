from __future__ import annotations

from jira_qa_agent.bitbucket_pr import (
    PRRef,
    extract_pr_refs_from_remote_links,
    extract_pr_refs_from_text,
)


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


def test_extract_short_ref_without_server_url():
    text = "Fix for myworkspace/my-repo#55"
    refs = extract_pr_refs_from_text(text)
    assert len(refs) == 1
    assert refs[0] == PRRef(
        kind="cloud",
        project_or_workspace="myworkspace",
        repo_slug="my-repo",
        pr_id=55,
        dc_base_url=None,
    )


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
    assert refs[0] == PRRef(
        kind="dc",
        project_or_workspace="NDP",
        repo_slug="nd-mfe",
        pr_id=42,
        dc_base_url="https://stash.example.com",
    )


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
