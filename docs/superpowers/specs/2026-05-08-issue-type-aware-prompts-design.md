# Design: Issue-Type-Aware Test Case Generation

**Date:** 2026-05-08  
**Status:** Approved  
**Goal:** Give each Jira issue type (Bug, Feature, Story, Task, Sub-task) a dedicated LLM prompt so the generated test cases match the nature and testing goals of that ticket type.

---

## Problem

The current agent uses a single system prompt for every ticket regardless of type. This produces:
- Bug tickets with happy-path creation flows instead of reproduce/regression tests
- Story tickets with low-level button-click steps instead of user-journey acceptance criteria
- Task and Sub-task tickets with the same deep coverage as full features

---

## Solution: One Prompt Per Issue Type (Approach A)

The agent reads `fields.issuetype.name` from the Jira response (already fetched), selects the matching prompt from a lookup table, and passes it to the LLM. Everything else in the pipeline is unchanged.

---

## Architecture

Only `analyze.py` and `cli.py` change. All other files are untouched.

### `jira_qa_agent/analyze.py`

**Before:** One `SYSTEM` constant, `build_test_report(llm, bundle) -> str`

**After:**

```
SYSTEM_BUG       — prompt for Bug tickets
SYSTEM_FEATURE   — prompt for Feature tickets
SYSTEM_STORY     — prompt for Story tickets
SYSTEM_TASK      — prompt for Task tickets
SYSTEM_DEFAULT   — fallback: Sub-task + any unknown type

_PROMPTS: dict[str, str] = {
    "Bug":     SYSTEM_BUG,
    "Feature": SYSTEM_FEATURE,
    "Story":   SYSTEM_STORY,
    "Task":    SYSTEM_TASK,
}

get_system_prompt(issue_type: str) -> str
    Returns _PROMPTS.get(issue_type, SYSTEM_DEFAULT)

build_test_report(llm, bundle, issue_type: str = "") -> str
    Calls get_system_prompt(issue_type), passes result as SystemMessage
```

The old `SYSTEM` constant is removed. `build_test_report` gains one new optional parameter with a safe default so existing callers (e.g. tests) don't break.

### `jira_qa_agent/cli.py`

One new line in `main()` to extract the issue type from the already-fetched issue:

```python
issue_type = str((fields.get("issuetype") or {}).get("name") or "")
```

And pass it through to `build_test_report` and `_review_loop`:

```python
report_md = _review_loop(args.issue_key, summary, bundle, llm, issue_type, no_confirm=args.yes)
```

`_review_loop` passes `issue_type` to `build_test_report` on both the initial call and any regeneration calls (so feedback-based regeneration also uses the correct prompt).

---

## Prompt Design Per Type

### Bug

**Focus:** Reproduce the original defect, verify the fix, prevent regression.

**Output sections:** Summary · Preconditions · Test Cases · Risks & Notes

**Test case emphasis:**
- Reproduce steps for the original bug (negative — should have failed before fix)
- Fix verification (positive — now works correctly)
- Regression: does the bug come back under similar conditions?
- Adjacent areas that the fix could have broken

**Minimum counts:** 3 positive · 3 negative · 2 edge · 1 mobile  
**Required TC:** One TC that reproduces the original bug and confirms it no longer occurs.

---

### Feature

**Focus:** Full coverage of new functionality — UI flows, API endpoints, permission checks, integration.

**Output sections:** Summary · Preconditions · Test Cases · Risks & Notes

**Test case emphasis:**
- All new UI elements/actions/API endpoints from the diff
- Happy-path flows for each new capability
- Permission and role checks (who should and shouldn't have access)
- Integration with existing features (does the new thing break the old thing?)

**Minimum counts:** 3 positive · 3 negative · 2 edge · 1 mobile

---

### Story

**Focus:** User journey and business-rule validation. Written for non-technical stakeholders.

**Output sections:** Summary · Preconditions · Test Cases · Risks & Notes

**Test case emphasis:**
- End-to-end user journeys (not individual buttons)
- Written in plain language: "As a user I can… / When I do X, Y happens"
- Business rules and acceptance criteria from the ticket description
- Role/persona-based scenarios

**Minimum counts:** 3 positive journeys · 2 negative (invalid states, missing permissions) · 2 edge · 1 mobile  
**Style:** Steps describe the user goal at each stage, not every individual click.

---

### Task

**Focus:** Technical smoke tests only. Did the change break existing behaviour?

**Output sections:** Summary · Preconditions · Test Cases · Risks & Notes

**Test case emphasis:**
- Smoke tests of the directly affected component
- Regression checks on adjacent functionality
- No deep coverage — the change is infrastructure/technical, not user-facing

**Minimum counts:** 3 smoke tests · 1 regression check  
**Mobile:** Not required.  
**Note in output:** "This is a Task ticket. Test coverage is limited to smoke and regression tests."

---

### Sub-task / Unknown (Default)

**Focus:** Minimal — defers testing responsibility to the parent ticket.

**Output sections:** Summary · Test Cases (max 3)

**Test case emphasis:**
- 1–3 smoke tests confirming this unit of work functions
- A note directing testers to the parent ticket for full coverage

**Maximum:** 3 TCs.  
**Note in output:** "This is a sub-task. Full test coverage belongs on the parent ticket [PARENT-KEY]."

---

## Terminal Output

The report header shown in the terminal gains one line showing the detected type:

```
======================================================================
  GENERATED TEST REPORT — SOFT-186005: <summary>
  Issue type: Feature
======================================================================
```

If the type is not recognised, it shows `Issue type: Unknown (using default prompt)`.

---

## Backward Compatibility

- `build_test_report(llm, bundle)` still works with no `issue_type` argument — defaults to `SYSTEM_DEFAULT`.
- All existing tests pass unchanged.
- No new environment variables or dependencies.

---

## Success Criteria

1. Running the agent on a Bug ticket produces a report that leads with reproduce steps and regression TCs, not creation flows.
2. Running on a Story ticket produces user-journey style TCs in plain language.
3. Running on a Task ticket produces 3–5 smoke tests with a note explaining the limited scope.
4. Running on a Sub-task produces ≤3 TCs with a note deferring to the parent.
5. Running on a Feature ticket produces output identical in quality to today (no regression).
6. Unknown/custom issue types fall back to the default prompt without error.
