from __future__ import annotations
import json
from datetime import datetime, timezone

DEFAULT_STATE_MAP: dict[str, str] = {
    "todo": "To Do",
    "in_progress": "In Progress",
    "on_hold": "On Hold",
    "investigating": "In Progress",
    "implementing": "In Progress",
    "code_review": "In Review",
    "qa": "Testing",
    "ready_to_merge": "Ready to Merge",
    "done": "Done",
    "blocked": "Blocked",
    "cancelled": "Cancelled",
}


def resolve_state_map(config_json: str | None) -> dict[str, str]:
    if not config_json:
        return DEFAULT_STATE_MAP
    try:
        override = json.loads(config_json)
        return {**DEFAULT_STATE_MAP, **override}
    except Exception:
        return DEFAULT_STATE_MAP


def find_transition_id(transitions: list[dict], target_name: str) -> str | None:
    target = target_name.lower()
    for t in transitions:
        if t["to"]["name"].lower() == target or t["name"].lower() == target:
            return t["id"]
    return None


def format_worklog_started(unix_ts: float) -> str:
    dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.000+0000")
