# jira-qa-agent

CLI that turns a Jira ticket + its linked Bitbucket PR(s) into a QA test plan,
then posts the plan back as a comment on the ticket.

## What it does

1. Fetches the Jira issue (summary, description, comments).
2. Discovers linked Bitbucket pull requests via, in order:
   - `--pr` flag (manual override)
   - Jira Development panel (`dev-status` API) + remote links
   - Regex scan of ticket text
3. Pulls the unified diff for the selected PR(s) from Bitbucket Cloud or Data Center.
4. Sends the bundle (ticket + diff) to an OpenAI chat model using a per-issue-type
   system prompt (Bug / Feature / Story / Task / default).
5. If **exactly one** PR is linked (or you pass a single `--pr`), the report is posted
   to Jira **without** a confirmation prompt. With **multiple** PRs, you pick which
   PRs to analyse, then review the report (`y` / `n` / feedback) before posting — unless
   you pass `--yes` to post immediately. Use `--review` to always show the confirmation
   step even for a single PR.
6. Renders the test cases as a full-width ADF table and posts the comment to Jira.

## Install

```bash
pip install -r requirements.txt
```

For development (tests, lint):

```bash
pip install -r requirements-dev.txt
```

Or, if you prefer editable installs with packaging metadata:

```bash
pip install -e ".[dev]"
```

## Configure

The CLI reads from environment variables (a local `.env` is auto-loaded if present).

| Variable | Required | Purpose |
| --- | --- | --- |
| `JIRA_HOST` | yes | e.g. `https://your-domain.atlassian.net` |
| `JIRA_EMAIL` | yes | Atlassian account email |
| `JIRA_API_TOKEN` | yes | Atlassian API token |
| `BITBUCKET_USERNAME` + `BITBUCKET_APP_PASSWORD` | one of these pairs | Basic auth (preferred for DC/Server) |
| `BITBUCKET_ACCESS_TOKEN` | one of these pairs | Bearer token (fallback) |
| `BITBUCKET_SERVER_URL` | for DC/Server | e.g. `https://stash.company.com` — enables short-form `PROJECT/repo#123` refs |
| `OPENAI_API_KEY` | yes | Used by `langchain-openai` |
| `OPENAI_MODEL` | no | Defaults to `gpt-4o-mini` |
| `JIRA_QA_MAX_DIFF_CHARS` | no | Per-PR diff char cap. Default `120000` |

## Use

```bash
python -m jira_qa_agent PROJ-123
```

Manual PR override (Cloud, DC, or full URL):

```bash
python -m jira_qa_agent PROJ-123 --pr workspace/repo#123
python -m jira_qa_agent PROJ-123 --pr PROJECT/repo#123              # DC if BITBUCKET_SERVER_URL is set
python -m jira_qa_agent PROJ-123 --pr https://stash.x.com/projects/P/repos/r/pull-requests/9
```

Single linked PR posts automatically (no prompt). Multiple PRs: pick PRs, then review before posting.

Always show the review prompt (even with one PR):

```bash
python -m jira_qa_agent PROJ-123 --review
```

Skip the interactive review for any ticket (e.g. multiple PRs after you picked them):

```bash
python -m jira_qa_agent PROJ-123 --yes
```

Generate and inspect the ADF payload without posting:

```bash
python -m jira_qa_agent PROJ-123 --dry-run
```

If installed via `pip install -e .`, a `jira-qa` console script is available:

```bash
jira-qa PROJ-123
```

## Project layout

```
jira_qa_agent/
  cli.py            argparse entry, PR discovery, multi-PR picker, review loop
  config.py         env-var settings + auth validation
  jira_client.py    httpx wrapper for Jira REST API v3
  bitbucket_pr.py   PR ref parsing + diff fetch (Cloud + DC/Server)
  analyze.py        per-issue-type system prompts + build_test_report()
  adf.py            Markdown → Atlassian Document Format (incl. TC table)

tests/              pytest suite
```

## Running tests

```bash
python3 -m pytest -q
```
