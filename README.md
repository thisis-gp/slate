# Slate

Task tracking for agentic workflows. Slate gives AI agents a shared, persistent kanban board — a place to create tasks, log runs, track costs, and request human approval before taking risky actions.

Built to work with Claude Code, Codex CLI, Cursor, and any other agent that can run shell commands or call an HTTP API.

---

## Packages

| Package | Description |
|---------|-------------|
| `packages/core` | Python backend — CLI, HTTP API, MCP server, SQLite storage |
| `packages/ui` | React + Vite kanban UI |

---

## Quick Start

**Requirements:** Python 3.11+, [uv](https://github.com/astral-sh/uv)

```bash
# Install
cd packages/core
uv sync

# Start the API server
uv run uvicorn slate.api.app:create_app --factory --host 0.0.0.0 --port 7331

# Use the CLI
uv run slate project create "my-app" --desc "My application"
uv run slate task create "Fix login bug" --project <project-id> --type bug --priority high
uv run slate task list --project <project-id>
```

---

## CLI Reference

```bash
# Projects
slate project create "my-app" --desc "Description"
slate project list

# Tasks
slate task create "Fix login bug" --project <id> --type bug --priority high
slate task list --project <id> --state todo
slate task show <task-id>
slate task move <task-id> implementing --by claude-code

# Agent run logging
slate run log <task-id> "Investigated the auth flow" --agent claude --tool claude-code

# Sessions
slate session start claude --tool claude-code --project <id>
slate session end <session-id> --summary "Implemented JWT" --cost 0.12

# Approvals
slate approve list
slate approve approve <approval-id>
slate approve reject <approval-id> --note "Not ready"

# Sync reports
slate sync daily
slate sync weekly
```

## Task States

```
todo → investigating → implementing → code_review → qa → ready_to_merge → done
                                   ↘ blocked
                                   ↘ cancelled
```

---

## HTTP API

```bash
# Health check
GET /health

# Core resources
POST   /projects
GET    /projects
POST   /tasks
GET    /tasks
POST   /tasks/{id}/move
GET    /tasks/{id}/context
POST   /runs
POST   /sessions
POST   /sessions/{id}/end
POST   /approvals
GET    /approvals
POST   /approvals/{id}/respond
GET    /sync/daily
GET    /sync/weekly
```

---

## MCP Server

For use with Claude Code, Cursor, or any MCP-compatible client:

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

**Available tools:** `create_project`, `create_task`, `update_task_state`, `log_agent_run`, `get_task_context`, `list_tasks`, `request_approval`, `daily_sync`

---

## UI

```bash
cd packages/ui
npm install
npm run dev
```

Opens a kanban board at `http://localhost:5173` connected to the local API server.

---

## Docker

```bash
docker-compose up
```

Runs the API server and UI together. API on port `7331`, UI on port `80`.
