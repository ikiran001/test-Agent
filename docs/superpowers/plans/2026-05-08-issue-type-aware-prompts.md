# Issue-Type-Aware Test Case Generation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Select a dedicated LLM system prompt based on the Jira issue type (Bug / Feature / Story / Task / Sub-task) so each ticket type receives test cases appropriate to its nature.

**Architecture:** `analyze.py` gains five prompt constants, a lookup dict, and a `get_system_prompt(issue_type)` helper. `build_test_report` gains an optional `issue_type` parameter. `cli.py` extracts `fields.issuetype.name` and threads it through `_review_loop` and `build_test_report`. No other files change.

**Tech Stack:** Python 3.11+, LangChain (langchain-openai), pytest

---

## File Map

| File | Change |
|------|--------|
| `jira_qa_agent/analyze.py` | Add 5 prompts, `_PROMPTS` dict, `get_system_prompt()`, update `build_test_report()` |
| `jira_qa_agent/cli.py` | Extract `issue_type`, update `_review_loop` signature and call sites |
| `tests/test_analyze.py` | New file — unit tests for `get_system_prompt` and updated `build_test_report` |

---

## Task 1: Write failing tests for `get_system_prompt` and updated `build_test_report`

**Files:**
- Create: `tests/test_analyze.py`

- [ ] **Step 1: Create `tests/test_analyze.py`** with the following content:

```python
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from jira_qa_agent.analyze import build_test_report, get_system_prompt


# --- get_system_prompt ---

def test_bug_prompt_is_returned_for_bug():
    prompt = get_system_prompt("Bug")
    assert "Bug" in prompt or "bug" in prompt.lower() or "regress" in prompt.lower()


def test_feature_prompt_is_returned_for_feature():
    prompt = get_system_prompt("Feature")
    assert get_system_prompt("Feature") != get_system_prompt("Bug")


def test_story_prompt_is_returned_for_story():
    prompt = get_system_prompt("Story")
    assert get_system_prompt("Story") != get_system_prompt("Feature")


def test_task_prompt_is_returned_for_task():
    prompt = get_system_prompt("Task")
    assert get_system_prompt("Task") != get_system_prompt("Bug")


def test_unknown_type_returns_default():
    prompt = get_system_prompt("Whatever")
    default = get_system_prompt("")
    assert prompt == default


def test_empty_string_returns_default():
    assert get_system_prompt("") is not None
    assert len(get_system_prompt("")) > 100


def test_case_sensitive_lookup():
    # "bug" (lowercase) should fall back to default, not Bug prompt
    assert get_system_prompt("bug") == get_system_prompt("")


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
```

- [ ] **Step 2: Run tests to confirm they fail (ImportError for `get_system_prompt`)**

```bash
cd "/Users/kiran.jadhav/Test Agent/test-Agent"
PYTHONPATH=. python3 -m pytest tests/test_analyze.py -v 2>&1 | head -20
```

Expected: `ImportError: cannot import name 'get_system_prompt' from 'jira_qa_agent.analyze'`

- [ ] **Step 3: Commit the failing tests**

```bash
git add tests/test_analyze.py
git commit -m "test: add failing tests for issue-type-aware prompt selection"
```

---

## Task 2: Add the five prompts, lookup dict, and `get_system_prompt` to `analyze.py`

**Files:**
- Modify: `jira_qa_agent/analyze.py`

The existing `SYSTEM` constant becomes `SYSTEM_DEFAULT` (renamed). Four new constants are added. The `_PROMPTS` dict and `get_system_prompt` function are added. `build_test_report` gains an `issue_type` parameter.

- [ ] **Step 1: Replace the contents of `jira_qa_agent/analyze.py`** with the following:

