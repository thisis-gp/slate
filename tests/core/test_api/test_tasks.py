import pytest


@pytest.mark.asyncio
async def test_create_task(client):
    resp = await client.post("/tasks", json={"prompt": "fix the login bug"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["prompt"] == "fix the login bug"
    assert data["status"] == "pending"
    assert "id" in data


@pytest.mark.asyncio
async def test_get_task(client):
    create_resp = await client.post("/tasks", json={"prompt": "write tests"})
    task_id = create_resp.json()["id"]
    get_resp = await client.get(f"/tasks/{task_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["id"] == task_id


@pytest.mark.asyncio
async def test_get_nonexistent_task_returns_404(client):
    resp = await client.get("/tasks/nonexistent-id")
    assert resp.status_code == 404
