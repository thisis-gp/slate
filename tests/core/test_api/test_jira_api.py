import pytest


@pytest.mark.asyncio
async def test_jira_configure_and_status(client):
    resp = await client.post("/jira/configure", json={
        "base_url": "https://myorg.atlassian.net",
        "email": "dev@myorg.com",
        "api_token": "secret",
        "sync_time": "09:00",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["sync_time"] == "09:00"

    resp = await client.get("/jira/status")
    assert resp.status_code == 200
    assert resp.json()["base_url"] == "https://myorg.atlassian.net"


@pytest.mark.asyncio
async def test_jira_status_not_configured(client):
    resp = await client.get("/jira/status")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_create_task_with_jira_key(client):
    proj_resp = await client.post("/projects", json={"name": "testproj", "key": "TP"})
    assert proj_resp.status_code == 201
    pid = proj_resp.json()["id"]

    task_resp = await client.post("/tasks", json={
        "project_id": pid,
        "title": "Fix login",
        "jira_issue_key": "TP-100",
    })
    assert task_resp.status_code == 201
    assert task_resp.json()["jira_issue_key"] == "TP-100"
