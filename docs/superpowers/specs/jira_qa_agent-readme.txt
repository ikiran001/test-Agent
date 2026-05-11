jira_qa_agent — AI-powered test case generator for Jira tickets

What it does
------------
Given a Jira ticket ID, the agent:
  1. Fetches the ticket (summary, description, comments)
  2. Auto-discovers linked Bitbucket PRs (Jira Development panel → remote links → text scan)
  3. Fetches PR diffs from Bitbucket (Cloud or Data Center)
  4. Sends everything to GPT-4.1 to generate structured test cases
  5. Shows you the report for review, then posts it to Jira as a comment

Setup
-----
From the repository root, install dependencies:

  python3 -m pip install -r requirements.txt

Copy docs/superpowers/specs/.env.example to docs/superpowers/specs/.env and fill in:

  OPENAI_API_KEY        — required for LLM (GPT-4.1)
  JIRA_HOST             — https://YOUR.atlassian.net
  JIRA_EMAIL            — Atlassian account email
  JIRA_API_TOKEN        — from https://id.atlassian.com/manage-profile/security/api-tokens

Bitbucket — Cloud OR Data Center / Server

  Cloud (bitbucket.org):
    BITBUCKET_USERNAME + BITBUCKET_APP_PASSWORD  — App Password from Bitbucket Cloud settings

  Data Center / Server (e.g. stash.company.com):
    BITBUCKET_SERVER_URL=https://stash.company.com
    BITBUCKET_USERNAME + BITBUCKET_APP_PASSWORD  — username + HTTP access token / PAT

Optional:
  OPENAI_MODEL          — default: gpt-4o-mini
  JIRA_QA_MAX_DIFF_CHARS — default: 120000 (per PR; auto-scaled down for multi-PR)

Run
---
Always set PYTHONPATH to the repo root:

  cd /path/to/test-Agent
  PYTHONPATH=. python3 -m jira_qa_agent PROJ-123

With an explicit PR override:

  PYTHONPATH=. python3 -m jira_qa_agent PROJ-123 --pr PROJECT/repo#42

Skip interactive review and post directly to Jira:

  PYTHONPATH=. python3 -m jira_qa_agent PROJ-123 --yes

PR short-form:
  Cloud:  workspace/repo#123
  DC/Server (with BITBUCKET_SERVER_URL set):  PROJECT_KEY/repo-slug#123
  Full URL also accepted (bitbucket.org or stash host)

Multi-PR selection
------------------
If multiple PRs are linked to the ticket, a numbered menu is shown:

  [1]  dc  CL / huapi  #1387
  [2]  dc  CL / huapi  #1409

  Select: single number (1), comma-separated (1,2), or 'all'

When multiple PRs are selected, their diffs are combined into one analysis
and the total diff budget is automatically split (90,000 chars / N PRs) to
stay within LLM token limits.

Issue-type-aware prompts
------------------------
The agent reads the Jira issue type and picks a tailored LLM prompt:

  Bug       — reproduce TC first, fix verification, regression prevention
  Feature   — happy paths, negatives, edge cases, permissions
  Story     — end-to-end user journeys, acceptance criteria
  Task      — smoke tests only (4 TCs), explicit note about scope limit
  Sub-task / Unknown — default full-coverage prompt (9+ TCs)

Interactive review
------------------
The report is always shown before posting. At the prompt:

  [y]        — post to Jira
  [n]        — discard, do not post
  [text]     — type feedback and press Enter to regenerate

The --yes flag bypasses the review and posts immediately.

Notes
-----
- Do NOT commit .env — keep credentials out of git.
- Large PR diffs are truncated to JIRA_QA_MAX_DIFF_CHARS per PR.
- Jira comments are posted in Atlassian Document Format (ADF).
- Bitbucket Cloud uses api.bitbucket.org; DC/Server uses BITBUCKET_SERVER_URL.
