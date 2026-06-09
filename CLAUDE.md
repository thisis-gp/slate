# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What Slate is

A shared, persistent kanban board for AI agents: create tasks, log runs/worklogs, track cost, and gate risky actions (notably Jira pushes) behind human approval. Two packages:

- `packages/core` — Python backend: Typer CLI, FastAPI HTTP API, MCP server, SQLite storage, Jira sync.
- `packages/ui` — React 19 + Vite + Tailwind kanban UI (TanStack Query, react-router).

## Commands

All Python commands run from `packages/core` (the uv workspace root is the repo root, but `slate` is defined there). Use `uv`, not bare `python`.

```bash
# Backend setup
cd packages/core && uv sync

# Run API (dev)
uv run uvicorn slate.api.app:create_app --factory --host 0.0.0.0 --port 7331

# CLI (entry point: slate.cli.main:app)
uv run slate <subcommand>

# MCP server (entry point: slate.mcp.server:main)
uv run slate-mcp

# Tests — run from REPO ROOT (testpaths=["tests"] in root pyproject.toml; asyncio_mode=auto)
uv run pytest                                  # full suite
uv run pytest tests/core/test_jira_sync.py     # one file
uv run pytest tests/core/test_jira_sync.py::test_name   # one test
uv run pytest -k jira                           # by keyword

# UI (package manager is Yarn v1.x per global rules — but UI scripts shown with the lockfile present)
cd packages/ui && yarn install && yarn dev      # dev server on :5173, proxies to API
yarn build                                      # tsc && vite build

# Full stack via Docker (UI + API + nginx, one container, host port 7331)
docker-compose up
```

Note: tests live in `tests/` at the repo root (the active suite, 13 files). There is one stray legacy test at `packages/core/tests/core/test_jira_client.py` that is **not** on the configured testpaths — prefer the root `tests/` tree.

## Architecture

**Storage is a single SQLite file at `~/.slate/db.sqlite`.** There is no ORM and no migration framework. `slate/db/schema.py` holds the full DDL plus an idempotent `MIGRATIONS` list of `ALTER`/`CREATE` statements wrapped in try/except (duplicate-column errors are swallowed). `apply_schema(conn)` runs both and is called on **every** connection open.

**The CLI and API both talk to SQLite directly — the CLI does NOT go through the HTTP API.** Each CLI command opens its own `aiosqlite` connection to `~/.slate/db.sqlite`, calls `apply_schema`, does its work, and closes. The API keeps one long-lived connection on `app.state.db` (created in the `lifespan` context manager). Because both processes share one file, the running API server and CLI invocations operate on the same live data. Tests inject an in-memory DB onto `app.state.db` instead (see `tests/core/test_api/conftest.py`).

**Layering** (`packages/core/src/slate/`):
- `models.py` — Pydantic models + the canonical enums (`TaskState`, `TaskType`, `TaskPriority`, `RunStatus`, …).
- `db/queries.py` — all SQL. Both the CLI commands and `mcp/tools.py` call these functions; keep query logic here, not in callers.
- `cli/` — one Typer sub-app per noun (`task`, `project`, `run`, `session`, `comment`, `sync`, `sprint`, `jira`, `worklog`, `notify`, `obsidian`), wired together in `cli/main.py`. Each command wraps an async `_run()` in `asyncio.run`.
- `api/` — `app.py` builds the FastAPI app and includes one router per resource from `api/routes/`.
- `mcp/` — MCP server (`server.py`) exposing `tools.py`, which are thin wrappers over `db/queries.py`.
- `jira/` — Jira integration (see below). `jira/scrub.py` strips agent/tool identity from worklog text; `jira/importer.py` is the approval-gated Jira→Slate pull.
- `obsidian/vault.py` — per-Jira markdown docs in a central vault (managed block + freeform). Config: `SLATE_VAULT_PATH`, overridable per-repo via `.agents/slate.json`.
- `llm/summarize.py` — worklog summarizer (neutral-voice prompt; output is scrubbed).
- `notifications/` — notification engine + rules.

### Jira sync (the core domain logic)

Slate pushes **Slate → Jira only** (state transitions + aggregated worklogs), never the reverse, and only after **explicit human approval**. The flow in `jira/sync.py`:

