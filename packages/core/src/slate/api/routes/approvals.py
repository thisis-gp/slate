from __future__ import annotations
import uuid
from fastapi import APIRouter, Request
from pydantic import BaseModel
from slate.db.queries import insert_approval, respond_approval, list_approvals

router = APIRouter(tags=["approvals"])

class RequestApprovalRequest(BaseModel):
    task_id: str = ""
    requested_by: str
    reason: str
    context: str = ""

class RespondApprovalRequest(BaseModel):
    status: str
    response_note: str = ""

@router.post("/approvals", status_code=201)
async def request_approval(body: RequestApprovalRequest, request: Request):
    aid = str(uuid.uuid4())
    await insert_approval(request.app.state.db, id=aid, **body.model_dump())
    return {"id": aid, **body.model_dump(), "status": "pending"}

@router.get("/approvals")
async def get_approvals(request: Request, status: str = "pending"):
    return await list_approvals(request.app.state.db, status=status)

@router.post("/approvals/{approval_id}/respond")
async def respond(approval_id: str, body: RespondApprovalRequest, request: Request):
    await respond_approval(request.app.state.db, approval_id=approval_id,
                            status=body.status, response_note=body.response_note)
    return {"id": approval_id, "status": body.status}
