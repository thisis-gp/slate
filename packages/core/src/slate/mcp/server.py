from __future__ import annotations
import asyncio
import json
from pathlib import Path
import aiosqlite
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp import types
from slate.db.schema import apply_schema
from slate.mcp import tools

DB_PATH = Path.home() / ".slate" / "db.sqlite"
server = Server("slate")


async def _get_db() -> aiosqlite.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    await apply_schema(db)
    return db


@server.list_tools()
async def list_tools() -> list[types.Tool]:
    return [
        types.Tool(
            name="create_project",
            description="Create a new project in Slate",
            inputSchema={"type": "object", "required": ["name"],
                         "properties": {"name": {"type": "string"},
                                        "description": {"type": "string"},
                                        "key": {"type": "string", "description": "Short uppercase project key e.g. BX"}}}
        ),
        types.Tool(
            name="create_task",
            description="Create a new task and assign it to an agent",
            inputSchema={"type": "object", "required": ["project_id", "title"],
                         "properties": {
                             "project_id": {"type": "string"},
                             "title": {"type": "string"},
                             "description": {"type": "string"},
                             "type": {"type": "string",
                                      "enum": ["feature","bug","research","chore","spike"]},
                             "priority": {"type": "string",
                                          "enum": ["low","medium","high","critical"]},
                             "created_by": {"type": "string"},
                             "assigned_to": {"type": "string"},
                             "reporter": {"type": "string"},
                             "parent_task_id": {"type": "string"},
                             "story_points": {"type": "integer", "enum": [1, 2, 3, 5, 8, 13]},
                             "labels": {"type": "string", "description": "JSON array string e.g. [\"auth\",\"backend\"]"},
                             "links": {"type": "string", "description": "JSON array string e.g. [{\"url\":\"...\",\"label\":\"...\",\"type\":\"doc\"}]"}}}
        ),
        types.Tool(
            name="update_task_state",
            description="Move a task to a new state and optionally reassign it",
            inputSchema={"type": "object",
                         "required": ["task_id", "to_state", "changed_by"],
                         "properties": {
                             "task_id": {"type": "string"},
                             "to_state": {"type": "string",
                                          "enum": ["todo","in_progress","code_review","qa",
                                                   "ready_to_merge","done","blocked",
                                                   "on_hold","cancelled"]},
                             "changed_by": {"type": "string"},
                             "reason": {"type": "string"},
                             "new_assignee": {"type": "string"}}}
        ),
        types.Tool(
            name="log_agent_run",
            description="Log what this agent did on a task",
            inputSchema={"type": "object",
                         "required": ["task_id", "agent_name", "tool", "summary"],
                         "properties": {
                             "task_id": {"type": "string"},
                             "agent_name": {"type": "string"},
                             "tool": {"type": "string"},
                             "summary": {"type": "string"},
                             "outcome": {"type": "string"},
                             "status": {"type": "string"},
                             "cost_usd": {"type": "number"},
                             "session_id": {"type": "string"},
                             "commit_sha": {"type": "string", "description": "Full or short git commit SHA"},
                             "commit_message": {"type": "string", "description": "Git commit message"}}}
        ),
        types.Tool(
            name="get_task_context",
            description="Get full task context: state, all agent runs, transitions. Use to resume a task.",
            inputSchema={"type": "object", "required": ["task_id"],
                         "properties": {"task_id": {"type": "string"}}}
        ),
        types.Tool(
            name="list_tasks",
            description="List tasks, optionally filtered by project, state, or assignee",
            inputSchema={"type": "object",
                         "properties": {
                             "project_id": {"type": "string"},
                             "state": {"type": "string"},
                             "assigned_to": {"type": "string"}}}
        ),
        types.Tool(
            name="add_comment",
            description="Add a comment to a task — use for notes, status updates, review feedback",
            inputSchema={"type": "object", "required": ["task_id", "author", "body"],
                         "properties": {
                             "task_id": {"type": "string"},
                             "author": {"type": "string"},
                             "body": {"type": "string"},
                             "author_type": {"type": "string", "enum": ["agent", "human"]}}}
        ),
        types.Tool(
            name="daily_sync",
            description="Get daily sync report: what agents did today and total cost",
            inputSchema={"type": "object",
                         "properties": {"date_str": {"type": "string",
                                                     "description": "YYYY-MM-DD, defaults to today"}}}
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
    db = await _get_db()
    try:
        if name == "create_project":
            result = await tools.create_project(db, **arguments)
        elif name == "create_task":
            result = await tools.create_task(db, **arguments)
        elif name == "update_task_state":
            result = await tools.update_task_state(db, **arguments)
        elif name == "log_agent_run":
            result = await tools.log_agent_run(db, **arguments)
        elif name == "get_task_context":
            result = await tools.get_task_context(db, arguments["task_id"])
        elif name == "list_tasks":
            result = await tools.list_tasks_tool(db, **arguments)
        elif name == "add_comment":
            result = await tools.add_comment_tool(db, **arguments)
        elif name == "daily_sync":
            result = await tools.daily_sync_tool(db, **arguments)
        else:
            result = {"error": f"Unknown tool: {name}"}
    finally:
        await db.close()
    return [types.TextContent(type="text", text=json.dumps(result, indent=2, default=str))]


async def main() -> None:
    async with stdio_server() as streams:
        await server.run(streams[0], streams[1],
                         server.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
