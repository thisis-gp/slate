from __future__ import annotations
import asyncio
import json
import httpx
from typing import Optional
import aiosqlite
from slate.db.queries import (
    insert_notification, list_pending_notifications,
    mark_notification_sent, list_notification_rules,
)


async def create_notification(
    db: aiosqlite.Connection,
    event_type: str,
    title: str,
    body: str,
    task_id: str = "",
    channel: str = "console",
    destination: str = "",
) -> str:
    """Create a notification. If no rules match, defaults to console."""
    import uuid
    nid = str(uuid.uuid4())
    
    # Check rules
    rules = await list_notification_rules(db, enabled_only=True)
    matched = False
    for rule in rules:
        if rule["event_type"] == event_type or rule["event_type"] == "*":
            # Simple condition matching (can be extended)
            if rule.get("condition"):
                # For now, skip complex conditions
                continue
            await insert_notification(
                db, id=nid, type=event_type, task_id=task_id,
                title=title, body=body,
                channel=rule["channel"], destination=rule["destination"],
            )
            matched = True
            break
    
    if not matched:
        await insert_notification(
            db, id=nid, type=event_type, task_id=task_id,
            title=title, body=body,
            channel=channel, destination=destination,
        )
    
    return nid


async def send_notification(db: aiosqlite.Connection, notification: dict) -> bool:
    """Send a single notification via its configured channel."""
    channel = notification.get("channel", "console")
    
    if channel == "console":
        print(f"[SLATE NOTIFICATION] {notification['title']}: {notification['body']}")
        await mark_notification_sent(db, notification["id"])
        return True
    
    elif channel == "webhook":
        destination = notification.get("destination", "")
        if not destination:
            return False
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    destination,
                    json={
                        "title": notification["title"],
                        "body": notification["body"],
                        "type": notification["type"],
                        "task_id": notification.get("task_id"),
                    },
                    timeout=10.0,
                )
            await mark_notification_sent(db, notification["id"])
            return True
        except Exception:
            return False
    
    elif channel == "slack":
        # Slack webhook URL
        destination = notification.get("destination", "")
        if not destination:
            return False
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    destination,
                    json={
                        "text": f"*{notification['title']}*\n{notification['body']}",
                    },
                    timeout=10.0,
                )
            await mark_notification_sent(db, notification["id"])
            return True
        except Exception:
            return False
    
    return False


async def process_pending_notifications(db: aiosqlite.Connection) -> dict:
    """Process all pending notifications."""
    pending = await list_pending_notifications(db)
    sent = 0
    failed = 0
    
    for notification in pending:
        success = await send_notification(db, notification)
        if success:
            sent += 1
        else:
            failed += 1
    
    return {"sent": sent, "failed": failed, "total": len(pending)}


async def notify_task_state_change(
    db: aiosqlite.Connection,
    task_id: str,
    task_title: str,
    from_state: str,
    to_state: str,
    changed_by: str,
) -> str:
    """Create and immediately send a task state change notification."""
    title = f"Task moved: {task_title}"
    body = f"State changed from '{from_state or 'new'}' to '{to_state}' by {changed_by}"
    nid = await create_notification(
        db, event_type="task_state_change",
        title=title, body=body, task_id=task_id,
    )
    # Also process immediately
    pending = await list_pending_notifications(db)
    for n in pending:
        if n["id"] == nid:
            await send_notification(db, n)
            break
    return nid


async def notify_worklog_synced(
    db: aiosqlite.Connection,
    task_id: str,
    jira_key: str,
    minutes: int,
) -> str:
    """Notify that worklogs were synced to Jira."""
    title = f"Worklog synced: {jira_key}"
    body = f"{minutes} minutes logged to Jira issue {jira_key}"
    return await create_notification(
        db, event_type="worklog_synced",
        title=title, body=body, task_id=task_id,
    )
