"""``slate timer``: measured time for Jira worklogs.

    slate timer start BX-4270 --agent claude --tool claude-code
    slate timer stop "Fixed ... ; PR #7801" --agent claude
    slate timer status [--agent claude] [--json]
    slate timer pause|resume --agent claude
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import aiosqlite
import typer
from rich.console import Console

from slate import timer as timers
from slate.db.schema import apply_schema
from slate.jira.scrub import WORKLOG_FORMAT_HINT

app = typer.Typer(help="Start/stop a work timer; stop writes a measured worklog")
console = Console(legacy_windows=False)

AGENT_OPT = typer.Option("human", "--agent", "-a", help="Agent name (one timer per agent)")


def _db_path() -> Path:
    p = Path.home() / ".slate" / "db.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _run(coro_fn):
    async def _wrap():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            try:
                return await coro_fn(db)
            except timers.TimerError as e:
                console.print(f"[red]{e}[/]")
                if str(e).startswith("summary rejected"):
                    console.print(f"[dim]{WORKLOG_FORMAT_HINT}[/]")
                raise typer.Exit(1)
    return asyncio.run(_wrap())


def _fmt(seconds: int) -> str:
    return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m" if seconds >= 3600 else f"{seconds // 60}m"


@app.command("start")
def start_cmd(
    ticket: str = typer.Argument(..., help="BX-<n> (or slate task id)"),
    agent: str = AGENT_OPT,
    tool: str = typer.Option("cli", "--tool", "-t", help="Tool (claude-code, codex, ...)"),
):
    """Start timing work on a ticket. Re-running for the same ticket is a no-op."""
    async def go(db):
        t, created = await timers.start(db, ticket, agent, tool)
        verb = "Timer started" if created else "Timer already running"
        console.print(f"[green]{verb}[/] on [cyan]{timers.label(t)}[/] for {agent} "
                      f"({_fmt(timers.elapsed_seconds(t))} so far)")
    _run(go)


@app.command("stop")
def stop_cmd(
    summary: str = typer.Argument("", help="1-3 sentences: what was done, finding, artifacts, outcome"),
    agent: str = AGENT_OPT,
    time_spent: int = typer.Option(0, "--time", help="Override measured time (minutes)"),
    discard: bool = typer.Option(False, "--discard", help="Stop without writing a worklog"),
    force: bool = typer.Option(False, "--force", help="Skip the summary quality check"),
):
    """Stop the timer and write one worklog with the measured time."""
    async def go(db):
        r = await timers.stop(db, agent, summary, minutes=time_spent, discard=discard, force=force)
        if r["status"] == "discarded":
            console.print(f"[yellow]Timer discarded[/] on {timers.label(r)} "
                          f"({_fmt(r['seconds'])} not logged)")
        else:
            console.print(f"[green]Worklog added[/] ({_fmt(r['seconds'])}) "
                          f"-> Jira [cyan]{timers.label(r)}[/]")
    _run(go)


@app.command("status")
def status_cmd(
    agent: str = typer.Option("", "--agent", "-a", help="Only this agent"),
    as_json: bool = typer.Option(False, "--json", help="Machine-readable output for hooks"),
):
    """Show running or paused timers."""
    async def go(db):
        rows = await timers.active_timers(db, agent)
        if as_json:
            print(json.dumps([{
                "agent": r["agent_name"], "tool": r["tool"], "status": r["status"],
                "jira": r.get("jira_issue_key"), "task_id": r["task_id"],
                "title": r.get("task_title"), "started_at": r["started_at"],
                "elapsed_minutes": timers.elapsed_seconds(r) // 60,
            } for r in rows]))
            return
        if not rows:
            console.print("[dim]No timer running.[/]")
            return
        for r in rows:
            console.print(f"{r['agent_name']}: [cyan]{timers.label(r)}[/] {r['status']} "
                          f"{_fmt(timers.elapsed_seconds(r))}  {r.get('task_title') or ''}")
    _run(go)


@app.command("pause")
def pause_cmd(agent: str = AGENT_OPT):
    """Pause the timer (time while paused is not logged)."""
    async def go(db):
        t = await timers.pause(db, agent)
        console.print(f"[yellow]Paused[/] {timers.label(t)} at {_fmt(timers.elapsed_seconds(t))}")
    _run(go)


@app.command("resume")
def resume_cmd(agent: str = AGENT_OPT):
    """Resume a paused timer."""
    async def go(db):
        t = await timers.resume(db, agent)
        console.print(f"[green]Resumed[/] {timers.label(t)} at {_fmt(timers.elapsed_seconds(t))}")
    _run(go)
