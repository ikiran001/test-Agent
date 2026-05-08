from __future__ import annotations

from typing import Any

import httpx


class JiraClient:
    def __init__(self, host: str, email: str, api_token: str) -> None:
        self._base = f"{host.rstrip('/')}/rest/api/3"
        self._auth = (email, api_token)

    def get_issue(self, key: str) -> dict[str, Any]:
        with httpx.Client(auth=self._auth, timeout=60.0) as c:
            r = c.get(
                f"{self._base}/issue/{key}",
                params={"expand": "renderedFields"},
            )
            r.raise_for_status()
            return r.json()

    def get_comments(self, key: str) -> list[dict[str, Any]]:
        with httpx.Client(auth=self._auth, timeout=60.0) as c:
            r = c.get(f"{self._base}/issue/{key}/comment")
            r.raise_for_status()
            return list(r.json().get("comments") or [])

    def get_remote_links(self, key: str) -> list[dict]:
        """
        Returns all remote links on a Jira issue.
        The Bitbucket app adds a remote link for every PR it associates with the ticket.
        Returns an empty list (not an error) if the endpoint returns 404 or 403.
        """
        with httpx.Client(auth=self._auth, timeout=60.0) as c:
            r = c.get(f"{self._base}/issue/{key}/remotelink")
            if r.status_code in (403, 404):
                return []
            r.raise_for_status()
            return list(r.json() or [])

    def add_comment(self, key: str, adf_body: dict[str, Any]) -> dict[str, Any]:
        payload = {"body": adf_body}
        with httpx.Client(auth=self._auth, timeout=60.0) as c:
            r = c.post(f"{self._base}/issue/{key}/comment", json=payload)
            r.raise_for_status()
            return r.json()
