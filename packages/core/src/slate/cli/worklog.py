from __future__ import annotations
import asyncio, uuid
import typer
from rich.console import Console
from rich.table import Table
import aiosqlite
from pathlib import Path
from slate.db.schema import apply_schema
from slate.db.queries import (
    insert_worklog, list_worklogs, get_task,
    mark_worklog_synced, get_unsynced_worklogs,
)
from slate.jira.client import JiraClient
from slate.jira.mapping import format_worklog_started
from slate.jira.sync import _fallback_summary, _worklog_entries
from slate.db.queries import get_jira_config, insert_jira_sync_log

app = typer.Typer(help="Worklog tracking for Jira")
console = Console(legacy_windows=False)


def _db_path() -> Path:
    p = Path.home() / ".slate" / "db.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@app.command("add")
def add_worklog(
    task_id: str = typer.Argument(..., help="Slate task ID or ticket"),
    summary: str = typer.Argument(..., help="1-3 line summary of work done"),
    agent: str = typer.Option("human", "--agent", "-a", help="Agent name"),
    tool: str = typer.Option("cli", "--tool", "-t", help="Tool used (claude-code, codex, cursor, etc)"),
    time_spent: int = typer.Option(0, "--time", help="Time spent in minutes (0 = auto from now)"),
    run_id: str = typer.Option("", "--run", help="Link to agent_run ID"),
):
    """Add a worklog entry for a task. Used by agents to log their work."""
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            task = await get_task(db, task_id)
            if not task:
                console.print(f"[red]Task {task_id} not found[/]")
                raise typer.Exit(1)
            
            # Auto-calculate time if not provided (default 30 min)
            seconds = time_spent * 60 if time_spent > 0 else 1800
            
            wid = str(uuid.uuid4())
            await insert_worklog(
                db, id=wid, task_id=task_id, agent_run_id=run_id,
                agent_name=agent, tool=tool, summary=summary,
                time_spent_seconds=seconds,
            )
            mins = seconds // 60
            jira_note = ""
            if task.get("jira_issue_key"):
                jira_note = f" -> Jira [cyan]{task['jira_issue_key']}[/]"
            console.print(f"[green]Worklog added[/] ({mins}m) for {task_id[:8]}{jira_note}")
    asyncio.run(_run())


@app.command("list")
def list_worklogs_cmd(
    task_id: str = typer.Option("", "--task", "-t", help="Filter by task"),
    pending: bool = typer.Option(False, "--pending", help="Show only unsynced"),
):
    """List worklog entries."""
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            logs = await list_worklogs(
                db, task_id=task_id,
                unsynced_only=pending,
            )
        if not logs:
            console.print("[dim]No worklogs found.[/]")
            return
        table = Table("ID", "Task", "Agent", "Tool", "Summary", "Time", "Status")
        for w in logs:
            mins = w.get("time_spent_seconds", 0) // 60
            status = "[green]synced[/]" if w.get("synced_to_jira") else "[yellow]pending[/]"
            table.add_row(
                w["id"][:8],
                w["task_id"][:8],
                w["agent_name"],
                w["tool"],
                w["summary"][:50],
                f"{mins}m",
                status,
            )
        console.print(table)
    asyncio.run(_run())


@app.command("sync")
def sync_worklogs(
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be synced"),
):
    """Sync all pending worklogs to Jira. Aggregates by task into a single daily worklog."""
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            config = await get_jira_config(db)
            if not config or not config.get("enabled"):
                console.print("[yellow]Jira not configured.[/] Run: slate jira configure ...")
                raise typer.Exit(1)
            
            client = JiraClient(
                base_url=config["base_url"],
                email=config["email"],
                api_token=config["api_token"],
            )
            
            # Get all unsynced worklogs grouped by task
            logs = await get_unsynced_worklogs(db)
            if not logs:
                console.print("[dim]No pending worklogs to sync.[/]")
                return
            
            # Group by jira_issue_key
            from collections import defaultdict
            by_jira = defaultdict(list)
            for log in logs:
                jira_key = log.get("jira_issue_key")
                if jira_key:
                    by_jira[jira_key].append(log)
            
            if dry_run:
                console.print(f"[cyan]Dry run — would sync {len(logs)} worklog(s) across {len(by_jira)} Jira issue(s):[/]")
                for jira_key, items in by_jira.items():
                    total_mins = sum(w["time_spent_seconds"] for w in items) // 60
                    console.print(f"  {jira_key}: {len(items)} entries, {total_mins}m total")
                return
            
            # Sync each task's worklogs as a single aggregated entry
            for jira_key, items in by_jira.items():
                total_seconds = sum(w["time_spent_seconds"] for w in items)
                total_mins = total_seconds // 60
                
                # Build summary from all worklog entries
                summaries = _worklog_entries(items)
                combined_summary = _fallback_summary(summaries)
                if len(summaries) > 10:
                    combined_summary += f"\n... and {len(summaries) - 10} more entries"
                
                # Use earliest started_at
                started_ts = min(w["started_at"] for w in items)
                
                try:
                    result = await client.add_worklog(
                        jira_key,
                        time_spent_seconds=max(60, total_seconds),
                        comment=combined_summary,
                        started=format_worklog_started(started_ts),
                    )
                    jira_wid = result.get("id", "")
                    
                    # Mark all worklogs as synced
                    for w in items:
                        await mark_worklog_synced(db, w["id"], jira_wid)
                        await insert_jira_sync_log(
                            db, task_id=w["task_id"], jira_key=jira_key,
                            action="worklog", status="ok",
                            detail=f"Aggregated {len(items)} entries, {total_mins}m",
                        )
                    
                    console.print(f"[green]Synced[/] {jira_key}: {len(items)} entries, {total_mins}m")
                except Exception as e:
                    console.print(f"[red]Failed[/] {jira_key}: {str(e)[:80]}")
                    for w in items:
                        await insert_jira_sync_log(
                            db, task_id=w["task_id"], jira_key=jira_key,
                            action="worklog", status="error",
                            detail=str(e)[:200],
                        )
    asyncio.run(_run())
