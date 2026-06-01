from __future__ import annotations
import asyncio
import typer
from rich.console import Console
from rich.table import Table
import aiosqlite
from pathlib import Path
from slate.db.schema import apply_schema
from slate.db.queries import (
    insert_notification_rule, list_notification_rules,
    list_pending_notifications, mark_notification_sent,
)
from slate.notifications.engine import process_pending_notifications

app = typer.Typer(help="Notification system")
console = Console(legacy_windows=False)


def _db_path() -> Path:
    p = Path.home() / ".slate" / "db.sqlite"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


@app.command("rule-add")
def add_rule(
    name: str = typer.Argument(...),
    event_type: str = typer.Option(..., "--event", help="Event type: task_state_change, worklog_synced, *"),
    destination: str = typer.Option(..., "--dest", help="Webhook URL, Slack webhook, etc"),
    channel: str = typer.Option("webhook", "--channel", help="console, webhook, slack"),
    condition: str = typer.Option("", "--condition", help="Optional condition filter"),
):
    """Add a notification rule."""
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            await insert_notification_rule(
                db, name=name, event_type=event_type,
                condition=condition, channel=channel, destination=destination,
            )
        console.print(f"[green]Rule added:[/] {name} -> {channel} on {event_type}")
    asyncio.run(_run())


@app.command("rule-list")
def list_rules():
    """List notification rules."""
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            rules = await list_notification_rules(db, enabled_only=False)
        if not rules:
            console.print("[dim]No notification rules.[/]")
            return
        table = Table("ID", "Name", "Event", "Channel", "Destination", "Enabled")
        for r in rules:
            table.add_row(
                str(r["id"]), r["name"], r["event_type"],
                r["channel"], r["destination"][:50],
                "yes" if r["enabled"] else "no",
            )
        console.print(table)
    asyncio.run(_run())


@app.command("pending")
def pending():
    """Show pending notifications."""
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            notifications = await list_pending_notifications(db)
        if not notifications:
            console.print("[dim]No pending notifications.[/]")
            return
        table = Table("ID", "Type", "Title", "Channel", "Created")
        for n in notifications:
            table.add_row(
                n["id"][:8], n["type"], n["title"][:40],
                n["channel"], str(round(n.get("created_at", 0))),
            )
        console.print(table)
    asyncio.run(_run())


@app.command("process")
def process():
    """Process and send all pending notifications."""
    async def _run():
        async with aiosqlite.connect(_db_path()) as db:
            db.row_factory = aiosqlite.Row
            await apply_schema(db)
            result = await process_pending_notifications(db)
        console.print(f"[green]Processed {result['total']} notifications:[/] {result['sent']} sent, {result['failed']} failed")
    asyncio.run(_run())
