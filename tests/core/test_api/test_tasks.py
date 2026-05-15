import pytest

@pytest.mark.asyncio
async def test_create_and_list_project(client):
    r = await client.post("/projects", json={"name": "my-app"})
    assert r.status_code == 201
    pid = r.json()["id"]
    r2 = await client.get("/projects")
    assert r2.status_code == 200
    assert any(p["id"] == pid for p in r2.json())

@pytest.mark.asyncio
async def test_create_project_missing_name(client):
    r = await client.post("/projects", json={})
    assert r.status_code == 422

@pytest.mark.asyncio
async def test_create_task_and_move_state(client):
    r = await client.post("/projects", json={"name": "proj"})
    pid = r.json()["id"]
    r2 = await client.post("/tasks", json={
        "project_id": pid, "title": "Fix bug", "type": "bug", "created_by": "human"
    })
    assert r2.status_code == 201
    tid = r2.json()["id"]
    assert r2.json()["state"] == "todo"
    r3 = await client.post(f"/tasks/{tid}/move",
                           json={"to_state": "investigating", "changed_by": "claude"})
    assert r3.status_code == 200
    assert r3.json()["state"] == "investigating"

@pytest.mark.asyncio
async def test_task_context(client):
    r = await client.post("/projects", json={"name": "ctx-proj"})
    pid = r.json()["id"]
    r2 = await client.post("/tasks", json={"project_id": pid, "title": "Research task", "created_by": "human"})
    tid = r2.json()["id"]
    r3 = await client.get(f"/tasks/{tid}/context")
    assert r3.status_code == 200
    ctx = r3.json()
    assert ctx["task"]["id"] == tid
    assert "runs" in ctx
    assert "transitions" in ctx

@pytest.mark.asyncio
async def test_log_run(client):
    r = await client.post("/projects", json={"name": "run-proj"})
    pid = r.json()["id"]
    r2 = await client.post("/tasks", json={"project_id": pid, "title": "Do work", "created_by": "human"})
    tid = r2.json()["id"]
    r3 = await client.post("/runs", json={
        "task_id": tid, "agent_name": "claude", "tool": "claude-code",
        "summary": "Implemented the feature"
    })
    assert r3.status_code == 201

@pytest.mark.asyncio
async def test_approval_flow(client):
    r = await client.post("/projects", json={"name": "appr-proj"})
    pid = r.json()["id"]
    r2 = await client.post("/tasks", json={"project_id": pid, "title": "Deploy", "created_by": "human"})
    tid = r2.json()["id"]
    r3 = await client.post("/approvals", json={
        "task_id": tid, "requested_by": "orchestrator", "reason": "Ready to deploy?"
    })
    assert r3.status_code == 201
    aid = r3.json()["id"]
    r4 = await client.get("/approvals?status=pending")
    assert any(a["id"] == aid for a in r4.json())
    r5 = await client.post(f"/approvals/{aid}/respond", json={"status": "approved"})
    assert r5.status_code == 200

@pytest.mark.asyncio
async def test_sync_daily(client):
    r = await client.get("/sync/daily")
    assert r.status_code == 200
    data = r.json()
    assert "runs" in data
    assert "sessions" in data
    assert "total_cost_usd" in data
