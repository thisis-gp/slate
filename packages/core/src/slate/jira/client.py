from __future__ import annotations
import base64
from dataclasses import dataclass
import httpx


def _adf_comment(text: str) -> dict:
    return {
        "type": "doc",
        "version": 1,
        "content": [
            {
                "type": "paragraph",
                "content": [{"type": "text", "text": text}],
            }
        ],
    }


@dataclass
class JiraClient:
    base_url: str
    email: str
    api_token: str

    def _auth_header(self) -> str:
        creds = base64.b64encode(f"{self.email}:{self.api_token}".encode()).decode()
        return f"Basic {creds}"

    def _headers(self, content_type: str = "") -> dict:
        h = {"Authorization": self._auth_header(), "Accept": "application/json"}
        if content_type:
            h["Content-Type"] = content_type
        return h

    async def get_issue(self, key: str) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.base_url}/rest/api/3/issue/{key}",
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json()

    async def search_issues(self, jql: str, *, max_results: int = 100,
                            fields: list[str] | None = None) -> list[dict]:
        """Search issues via JQL. Returns the raw issue dicts (key + fields)."""
        flds = fields or ["summary", "status", "issuetype", "priority", "assignee"]
        issues: list[dict] = []
        start_at = 0
        async with httpx.AsyncClient() as client:
            while True:
                r = await client.post(
                    f"{self.base_url}/rest/api/3/search",
                    headers=self._headers("application/json"),
                    json={"jql": jql, "startAt": start_at,
                          "maxResults": max_results, "fields": flds},
                )
                r.raise_for_status()
                data = r.json()
                batch = data.get("issues", [])
                issues.extend(batch)
                start_at += len(batch)
                if start_at >= data.get("total", 0) or not batch:
                    break
        return issues

    async def get_transitions(self, key: str) -> list[dict]:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{self.base_url}/rest/api/3/issue/{key}/transitions",
                headers=self._headers(),
            )
            r.raise_for_status()
            return r.json().get("transitions", [])

    async def transition_issue(self, key: str, transition_id: str) -> None:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self.base_url}/rest/api/3/issue/{key}/transitions",
                headers=self._headers("application/json"),
                json={"transition": {"id": transition_id}},
            )
            r.raise_for_status()

    async def add_worklog(
        self, key: str, *, time_spent_seconds: int, comment: str, started: str
    ) -> dict:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{self.base_url}/rest/api/3/issue/{key}/worklog",
                headers=self._headers("application/json"),
                json={
                    "timeSpentSeconds": max(60, time_spent_seconds),
                    "comment": _adf_comment(comment),
                    "started": started,
                },
            )
            r.raise_for_status()
            return r.json()
