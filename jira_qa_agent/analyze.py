from __future__ import annotations

import re

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

# ---------------------------------------------------------------------------
# Shared TC template injected into every prompt
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
# Default prompt — Sub-task, unknown type, or fallback
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
    if not re.match(r"^##\s", t):
        t = "## Overview\n" + t
    parts = re.split(r"\n(?=##\s)", t)
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
        title, _, body = rest.partition("\n")
        out.append((title.strip(), body.strip()))
    return out