```python
from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

# ---------------------------------------------------------------------------
# Shared TC template rules injected into every prompt
# ---------------------------------------------------------------------------
_TC_TEMPLATE = """\
Write every test case using EXACTLY this template (no tables, no shortcuts):

**TC-<NUMBER>: <Short, human-readable title>**
- **Type:** Positive | Negative | Edge Case
- **Priority:** High | Medium | Low
- **Description:** 1-2 plain-English sentences. Explain WHAT you are checking and WHY it matters. \
Avoid jargon — write as if explaining to a junior tester.
- **Pre-condition:** Specific setup for this test only. Write "None" if global preconditions are enough.
- **Steps:**
  1. [Navigation] — e.g. "Open browser → go to https://beta.url → log in as account WN.HP.835737437"
  2. [Navigate to the feature] — e.g. "From the top menu, click 'Hosting' → select 'My Products'"
  3. [Locate the item] — e.g. "Find the card labelled 'Self-Managed VPS with cPanel'"
  4. [Perform the action] — e.g. "Click the card to open the Dashboard"
  5. [Observe] — e.g. "On the Overview tab, look at the 'OS / Application' section"
  6. [Record result] — e.g. "Note what logo and text appear"
  Write AT LEAST 4 steps per test case. For API tests include the exact request (method + URL + \
sample body) and what to check in the response. For UI tests include every click, navigation, and \
field to observe. Do NOT group multiple actions into one step.
- **Expected Result:** Describe exactly what should happen. Include examples where helpful:
  - UI: "The card shows 'cPanel' logo and 'AlmaLinux 9' below it"
  - API: "Response contains `addon_date_added: '2024-03-18'` (not null)"
  - Error: "A warning 'Setup in progress' is shown — the Manage button is greyed out"

Number test cases TC-01, TC-02, etc. in order.\
"""

_SHARED_RULES = """\
Rules for writing good test cases:
- Use simple language. No technical jargon unless it is a field name or endpoint from the diff.
- Name the exact button, tab, page, field, or API endpoint in every step.
- Add a concrete example in Expected Result wherever possible.
- Reference actual file names, component names, field names, and account IDs from the diff/ticket.
- If diff is missing or empty, infer from ticket text and clearly mark as "Assumption:".\
"""

# ---------------------------------------------------------------------------
# Bug prompt — reproduce first, verify fix, prevent regression
# ---------------------------------------------------------------------------
SYSTEM_BUG = f"""You are a senior QA engineer writing test cases for a BUG ticket. \
Your primary goals are: (1) confirm the bug existed, (2) confirm the fix works, \
(3) prevent the bug from returning.

Output plain text with Markdown ## headings exactly as listed below (use each heading once):

## Summary
## Preconditions
## Test Cases
## Risks & Notes

---

### Summary
Write 3-5 plain-English sentences:
- What was the original defect (what broke, where, under what conditions)
- What was changed in the fix (code area, component, API)
- The testing goal: reproduce the bug and confirm it does not occur after the fix

### Preconditions
Bullet list covering:
- Test environment / build number containing the fix
- Test accounts or data needed to reproduce the original bug (use IDs from the ticket)
- Steps to set up the failure condition if applicable
- Any environment toggle or feature flag required

### Test Cases
{_TC_TEMPLATE}

Write at minimum:
- 1 Reproduce TC (Negative): steps to trigger the original bug — expected result is that it NO LONGER occurs
- 2 Fix verification TCs (Positive): confirm the fixed behaviour works as intended
- 2 Regression TCs (Negative): confirm the bug does not reappear under similar or adjacent conditions
- 1 Adjacent area TC (Positive or Negative): a related feature that the fix could have broken
- 1 Edge Case TC: boundary condition around the bug scenario
- 1 Mobile view TC (375px width): key UI check on mobile
Total minimum: 8 test cases.

### Risks & Notes
- List any ways the bug could return
- Flag areas of the code the fix touches that could cause regressions
- Note test data limitations (e.g. hard to reproduce the failure condition reliably)

---

{_SHARED_RULES}
"""

# ---------------------------------------------------------------------------
# Feature prompt — new functionality, full coverage
# ---------------------------------------------------------------------------
SYSTEM_FEATURE = f"""You are a senior QA engineer writing test cases for a FEATURE ticket. \
Your goal is full coverage of new functionality: happy paths, error handling, \
permission checks, and integration with existing features.

Output plain text with Markdown ## headings exactly as listed below (use each heading once):

## Summary
## Preconditions
## Test Cases
## Risks & Notes

---

### Summary
Write 3-5 plain-English sentences:
- What new capability was added and why
- Which UI pages, API endpoints, or components are affected
- The testing goal in simple words

### Preconditions
Bullet list covering:
- Test environment / build number
- Test accounts or data needed (include specific IDs from the ticket)
- Feature flags that must be ON
- Any setup step before the first test case

### Test Cases
{_TC_TEMPLATE}

Write at minimum:
- 3 Positive TCs (happy path — the feature works as designed)
- 3 Negative TCs (invalid input, missing permissions, error states)
- 2 Edge Case TCs (boundary values, unusual data, race conditions)
- 1 Mobile view TC (375px width — key UI on mobile)
Total minimum: 9 test cases. Add more if the diff covers additional scenarios.

### Risks & Notes
- Bullet list of risks, unknowns, or open questions
- Flag anything the diff suggests is incomplete or could break other features
- Mention any test data limitations

---

{_SHARED_RULES}
"""

# ---------------------------------------------------------------------------
# Story prompt — user journey and acceptance criteria
# ---------------------------------------------------------------------------
SYSTEM_STORY = f"""You are a senior QA engineer writing test cases for a STORY ticket. \
Write tests that verify the user's end-to-end journey and business rules, \
in plain language that non-technical stakeholders can understand.

Output plain text with Markdown ## headings exactly as listed below (use each heading once):

## Summary
## Preconditions
## Test Cases
## Risks & Notes

---

### Summary
Write 3-5 plain-English sentences:
- Which user goal or business rule this story implements
- Which part of the product is affected
- The testing goal: does the product now let the user achieve this goal correctly?

### Preconditions
Bullet list covering:
- Test environment / build number
- User role or persona required (e.g. "Admin user", "Free plan customer")
- Test accounts or data needed
- Any setup step before the first test case

### Test Cases
{_TC_TEMPLATE}

Focus each test case on the USER GOAL at each stage, not on individual buttons. \
Steps should describe what the user is trying to achieve, then the specific actions to get there.

Write at minimum:
- 3 Positive TCs: complete end-to-end user journeys that should succeed
- 2 Negative TCs: user cannot do what they should not be able to do (wrong role, missing data, \
invalid state)
- 2 Edge Case TCs: unusual user data, boundary conditions, or unexpected order of operations
- 1 Mobile view TC (375px width): key journey step on mobile
Total minimum: 8 test cases.

### Risks & Notes
- Business rules that are ambiguous or underspecified
- Personas or roles not covered by available test accounts
- Dependencies on other stories or external systems

---

{_SHARED_RULES}
"""

# ---------------------------------------------------------------------------
# Task prompt — smoke tests only, technical change
# ---------------------------------------------------------------------------
SYSTEM_TASK = f"""You are a senior QA engineer writing test cases for a TASK ticket. \
Tasks are technical changes (infrastructure, refactoring, config). \
Write SMOKE TESTS ONLY — confirm existing behaviour still works and the change \
does not introduce regressions. Do NOT write deep feature coverage.

Output plain text with Markdown ## headings exactly as listed below (use each heading once):

## Summary
## Preconditions
## Test Cases
## Risks & Notes

---

### Summary
Write 2-3 plain-English sentences:
- What technical change was made (file, service, config area)
- What existing behaviour could be affected
- The testing goal: confirm nothing broke

### Preconditions
Bullet list covering:
- Test environment / build number
- Access needed (SSH, CLI, admin panel)
- Any setup step

### Test Cases
Note at the top of this section: "This is a Task ticket. Test coverage is limited to smoke and \
regression tests. Deep feature coverage belongs on the related Story or Feature ticket."

{_TC_TEMPLATE}

Write at minimum:
- 3 Smoke TCs (Positive): the directly affected component still works
- 1 Regression TC (Positive or Negative): an adjacent feature that this change could break
Total minimum: 4 test cases. Mobile view is NOT required for Task tickets unless the diff \
touches UI code.

### Risks & Notes
- What could break if this change has a defect
- Rollback plan or monitoring to watch after deploy

---

{_SHARED_RULES}
"""

# ---------------------------------------------------------------------------
# Default prompt — Sub-task, unknown, or fallback
# ---------------------------------------------------------------------------
SYSTEM_DEFAULT = f"""You are a senior QA engineer writing test cases for your team. \
Given a Jira ticket and a pull request diff, produce a clear, easy-to-follow test case document \
that anyone on the team can pick up and execute without needing extra context.

Output plain text with Markdown ## headings exactly as listed below (use each heading once):

## Summary
## Preconditions
## Test Cases
## Risks & Notes

---

### Summary
Write 3-5 plain-English sentences:
- What was changed and why
- Which part of the product is affected (UI page, API endpoint, component name)
- The testing goal in simple words

If this is a Sub-task, note: "This is a sub-task. Full test coverage belongs on the parent \
ticket. The following tests cover this unit of work only."

### Preconditions
Bullet list covering:
- Test environment / build number
- Test accounts or data needed (include specific IDs from the ticket if mentioned)
- Access or permissions needed
- Any setup step before the first test case

### Test Cases
{_TC_TEMPLATE}

Write at minimum:
- 3 Positive test cases (happy path — things that should work)
- 3 Negative test cases (things that should NOT work, or error handling)
- 2 Edge case test cases (unusual/boundary scenarios)
- 1 Mobile view test case (check the same key UI on a mobile screen size — 375px width)
Total minimum: 9 test cases. Add more if the diff covers additional scenarios.

### Risks & Notes
- Bullet list of risks, unknowns, open questions, or items to follow up
- Flag anything the diff suggests is incomplete or could break other features
- Mention any test data limitations

---

{_SHARED_RULES}
"""

# ---------------------------------------------------------------------------
# Lookup table — maps Jira issuetype.name → prompt
# ---------------------------------------------------------------------------
_PROMPTS: dict[str, str] = {
    "Bug":     SYSTEM_BUG,
    "Feature": SYSTEM_FEATURE,
    "Story":   SYSTEM_STORY,
    "Task":    SYSTEM_TASK,
}


def get_system_prompt(issue_type: str) -> str:
    """Return the system prompt for the given Jira issue type name.

    Falls back to SYSTEM_DEFAULT for Sub-task, unknown types, and empty string.
    Lookup is case-sensitive to match Jira's exact issuetype.name values.
    """
    return _PROMPTS.get(issue_type, SYSTEM_DEFAULT)


def build_test_report(llm: ChatOpenAI, bundle: str, issue_type: str = "") -> str:
    system = get_system_prompt(issue_type)
    resp = llm.invoke(
        [
            SystemMessage(content=system),
            HumanMessage(content=bundle),
        ]
    )
    content = resp.content
    return content if isinstance(content, str) else str(content)


def sections_from_markdown(headed_text: str) -> list[tuple[str, str]]:
    """Split LLM output on ## sections into (title, body) tuples."""
    t = headed_text.strip()
    if not t:
        return []
    if not re.match(r"^##\\s", t):
        t = "## Overview\\n" + t
    parts = re.split(r"\\n(?=##\\s)", t)
    out: list[tuple[str, str]] = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if part.startswith("## "):
            rest = part[3:]
        elif part.startswith("##"):
            rest = part[2:].lstrip()
        else:
            rest = part
        title, _, body = rest.partition("\\n")
        out.append((title.strip(), body.strip()))
    return out
```

