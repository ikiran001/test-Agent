from __future__ import annotations

from unittest.mock import MagicMock

from jira_qa_agent.analyze import build_test_report, get_system_prompt


# --- get_system_prompt ---

def test_bug_prompt_is_returned_for_bug():
    prompt = get_system_prompt("Bug")
    assert "bug" in prompt.lower() or "regress" in prompt.lower()


def test_feature_prompt_is_returned_for_feature():
    assert get_system_prompt("Feature") != get_system_prompt("Bug")


def test_story_prompt_is_returned_for_story():
    assert get_system_prompt("Story") != get_system_prompt("Feature")


def test_task_prompt_is_returned_for_task():
    assert get_system_prompt("Task") != get_system_prompt("Bug")


def test_unknown_type_returns_default():
    assert get_system_prompt("Whatever") == get_system_prompt("")


def test_empty_string_returns_default():
    assert get_system_prompt("") is not None
    assert len(get_system_prompt("")) > 100


def test_case_sensitive_lookup():
    # "bug" (lowercase) should fall back to default, not Bug prompt
    assert get_system_prompt("bug") == get_system_prompt("")


def test_subtask_returns_default():
    assert get_system_prompt("Sub-task") == get_system_prompt("")


# --- build_test_report ---

def test_build_test_report_accepts_issue_type():
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="## Summary\ntest")
    result = build_test_report(llm, "some bundle", issue_type="Bug")
    assert result == "## Summary\ntest"
    llm.invoke.assert_called_once()


def test_build_test_report_default_issue_type():
    llm = MagicMock()
    llm.invoke.return_value = MagicMock(content="## Summary\ntest")
    # Should work with no issue_type argument (backward compat)
    result = build_test_report(llm, "some bundle")
    assert result == "## Summary\ntest"


def test_bug_and_feature_use_different_system_messages():
    calls = []

    def capture_invoke(messages):
        calls.append(messages[0].content)  # SystemMessage content
        return MagicMock(content="## Summary\ntest")

    llm = MagicMock()
    llm.invoke.side_effect = capture_invoke

    build_test_report(llm, "bundle", issue_type="Bug")
    build_test_report(llm, "bundle", issue_type="Feature")

    assert calls[0] != calls[1], "Bug and Feature should use different system prompts"
