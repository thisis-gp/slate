from __future__ import annotations
import uuid
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from slate.db.queries import (
    insert_sprint, get_sprint, list_sprints,
    update_sprint_status, assign_task_to_sprint, get_sprint_tasks,
)

router = APIRouter(tags=["sprints"])

class CreateSprintRequest(BaseModel):
    project_id: str
    name: str
    goal: str = ""
    start_date: str = ""
    end_date: str = ""

@router.post("/sprints", status_code=201)
async def create_sprint(body: CreateSprintRequest, request: Request):
    sid = str(uuid.uuid4())
    await insert_sprint(request.app.state.db, id=sid, **body.model_dump())
    sprint = await get_sprint(request.app.state.db, sid)
    if not sprint:
        raise HTTPException(status_code=500, detail="Sprint creation failed")
    return sprint

@router.get("/sprints")
async def get_sprints(request: Request, project_id: str = "", status: str = ""):
    return await list_sprints(request.app.state.db, project_id=project_id, status=status)

@router.get("/sprints/{sprint_id}")
async def get_sprint_by_id(sprint_id: str, request: Request):
    sprint = await get_sprint(request.app.state.db, sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    tasks = await get_sprint_tasks(request.app.state.db, sprint_id)
    return {**sprint, "tasks": tasks}

@router.post("/sprints/{sprint_id}/start")
async def start_sprint(sprint_id: str, request: Request):
    sprint = await get_sprint(request.app.state.db, sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    await update_sprint_status(request.app.state.db, sprint_id, "active")
    return await get_sprint(request.app.state.db, sprint_id)

@router.post("/sprints/{sprint_id}/complete")
async def complete_sprint(sprint_id: str, request: Request):
    sprint = await get_sprint(request.app.state.db, sprint_id)
    if not sprint:
        raise HTTPException(status_code=404, detail="Sprint not found")
    await update_sprint_status(request.app.state.db, sprint_id, "completed")
    return await get_sprint(request.app.state.db, sprint_id)

@router.post("/sprints/{sprint_id}/assign/{task_id}")
async def assign_task(sprint_id: str, task_id: str, request: Request):
    await assign_task_to_sprint(request.app.state.db, task_id=task_id, sprint_id=sprint_id)
    return {"ok": True}