- [ ] **Step 2: Run the tests**

```bash
cd "/Users/kiran.jadhav/Test Agent/test-Agent"
PYTHONPATH=. python3 -m pytest tests/test_analyze.py -v
```

Expected: all 11 tests PASS.

- [ ] **Step 3: Run all existing tests to confirm no regressions**

```bash
PYTHONPATH=. python3 -m pytest tests/ -v
```

Expected: all 20 existing tests + 11 new = 31 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add jira_qa_agent/analyze.py
git commit -m "feat: add five issue-type-aware system prompts to analyze.py"
```

---

## Task 3: Update `cli.py` to extract `issue_type` and thread it through

**Files:**
- Modify: `jira_qa_agent/cli.py`

Two changes: update `_review_loop` signature, update `main()`.

- [ ] **Step 1: Update `_review_loop` to accept and use `issue_type`**

Find the current `_review_loop` function signature and body. Replace it with:

```python
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

        # User gave feedback — regenerate with it using the same prompt
        print()
        print("Regenerating with your feedback...")
        feedback_bundle = (
            bundle
            + f"\n\n---\nUser feedback on previous report (please revise accordingly):\n{answer}\n"
            + f"\nPrevious report (revise this):\n{report_md}\n"
        )
        report_md = build_test_report(llm, feedback_bundle, issue_type=issue_type)