1. `build_batch` — DB-only, no network. Groups unsynced worklogs by Jira key, pairs each with its task's current state.
2. `summarize_batch` — runs each issue's worklog entries through `llm/summarize.py` (multi-provider, with timeout + plain-bullet fallback so sync never blocks on the LLM).
3. `prepare_pending` — stages the batch into `jira_pending_sync` (status `pending`) and emits a `jira_sync_approval` notification.
4. `approve_pending` / `reject_pending` — a human approves/rejects in the UI; only `approve_pending` calls the Jira API (`jira/client.py`). It re-reads fresh worklogs at push time, supports per-issue `exclude`, and supersedes overlapping pending batches.

The daily scheduler (`jira/scheduler.py`, started in the API `lifespan` when Jira config is `enabled`) runs `run_approval_scheduler`, which only *stages* a batch — it never pushes. The scheduler is **timezone-aware** (`SLATE_TZ`, default `Asia/Kolkata`) and **recovers missed runs**: a 60s poll loop stamps the last-fired local date in the `scheduler_state` table, so a window missed while the process was down fires on next startup and never twice the same day. (The container runs in UTC — without `SLATE_TZ`, `09:00` would fire at 09:00 UTC.)

**Worklog identity scrubbing.** Slate is a shared memory layer for several AI tools, but synced worklogs must read as the human's own work. `jira/scrub.py:scrub_identity` removes tool/agent/vendor names (claude, codex, cursor, kimi, hermes, gpt, anthropic, …) and neutralizes voice. It's applied on **every** path — LLM input/output *and* the offline fallback — so a banned token can't leak even on LLM timeout. The summarizer prompt also requests a neutral, impersonal voice.

**Jira→Slate import (`jira/importer.py`).** The inverse pull is also approval-gated: `stage_assigned_issues` (JQL `assignee = currentUser()`) only stages candidates into `jira_pending_import`; `approve_import` creates the linked task in a human-chosen project and scaffolds its Obsidian doc. BX-only allowlist and idempotency (skip already-imported/pending keys) enforced on the way in.

**Task context / shared memory.** `comments.kind` is `note | decision | heartbeat`. `get_task_context` returns `decisions`/`heartbeats`/`notes` splits plus `latest_heartbeat`. CLI: `slate task context [--json]` (the brief), `slate task heartbeat`, `slate comment decision`.

**Allowed-prefix enforcement (this org: BX-only).** `jira/mapping.py:is_allowed_jira_key` validates keys against the `JIRA_ALLOWED_PREFIXES` env var (comma-separated, e.g. `BX`). An empty allowlist permits any syntactically valid key. Enforcement happens at link time (`db/queries.py:_validate_jira_key`) **and** at push time (`build_batch` skips non-allowed keys — defense in depth). Worklogs on tasks with no Jira key never sync.

State→status mapping lives in `jira/mapping.py:DEFAULT_STATE_MAP`, overridable per-config via the `state_map` JSON column. When a target transition isn't available in the Jira workflow, sync records `approval_needed` rather than failing.

## Task states

Enum (`models.py`): `todo, in_progress, on_hold, code_review, qa, ready_to_merge, done, blocked, cancelled`. Note the CLI/docs sometimes use the workflow aliases `investigating` / `implementing`, which `DEFAULT_STATE_MAP` maps to Jira "In Progress".

## Conventions

- Timestamps are stored as REAL unix epoch seconds (`unixepoch('now','subsec')` defaults); IDs are `uuid4` strings.
- New SQL goes in `db/queries.py`; expose it to MCP via a wrapper in `mcp/tools.py`. New schema changes append to `schema.py`'s `DDL` **and** the `MIGRATIONS` list (so existing DBs upgrade).
- LLM provider keys are env-only (`MOONSHOT_API_KEY` → `NVIDIA_API_KEY` → `GEMINI_API_KEY` fallback order); never hardcode. See `.env.example`.

## This repo's own task tracking

Per the global agent rules, work on this repo is itself tracked in Slate and **every task must be linked to a `BX-<number>` Jira issue** before logging work. Use the `slate` CLI (never the MCP server for tracking). Ask the user for the BX number if you don't have it. See `AGENT_INSTRUCTIONS.md` for the per-task workflow.
