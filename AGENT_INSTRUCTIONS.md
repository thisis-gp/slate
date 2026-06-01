# Slate Agent Instructions

## For Claude Code, Codex CLI, Cursor, Kimi, and Hermes

**Slate** is your task tracking system. Use it for EVERY task you work on.

### Quick Reference

```bash
# Before starting work
slate task list --state todo --assign <your-name>    # See your tasks

# When you start working on a task
slate task move <task-id> implementing --by <your-name>

# Log your work (1-3 line summary)
slate worklog add <task-id> "Implemented auth middleware with JWT validation" --agent <your-name> --tool <tool-name>

# When done
slate task move <task-id> code_review --by <your-name> --assign <reviewer>

# Log agent run with cost
slate run log <task-id> "Refactored user service" --agent <your-name> --tool <tool-name> --cost 0.05
```

### Tool Names

Use these tool identifiers:
- `claude-code` — Claude Code CLI
- `codex` — OpenAI Codex CLI
- `cursor` — Cursor IDE
- `kimi` — Kimi AI
- `hermes` — Hermes Agent

### Agent Names

Use your identifier:
- `claude` — Anthropic Claude
- `codex` — OpenAI Codex
- `cursor` — Cursor
- `kimi` — Kimi
- `hermes` — Hermes

### Task States

```
todo -> investigating -> implementing -> code_review -> qa -> ready_to_merge -> done
```

### Jira Integration

**Every task MUST be linked to a `BX-<number>` Jira issue (e.g. `BX-3023`) before you log any work.**

- When creating a task, provide the Jira key (`--jira BX-3023`). You'll be prompted if you omit it.
- If you don't have the Jira issue number, **ASK the user** — do not guess and do not invent a key.
- **Never** log worklogs against an unlinked task. Worklogs on unlinked tasks will NOT sync to Jira and show up as "pending a Jira key".
- Link an existing task at any time: `slate jira link <task-id> BX-3023`.

Slate enforces this at both link time and push time:
- It will **reject** any Jira key that is not a `BX-<number>` (non-`BX` projects are not allowed on this Atlassian).
- It will **not sync** worklogs from tasks that have no Jira key.

Worklogs are aggregated per issue and synced to Jira on the daily schedule after human approval.

### Cost Tracking

Always log costs when possible:
```bash
slate run log <task-id> "Summary" --cost 0.05
```

### Daily Workflow

1. Check assigned tasks: `slate task list --assign <your-name>`
2. Pick a task and move to `implementing`
3. Do the work
4. Add worklog: `slate worklog add <task-id> "What you did"`
5. Move to next state when done
6. At end of day, check: `slate sync daily`

### Important

- **Always** use the `slate` **CLI** for task tracking — never a slate MCP server (CLI only).
- **Always** add worklogs for meaningful work
- **Always** log state changes
- **Never** work a task without a `BX-<number>` Jira key — ask the user if you don't have it