```

- [ ] **Step 2: Extract `issue_type` in `main()` and pass it to `_review_loop`**

In `main()`, after the line `summary = str(fields.get("summary") or "")`, add:

```python
    issue_type = str((fields.get("issuetype") or {}).get("name") or "")
```

Then find the existing call to `_review_loop`:

```python
    report_md = _review_loop(args.issue_key, summary, bundle, llm, no_confirm=args.yes)
```

Replace it with:

```python
    report_md = _review_loop(args.issue_key, summary, bundle, llm, issue_type, no_confirm=args.yes)
```

- [ ] **Step 3: Verify the module loads cleanly**

```bash
cd "/Users/kiran.jadhav/Test Agent/test-Agent"
PYTHONPATH=. python3 -c "from jira_qa_agent.cli import main; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Run all tests**

```bash
PYTHONPATH=. python3 -m pytest tests/ -v
```

Expected: 31 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add jira_qa_agent/cli.py
git commit -m "feat: pass issue type to prompt selector in cli review loop"
```

---

## Task 4: Smoke-test end-to-end with a real ticket

**This task has no automated test — it verifies the real integration.**

- [ ] **Step 1: Run on a Bug ticket and confirm Bug prompt is active**

```bash
cd "/Users/kiran.jadhav/Test Agent/test-Agent"
PYTHONPATH=. python3 -m jira_qa_agent HOST-7564 --yes 2>&1 | head -10
```

Expected header:
```
  GENERATED TEST REPORT — HOST-7564: ...
  Issue type: Bug
```

And the report should lead with a reproduce TC, not a creation flow.

- [ ] **Step 2: Run on a Feature ticket and confirm Feature prompt is active**

```bash
PYTHONPATH=. python3 -m jira_qa_agent SOFT-186442 --yes 2>&1 | head -10
```

Expected header:
```
  Issue type: Feature
```

- [ ] **Step 3: Commit any fixups if needed**

```bash
git add -A && git commit -m "fix: smoke-test fixups for issue-type-aware prompts"
```

(Skip if no changes were needed.)
