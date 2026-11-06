# Slate playbook — how Guru works this repo

Read with `CLAUDE.md` (commands/architecture) and `~/.agents/rules/how-guru-works.md` (his style).

## What slate is to him
The shared memory + worklog layer for ALL his agents (Claude Code, Codex, Cursor, Kimi, Hermes). It is infrastructure he depends on daily — a bug here corrupts his Jira time tracking. Change conservatively.

## Invariants he has stated explicitly
- Worklog summaries synced to Jira must **never contain tool names** (no "claude", "codex", "cursor", "agent") — they must read like a human wrote them. Since 2026-11-06 there is **no LLM rewrite**: `jira/scrub.py` sends the text verbatim, removes tool names only in tool-usage form ("Claude Tag", "email via Claude", gpt-5-nano are product work and stay), and drops status-poll/start-marker/housekeeping clauses. `worklog_problems()` rejects bad summaries at write time (`timer stop`, `worklog add`). Re-calibrate any regex change against the live worklogs: it must not cut real work.
- Time comes from `slate timer start/stop` (`slate/timer.py`): one active timer per agent (partial unique index), elapsed = wall clock minus pauses, >10h needs `--time`.
- Only **BX-<n>** Jira keys are valid; unlinked tasks never sync. Never weaken this validation.
- Humans approve every Jira push (daily batch in the slate UI). Agents never push directly.
- Watch for **duplicate worklogs** in the approval queue — dedupe logic has needed fixing before; verify dedupe when touching sync or cron code.
- The cron/daily sync has been flaky historically — when changing it, test the full cycle: worklog add → batch staging → approval → Jira push.

## Practicalities
- `uv` only, from `packages/core`; tests from repo root (`uv run pytest`). UI: React 19 + Vite in `packages/ui`.
- The production `slate` CLI on PATH runs inside the slate Docker container against the **live DB** — don't test destructive changes through it; use a dev DB.
- Consumers everywhere call the CLI (never the MCP server) — CLI flags/output are a public contract for all his other agents; don't break them silently.
