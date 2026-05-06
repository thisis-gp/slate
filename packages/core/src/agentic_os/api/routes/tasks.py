from __future__ import annotations
import uuid
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from agentic_os.db.queries import insert_task, get_task

router = APIRouter()


class CreateTaskRequest(BaseModel):
    prompt: str


@router.post("/tasks", status_code=201)
async def create_task(body: CreateTaskRequest, request: Request):
    task_id = str(uuid.uuid4())
    db = request.app.state.db
    await insert_task(db, id=task_id, prompt=body.prompt)
    task = await get_task(db, task_id)
    return task


@router.get("/tasks/{task_id}")
async def get_task_by_id(task_id: str, request: Request):
    db = request.app.state.db
    task = await get_task(db, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task
