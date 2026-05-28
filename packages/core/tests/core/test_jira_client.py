import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch
from slate.jira.client import JiraClient


def make_client():
    return JiraClient(
        base_url="https://myorg.atlassian.net",
        email="dev@myorg.com",
        api_token="secret",
    )


def mock_response(status_code: int, body: dict):
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = body
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        from httpx import HTTPStatusError
        resp.raise_for_status.side_effect = HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


@pytest.mark.asyncio
async def test_get_issue_returns_parsed_json():
    client = make_client()
    fake_issue = {"id": "10001", "key": "PROJ-42", "fields": {"status": {"name": "To Do"}}}
    mock_get = AsyncMock(return_value=mock_response(200, fake_issue))
    with patch("httpx.AsyncClient.get", mock_get):
        result = await client.get_issue("PROJ-42")
    assert result["key"] == "PROJ-42"
    mock_get.assert_called_once()
    call_url = mock_get.call_args[0][0]
    assert "PROJ-42" in call_url


@pytest.mark.asyncio
async def test_get_transitions_returns_list():
    client = make_client()
    fake = {"transitions": [
        {"id": "11", "name": "Start Progress", "to": {"name": "In Progress"}},
        {"id": "21", "name": "Done", "to": {"name": "Done"}},
    ]}
    mock_get = AsyncMock(return_value=mock_response(200, fake))
    with patch("httpx.AsyncClient.get", mock_get):
        result = await client.get_transitions("PROJ-42")
    assert len(result) == 2
    assert result[0]["id"] == "11"


@pytest.mark.asyncio
async def test_transition_issue_posts_correct_payload():
    client = make_client()
    mock_post = AsyncMock(return_value=mock_response(204, {}))
    with patch("httpx.AsyncClient.post", mock_post):
        await client.transition_issue("PROJ-42", "21")
    payload = mock_post.call_args[1]["json"]
    assert payload == {"transition": {"id": "21"}}


@pytest.mark.asyncio
async def test_add_worklog_sends_correct_fields():
    client = make_client()
    mock_post = AsyncMock(return_value=mock_response(201, {"id": "10100"}))
    with patch("httpx.AsyncClient.post", mock_post):
        result = await client.add_worklog(
            "PROJ-42",
            time_spent_seconds=3600,
            comment="claude-code: fixed auth bug",
            started="2026-05-28T09:00:00.000+0000",
        )
    payload = mock_post.call_args[1]["json"]
    assert payload["timeSpentSeconds"] == 3600
    assert payload["started"] == "2026-05-28T09:00:00.000+0000"
    assert "fixed auth bug" in json.dumps(payload["comment"])


@pytest.mark.asyncio
async def test_add_worklog_enforces_minimum_60s():
    client = make_client()
    mock_post = AsyncMock(return_value=mock_response(201, {"id": "10100"}))
    with patch("httpx.AsyncClient.post", mock_post):
        await client.add_worklog(
            "PROJ-42",
            time_spent_seconds=5,
            comment="short run",
            started="2026-05-28T09:00:00.000+0000",
        )
    payload = mock_post.call_args[1]["json"]
    assert payload["timeSpentSeconds"] == 60


@pytest.mark.asyncio
async def test_auth_header_uses_basic_base64():
    import base64
    client = JiraClient(base_url="https://x.atlassian.net", email="a@b.com", api_token="tok")
    header = client._auth_header()
    assert header.startswith("Basic ")
    decoded = base64.b64decode(header[6:]).decode()
    assert decoded == "a@b.com:tok"
