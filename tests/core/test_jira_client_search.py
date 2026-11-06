"""HTTP-level test for JiraClient.search_issues.

Guards against the regression found in a live dry-run: the old
``/rest/api/3/search`` endpoint was removed by Atlassian (410 Gone). These tests
mock the transport (not the method) so they assert the actual URL and the
token-based pagination of the enhanced ``/rest/api/3/search/jql`` endpoint.
"""
import httpx
import pytest
from slate.jira.client import JiraClient


def _client_with(handler):
    transport = httpx.MockTransport(handler)
    c = JiraClient(base_url="https://x.atlassian.net", email="a@b.com", api_token="t")
    # Patch httpx.AsyncClient so the client uses our mock transport.
    import slate.jira.client as mod
    orig = mod.httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = transport
        return orig(*args, **kwargs)

    mod.httpx.AsyncClient = factory
    return c, lambda: setattr(mod.httpx, "AsyncClient", orig)


async def test_uses_enhanced_endpoint(monkeypatch):
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"issues": [{"key": "BX-1"}], "isLast": True})

    c, restore = _client_with(handler)
    try:
        issues = await c.search_issues("assignee = currentUser()")
    finally:
        restore()
    assert seen["url"].endswith("/rest/api/3/search/jql")
    assert "/rest/api/3/search?" not in seen["url"]
    assert [i["key"] for i in issues] == ["BX-1"]


async def test_token_pagination_follows_next_page(monkeypatch):
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        import json as _json
        body = _json.loads(request.content)
        calls.append(body.get("nextPageToken"))
        if not body.get("nextPageToken"):
            return httpx.Response(200, json={
                "issues": [{"key": "BX-1"}], "nextPageToken": "tok2", "isLast": False})
        return httpx.Response(200, json={"issues": [{"key": "BX-2"}], "isLast": True})

    c, restore = _client_with(handler)
    try:
        issues = await c.search_issues("x")
    finally:
        restore()
    assert [i["key"] for i in issues] == ["BX-1", "BX-2"]
    assert calls == [None, "tok2"]  # first page no token, second follows it


async def test_stops_when_no_token_and_not_islast():
    def handler(request: httpx.Request) -> httpx.Response:
        # No nextPageToken and isLast missing → must still terminate.
        return httpx.Response(200, json={"issues": [{"key": "BX-9"}]})

    c, restore = _client_with(handler)
    try:
        issues = await c.search_issues("x")
    finally:
        restore()
    assert [i["key"] for i in issues] == ["BX-9"]
