from __future__ import annotations
import uuid
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from slate.db.queries import insert_project, get_project, list_projects

router = APIRouter(tags=["projects"])

class CreateProjectRequest(BaseModel):
    name: str
    description: str = ""
    key: str = ""   # short uppercase identifier, e.g. "BX"

@router.post("/projects", status_code=201)
async def create_project(body: CreateProjectRequest, request: Request):
    pid = str(uuid.uuid4())
    await insert_project(request.app.state.db, id=pid,
                          name=body.name, description=body.description,
                          key=body.key)
    return await get_project(request.app.state.db, pid)

@router.get("/projects")
async def get_projects(request: Request):
    return await list_projects(request.app.state.db)

@router.get("/projects/{project_id}")
async def get_project_by_id(project_id: str, request: Request):
    p = await get_project(request.app.state.db, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p
