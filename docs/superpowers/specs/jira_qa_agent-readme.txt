jira_qa_agent — inline execution (Bitbucket PR)

Setup
-----
From repository root:

  python3 -m pip install -r docs/superpowers/specs/requirements.txt

Copy docs/superpowers/specs/.env.example to docs/superpowers/specs/.env and set:

  OPENAI_API_KEY        — required for LLM
  JIRA_HOST             — https://YOUR.atlassian.net
  JIRA_EMAIL            — Atlassian account email
  JIRA_API_TOKEN        — from https://id.atlassian.com/manage-profile/security/api-tokens

Bitbucket — Cloud OR Data Center / Server

Cloud (bitbucket.org):

  BITBUCKET_USERNAME + BITBUCKET_APP_PASSWORD  — App Password from Bitbucket Cloud settings
  OR
  BITBUCKET_ACCESS_TOKEN                       — Bearer token if supported

Data Center / Server (e.g. stash.company.com):

  BITBUCKET_SERVER_URL=https://stash.company.com

For DC, short PR form is PROJECT_KEY/repo-slug#123 (not Cloud “workspace”). Or paste full URL:

  https://stash.company.com/projects/PROJ/repos/repo-slug/pull-requests/123

Use Bitbucket account username + HTTP access token / app password as Basic auth (your admin may issue PAT).

Optional: JIRA_QA_MAX_DIFF_CHARS (default 120000)

Run
---

Always set PYTHONPATH to the repo root so package `jira_qa_agent` resolves:

  cd /path/to/test-Agent
  PYTHONPATH=. python3 -m jira_qa_agent PROJ-123 --dry-run

With explicit PR — Cloud: workspace/repo#42; DC (with BITBUCKET_SERVER_URL): PROJECT_KEY/repo-slug#42:

  PYTHONPATH=. python3 -m jira_qa_agent PROJ-123 --pr MYPROJ/my-repo#42 --dry-run

Post the generated test-case report as a Jira comment (same env; removes --dry-run):

  PYTHONPATH=. python3 -m jira_qa_agent PROJ-123 --pr MYPROJ/my-repo#42

PR detection
------------
If you omit --pr, the tool searches the ticket summary, description, and comments for:

  - Bitbucket Cloud or DC pull-request URLs
  - Short form workspace/repo#123 (Cloud) or PROJECT/repo#123 when BITBUCKET_SERVER_URL is set (DC)

Notes
-----
- **Bitbucket Cloud** uses `api.bitbucket.org`. **Bitbucket Data Center / Server** uses your host (`BITBUCKET_SERVER_URL`) and REST `/rest/api/latest/...`.
- Large PR diffs are truncated per JIRA_QA_MAX_DIFF_CHARS.
- Do not commit `.env`; keep tokens out of git.
