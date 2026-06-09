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

---

## Jira Integration

Slate can push task status and agent run worklogs to linked Jira issues on a daily schedule.

**Setup:**
```bash
slate jira configure \
  --url https://myorg.atlassian.net \
  --email your@email.com \
  --token <your-atlassian-api-token> \
  --sync-time 09:00   # or 21:00 for evening
```

**Link a task to a Jira issue:**
```bash
# At creation time:
slate task create "Fix login bug" --project MP --jira PROJ-123

# Or link an existing task:
slate jira link MP-4 PROJ-123
```

**Manual sync:**
```bash
slate jira sync
```

**Import Jira issues assigned to you (Jira → Slate, approval-gated):**
```bash
slate jira import                 # stage assigned issues (creates NO tasks)
slate jira imports                # review the staged queue
slate jira import-approve <id> --project <project-id> --assign me   # create the linked task
slate jira import-reject <id>
```
Importing only *stages* candidates; every issue is assigned to a Slate project and
approved by you (in the CLI or the **Jira Import** UI tab) before a task is created.
Re-running is idempotent. Set `JIRA_IMPORT_ENABLED=1` (+ optional `JIRA_IMPORT_TIME`)
to stage assigned issues automatically each day — still approval-gated.

**Worklog identity:** synced worklog notes are scrubbed to a neutral, impersonal
voice — tool/agent/vendor names (Claude, Codex, Cursor, …) never reach Jira, on
the LLM path *and* the offline fallback.

**Scheduler timezone:** the daily approval-staging runs in `SLATE_TZ` (default
`Asia/Kolkata`) and recovers a missed window on next startup.

**View sync status and approval-needed items:**
```bash
slate jira status
```

**What gets synced (Slate → Jira only):**
- Task state → Jira workflow transition
- Agent run worklogs → Jira worklog entries (time spent + summary)

When a Jira transition isn't available in your workflow, Slate logs it as `approval_needed` instead of failing. Run `slate jira status` to see what needs manual action.

**Default state map:**

| Slate state | Jira status |
|---|---|
| `todo` | To Do |
| `in_progress` / `investigating` / `implementing` | In Progress |
| `on_hold` | On Hold |
| `code_review` | In Review |
| `qa` | Testing |
| `ready_to_merge` | Ready to Merge |
| `done` | Done |
| `blocked` | Blocked |
| `cancelled` | Cancelled |

Override with `--state-map '{"done":"Completed"}'` in `slate jira configure`.

**API endpoints:**
```
POST  /jira/configure
GET   /jira/status
POST  /jira/sync
GET   /jira/sync-log
POST  /jira/import                       # stage assigned issues
GET   /jira/imports                      # list staged imports
POST  /jira/imports/{id}/approve         # create linked task in chosen project
POST  /jira/imports/{id}/reject
```

---

## Shared context for agents

Slate is a shared memory layer across your tools (Claude Code, Codex, Cursor, …).
Before starting a task, an agent reads the brief; while working, it records progress
and decisions so the next agent (or you) has the full picture.

```bash
# The brief an agent reads before starting (human or --json for agents)
slate task context <task-id>
slate task context <task-id> --json

# Lightweight progress heartbeat (latest one surfaces in context)
slate task heartbeat <task-id> "wired the parser, tests next" --by codex

# Record a decision + rationale (shown prominently in context)
slate comment decision <task-id> "Chose SQLite over Postgres — single-file, no ops" --by claude
```

Comments carry a `kind` of `note`, `decision`, or `heartbeat`.

---

## Obsidian docs

Each Jira issue gets one markdown doc in a central vault, with per-repo subfolders.
Slate owns a managed block (status, worklogs, decisions, state history); everything
outside it is freeform for agents and you. Configure the vault root with
`SLATE_VAULT_PATH`, overridable per-repo via `.agents/slate.json`
(`{"vault_path": "..."}`).

```bash
slate obsidian path                 # show the resolved vault path
slate obsidian sync <task-id>       # write/update <vault>/slate/<JIRA_KEY>.md
slate obsidian show <JIRA_KEY>      # print the current doc
```

Approving a Jira import auto-scaffolds the issue's doc.
