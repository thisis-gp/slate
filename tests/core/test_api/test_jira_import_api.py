import uuid
from unittest.mock import AsyncMock, patch
import pytest
from slate.db.queries import insert_project, upsert_jira_config
import slate.jira.importer as importer


def _issue(key, summary="Do the thing"):
    return {"key": key, "fields": {"summary": summary,
            "issuetype": {"name": "Task"}, "priority": {"name": "Medium"},
            "status": {"name": "To Do"}}}


async def test_import_stage_and_approve_flow(client, monkeypatch):
    monkeypatch.setenv("JIRA_ALLOWED_PREFIXES", "BX")
    db = client._transport.app.state.db
    await upsert_jira_config(db, base_url="https://x.atlassian.net",
                             email="a@b.com", api_token="t", sync_time="09:00")
    pid = str(uuid.uuid4())
    await insert_project(db, id=pid, name="repo", key="BX")

    with patch.object(importer.JiraClient, "search_issues",
                      new=AsyncMock(return_value=[_issue("BX-11")])):
        r = await client.post("/jira/import", json={})
    assert r.status_code == 200
    assert r.json()["staged_count"] == 1

    r = await client.get("/jira/imports")
    rows = r.json()
    assert len(rows) == 1
    import_id = rows[0]["id"]

    r = await client.post(f"/jira/imports/{import_id}/approve",
                          json={"project_id": pid, "write_obsidian": False})
    assert r.status_code == 200
    body = r.json()
    assert body["jira_key"] == "BX-11"
    assert body["task_id"]

    # queue now empty
    assert await client.get("/jira/imports") and (await client.get("/jira/imports")).json() == []


async def test_import_approve_bad_project_is_400(client, monkeypatch):
    monkeypatch.setenv("JIRA_ALLOWED_PREFIXES", "BX")
    db = client._transport.app.state.db
    await upsert_jira_config(db, base_url="https://x.atlassian.net",
                             email="a@b.com", api_token="t", sync_time="09:00")
    with patch.object(importer.JiraClient, "search_issues",
                      new=AsyncMock(return_value=[_issue("BX-12")])):
        await client.post("/jira/import", json={})
    import_id = (await client.get("/jira/imports")).json()[0]["id"]
    # approving the same import twice -> second is a 400
    await client.post(f"/jira/imports/{import_id}/approve",
                      json={"project_id": "nope", "write_obsidian": False})
    r = await client.post(f"/jira/imports/{import_id}/approve",
                          json={"project_id": "nope", "write_obsidian": False})
    assert r.status_code == 400
