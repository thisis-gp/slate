import pytest
from slate.models import (
    Project, Task, TaskState, TaskType, TaskPriority,
    Session, AgentRun, Approval, ApprovalStatus, StateTransition
)

def test_task_state_values():
    assert TaskState.TODO == "todo"
    assert TaskState.INVESTIGATING == "investigating"
    assert TaskState.IMPLEMENTING == "implementing"
    assert TaskState.CODE_REVIEW == "code_review"
    assert TaskState.QA == "qa"
    assert TaskState.READY_TO_MERGE == "ready_to_merge"
    assert TaskState.DONE == "done"
    assert TaskState.BLOCKED == "blocked"
    assert TaskState.CANCELLED == "cancelled"

def test_project_requires_name():
    with pytest.raises(Exception):
        Project(id="p1", name="")

def test_task_defaults():
    t = Task(id="t1", project_id="p1", title="Fix bug", created_by="human")
    assert t.state == TaskState.TODO
    assert t.priority == TaskPriority.MEDIUM
    assert t.type == TaskType.FEATURE

def test_approval_status_values():
    assert ApprovalStatus.PENDING == "pending"
    assert ApprovalStatus.APPROVED == "approved"
    assert ApprovalStatus.REJECTED == "rejected"
