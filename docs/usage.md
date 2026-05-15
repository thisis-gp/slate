# Slate Usage Guide

## CLI

```bash
# Projects
slate project create "my-app" --desc "My application"
slate project list

# Tasks
slate task create "Fix login bug" --project <project-id> --type bug --priority high
slate task list --project <project-id> --state todo
slate task show <task-id>
slate task move <task-id> implementing --by claude-code

# Agent runs
slate run log <task-id> "Investigated the auth flow" --agent claude --tool claude-code

# Sessions
slate session start claude --tool claude-code --project <project-id>
slate session end <session-id> --summary "Implemented JWT" --cost 0.12

# Approvals
slate approve list
slate approve approve <approval-id>
slate approve reject <approval-id> --note "Not ready"

# Sync reports
slate sync daily
slate sync weekly
```

## HTTP API

Start the server:
```bash
uvicorn slate.api.app:create_app --factory --host 0.0.0.0 --port 7331
```

Key endpoints:
- `GET /health`
- `POST /projects`, `GET /projects`
- `POST /tasks`, `GET /tasks`, `POST /tasks/{id}/move`, `GET /tasks/{id}/context`
- `POST /runs`
- `POST /sessions`, `POST /sessions/{id}/end`
- `POST /approvals`, `GET /approvals`, `POST /approvals/{id}/respond`
- `GET /sync/daily`, `GET /sync/weekly`

## MCP Server (for Claude Code / Cursor / Codex)

Add to your Claude Code MCP settings:

```json
{
  "mcpServers": {
    "slate": {
      "command": "uv",
      "args": ["run", "--directory", "<path-to-slate>/packages/core", "slate-mcp"]
    }
  }
}
```

Available MCP tools:
- `create_project` — create a project
- `create_task` — create and assign a task
- `update_task_state` — move a task through states (todo → investigating → implementing → code_review → qa → ready_to_merge → done)
- `log_agent_run` — record what was done and the cost
- `get_task_context` — get full context to resume a task (state + all runs + transitions)
- `list_tasks` — see what's pending
- `request_approval` — ask the human before proceeding with a risky action
- `daily_sync` — what happened today and total cost

## Task States

```
todo → investigating → implementing → code_review → qa → ready_to_merge → done
                                   ↘ blocked
                                   ↘ cancelled
```
