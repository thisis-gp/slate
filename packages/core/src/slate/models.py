from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, field_validator


class TaskState(str, Enum):
    TODO = "todo"
    INVESTIGATING = "investigating"
    IMPLEMENTING = "implementing"
    CODE_REVIEW = "code_review"
    QA = "qa"
    READY_TO_MERGE = "ready_to_merge"
    DONE = "done"
    BLOCKED = "blocked"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    FEATURE = "feature"
    BUG = "bug"
    RESEARCH = "research"
    CHORE = "chore"
    SPIKE = "spike"


class TaskPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SprintStatus(str, Enum):
    PLANNING = "planning"
    ACTIVE = "active"
    COMPLETED = "completed"


class RunStatus(str, Enum):
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED = "blocked"
    IN_PROGRESS = "in_progress"


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class Project(BaseModel):
    id: str
    name: str
    description: Optional[str] = None
    status: str = "active"
    created_at: Optional[float] = None
    updated_at: Optional[float] = None

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("name cannot be empty")
        return v


class Sprint(BaseModel):
    id: str
    project_id: str
    name: str
    goal: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    status: SprintStatus = SprintStatus.PLANNING
    created_at: Optional[float] = None


class Task(BaseModel):
    id: str
    project_id: str
    parent_task_id: Optional[str] = None
    sprint_id: Optional[str] = None
    title: str
    description: Optional[str] = None
    type: TaskType = TaskType.FEATURE
    state: TaskState = TaskState.TODO
    priority: TaskPriority = TaskPriority.MEDIUM
    created_by: str = "human"
    assigned_to: Optional[str] = None
    created_at: Optional[float] = None
    updated_at: Optional[float] = None


class StateTransition(BaseModel):
    id: Optional[int] = None
    task_id: str
    from_state: Optional[str] = None
    to_state: str
    changed_by: str
    reason: Optional[str] = None
    ts: Optional[float] = None


class Session(BaseModel):
    id: str
    agent_name: str
    tool: Optional[str] = None
    project_id: Optional[str] = None
    date: str
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    summary: Optional[str] = None
    total_cost_usd: float = 0.0


class AgentRun(BaseModel):
    id: str
    task_id: str
    session_id: Optional[str] = None
    agent_name: str
    tool: str
    summary: str
    outcome: Optional[str] = None
    status: RunStatus = RunStatus.COMPLETED
    started_at: Optional[float] = None
    completed_at: Optional[float] = None
    cost_usd: float = 0.0


class ModelUsage(BaseModel):
    id: Optional[int] = None
    agent_run_id: Optional[str] = None
    session_id: Optional[str] = None
    task_id: Optional[str] = None
    model: str
    provider: str
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cost_usd: float = 0.0
    ts: Optional[float] = None


class Comment(BaseModel):
    id: Optional[int] = None
    task_id: str
    author: str
    author_type: str = "human"
    body: str
    ts: Optional[float] = None


class Approval(BaseModel):
    id: str
    task_id: Optional[str] = None
    requested_by: str
    reason: str
    context: Optional[str] = None
    status: ApprovalStatus = ApprovalStatus.PENDING
    response_note: Optional[str] = None
    requested_at: Optional[float] = None
    responded_at: Optional[float] = None
