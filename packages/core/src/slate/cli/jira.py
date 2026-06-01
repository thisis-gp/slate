from __future__ import annotations
import asyncio
from pathlib import Path
import typer
import aiosqlite
from rich.console import Console
from rich.table import Table
from slate.db.schema import apply_schema
from slate.db.queries import (
    upsert_jira_config, get_jira_config,
    update_task_jira_key, list_jira_sync_log,
)
from slate.jira.sync import sync_all

app = typer.Typer(help="Jira integration")
console = Console(legacy_windows=False)


def _db_path() -> Path:
    p = Path.home() / ".slate" / "db.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@app.command("configure")
def configure(
    base_url: str = typer.Option(..., "--url", help="https://myorg.atlassian.net"),
    email: str = typer.Option(..., "--email", help="Your Atlassian account email"),
    api_token: str = typer.Option(..., "--token", help="Atlassian API token"),
    sync_time: str = typer.Option("09:00", "--sync-time", help="Daily sync time HH:MM (24h)"),
    state_map: str = typer.Option("", "--state-map",
                                   help='JSON override e.g. \'{"done":"Completed"}\''),
):
    """Configure Jira credentials and daily sync schedule."""
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            await upsert_jira_config(db, base_url=base_url, email=email,
                                      api_token=api_token, sync_time=sync_time,
                                      state_map=state_map)
        console.print(f"[green]Jira configured[/] — daily sync at [bold]{sync_time}[/]")
        console.print(f"  URL:   {base_url}")
        console.print(f"  Email: {email}")
    asyncio.run(_run())


@app.command("sync")
def sync_now():
    """Trigger an immediate Jira sync."""
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            result = await sync_all(db)
        if result.get("skipped"):
            console.print(f"[yellow]Skipped:[/] {result.get('reason')}")
            return
        console.print(f"[green]Synced {result['synced']} task(s)[/]")
        for r in result.get("results", []):
            wl = r.get("worklogs", {})
            console.print(
                f"  {r['jira_key']} — status: {r.get('status')} | worklogs: {wl.get('synced_worklogs', 0)}"
            )
    asyncio.run(_run())


@app.command("status")
def status():
    """Show Jira config and last sync results."""
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            config = await get_jira_config(db)
            logs = await list_jira_sync_log(db, limit=20)

        if not config:
            console.print("[yellow]Jira not configured.[/] Run: slate jira configure --url ... --email ... --token ...")
            return

        console.print("[bold]Jira Config[/]")
        console.print(f"  URL:        {config['base_url']}")
        console.print(f"  Email:      {config['email']}")
        console.print(f"  Sync time:  {config['sync_time']}")
        console.print(f"  Enabled:    {'yes' if config['enabled'] else 'no'}")

        if not logs:
            console.print("\n[dim]No sync history yet.[/]")
            return

        console.print("\n[bold]Recent Sync Log (last 20)[/]")
        table = Table("Jira Key", "Action", "Status", "Detail")
        for log in logs:
            table.add_row(log["jira_key"], log["action"], log["status"],
                          (log["detail"] or "")[:60])
        console.print(table)

        pending = [l for l in logs if l["status"] == "approval_needed"]
        if pending:
            console.print(f"\n[yellow]⚠ {len(pending)} transition(s) need approval:[/]")
            for l in pending:
                console.print(f"  {l['jira_key']}: {l['detail']}")
    asyncio.run(_run())


@app.command("link")
def link(
    task_id: str = typer.Argument(..., help="Slate task ID or ticket e.g. MP-3"),
    jira_key: str = typer.Argument(..., help="Jira issue key e.g. PROJ-123"),
):
    """Link an existing Slate task to a Jira issue."""
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            await update_task_jira_key(db, task_id=task_id, jira_key=jira_key)
        console.print(f"[green]Linked[/] {task_id} → [bold]{jira_key.upper()}[/]")
    try:
        asyncio.run(_run())
    except ValueError as e:
        console.print(f"[red]{e}[/]")
        raise typer.Exit(1)
