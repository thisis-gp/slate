from __future__ import annotations
import uuid
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from slate.db.queries import insert_task, get_task, list_tasks, update_task_state, get_task_context, add_comment, list_comments

router = APIRouter(tags=["tasks"])

class CreateTaskRequest(BaseModel):
    project_id: str
    title: str
    description: str = ""
    type: str = "feature"
    priority: str = "medium"
    created_by: str = "human"
    reporter: str = ""
    assigned_to: str = ""
    parent_task_id: str = ""
    sprint_id: str = ""
    story_points: int = 0
    labels: str = ""   # JSON array string e.g. '["auth","backend"]'
    links: str = ""    # JSON array string e.g. '[{"url":"...","label":"...","type":"doc"}]'

class MoveTaskRequest(BaseModel):
    to_state: str
    changed_by: str = "human"
    reason: str = ""
    new_assignee: str = ""

class AddCommentRequest(BaseModel):
    author: str
    body: str
    author_type: str = "agent"

@router.post("/tasks", status_code=201)
async def create_task(body: CreateTaskRequest, request: Request):
    tid = str(uuid.uuid4())
    await insert_task(request.app.state.db, id=tid, **body.model_dump())
    return await get_task(request.app.state.db, tid)

@router.get("/tasks")
async def get_tasks(request: Request, project_id: str = "",
                    state: str = "", assigned_to: str = ""):
    return await list_tasks(request.app.state.db, project_id=project_id,
                             state=state, assigned_to=assigned_to)

@router.get("/tasks/{task_id}")
async def get_task_by_id(task_id: str, request: Request):
    t = await get_task(request.app.state.db, task_id)
    if not t:
        raise HTTPException(status_code=404, detail="Task not found")
    return t

@router.post("/tasks/{task_id}/move")
async def move_task(task_id: str, body: MoveTaskRequest, request: Request):
    await update_task_state(request.app.state.db, task_id=task_id,
                             to_state=body.to_state, changed_by=body.changed_by,
                             reason=body.reason, new_assignee=body.new_assignee)
    return await get_task(request.app.state.db, task_id)

@router.get("/tasks/{task_id}/context")
async def task_context(task_id: str, request: Request):
    return await get_task_context(request.app.state.db, task_id)

@router.post("/tasks/{task_id}/comments", status_code=201)
async def create_comment(task_id: str, body: AddCommentRequest, request: Request):
    return await add_comment(request.app.state.db, task_id=task_id,
                              author=body.author, body=body.body,
                              author_type=body.author_type)

@router.get("/tasks/{task_id}/comments")
async def get_comments(task_id: str, request: Request):
    return await list_comments(request.app.state.db, task_id)
