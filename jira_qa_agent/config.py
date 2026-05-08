from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    jira_host: str
    jira_email: str
    jira_token: str
    bitbucket_username: str | None
    bitbucket_app_password: str | None
    bitbucket_access_token: str | None
    # If set (e.g. https://stash.company.com), short PR refs KEY/repo#num use Server/Data Center API.
    bitbucket_server_base_url: str | None
    openai_model: str
    max_diff_chars: int


def load_settings() -> Settings:
    host = (os.environ.get("JIRA_HOST") or "").rstrip("/")
    if not host:
        raise SystemExit("JIRA_HOST is required (e.g. https://your-domain.atlassian.net)")

    user = _strip_or_none("BITBUCKET_USERNAME")
    app_pw = _strip_or_none("BITBUCKET_APP_PASSWORD")
    bearer = _strip_or_none("BITBUCKET_ACCESS_TOKEN")

    # Prefer Basic auth (username + password/app-password) — more reliable on Bitbucket DC/Server.
    # Fall back to Bearer only when Basic credentials are not provided.
    if user and app_pw:
        bb_user, bb_pw = user, app_pw
        bearer = None
    elif bearer:
        bb_user, bb_pw = None, None
    else:
        raise SystemExit(
            "Bitbucket auth: set BITBUCKET_USERNAME + BITBUCKET_APP_PASSWORD, or BITBUCKET_ACCESS_TOKEN"
        )

    return Settings(
        jira_host=host,
        jira_email=_need("JIRA_EMAIL"),
        jira_token=_need("JIRA_API_TOKEN"),
        bitbucket_username=bb_user,
        bitbucket_app_password=bb_pw,
        bitbucket_access_token=bearer,
        bitbucket_server_base_url=_strip_or_none("BITBUCKET_SERVER_URL"),
        openai_model=(os.environ.get("OPENAI_MODEL") or "gpt-4.1").strip(),
        max_diff_chars=int(os.environ.get("JIRA_QA_MAX_DIFF_CHARS", "120000")),
    )


def _need(name: str) -> str:
    v = (os.environ.get(name) or "").strip()
    if not v:
        raise SystemExit(f"{name} is required")
    return v


def _strip_or_none(key: str) -> str | None:
    v = os.environ.get(key)
    if v is None:
        return None
    s = str(v).strip()
    return s if s else None
