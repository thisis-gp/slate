from __future__ import annotations
import uuid
from datetime import date
import aiosqlite
from slate.db import queries as q


async def create_project(db: aiosqlite.Connection, *, name: str,
                          description: str = "", key: str = "") -> dict:
    pid = str(uuid.uuid4())
    await q.insert_project(db, id=pid, name=name, description=description, key=key)
    return await q.get_project(db, pid)


async def create_task(db: aiosqlite.Connection, *, project_id: str, title: str,
                       description: str = "", type: str = "feature",
                       priority: str = "medium", created_by: str = "agent",
                       assigned_to: str = "", reporter: str = "",
                       parent_task_id: str = "", story_points: int = 0,
                       labels: str = "", links: str = "") -> dict:
    tid = str(uuid.uuid4())
    await q.insert_task(db, id=tid, project_id=project_id, title=title,
                         description=description, type=type, priority=priority,
                         created_by=created_by, assigned_to=assigned_to,
                         reporter=reporter, parent_task_id=parent_task_id,
                         story_points=story_points, labels=labels, links=links)
    return await q.get_task(db, tid)


async def update_task_state(db: aiosqlite.Connection, *, task_id: str,
                             to_state: str, changed_by: str,
                             reason: str = "", new_assignee: str = "") -> dict:
    await q.update_task_state(db, task_id=task_id, to_state=to_state,
                               changed_by=changed_by, reason=reason,
                               new_assignee=new_assignee)
    return await q.get_task(db, task_id)


async def log_agent_run(db: aiosqlite.Connection, *, task_id: str, agent_name: str,
                         tool: str, summary: str, outcome: str = "",
                         status: str = "completed", cost_usd: float = 0.0,
                         session_id: str = "", commit_sha: str = "",
                         commit_message: str = "") -> dict:
    rid = str(uuid.uuid4())
    await q.insert_agent_run(db, id=rid, task_id=task_id, agent_name=agent_name,
                              tool=tool, summary=summary, outcome=outcome,
                              status=status, cost_usd=cost_usd, session_id=session_id,
                              commit_sha=commit_sha, commit_message=commit_message)
    return {"id": rid, "task_id": task_id, "agent_name": agent_name,
            "tool": tool, "summary": summary, "status": status,
            "commit_sha": commit_sha or None}


async def get_task_context(db: aiosqlite.Connection, task_id: str) -> dict:
    return await q.get_task_context(db, task_id)


async def list_tasks_tool(db: aiosqlite.Connection, project_id: str = "",
                           state: str = "", assigned_to: str = "") -> list[dict]:
    return await q.list_tasks(db, project_id=project_id, state=state,
                               assigned_to=assigned_to)


async def daily_sync_tool(db: aiosqlite.Connection, date_str: str = "") -> dict:
    d = date_str or date.today().isoformat()
    return await q.get_daily_sync(db, d)


async def add_comment_tool(db: aiosqlite.Connection, *, task_id: str, author: str,
                            body: str, author_type: str = "agent") -> dict:
    return await q.add_comment(db, task_id=task_id, author=author,
                                body=body, author_type=author_type)
