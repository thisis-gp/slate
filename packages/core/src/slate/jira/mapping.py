from __future__ import annotations
import json
import os
import re
from datetime import datetime, timezone

_JIRA_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")


def allowed_jira_prefixes() -> list[str]:
    """Allowed project prefixes from JIRA_ALLOWED_PREFIXES (comma-separated).

    Empty list means "allow any valid key".
    """
    raw = os.getenv("JIRA_ALLOWED_PREFIXES", "")
    return [p.strip().upper() for p in raw.split(",") if p.strip()]


def normalize_jira_key(key: str) -> str:
    """Strip, remove internal spaces, uppercase a Jira key."""
    return "".join((key or "").split()).upper()


def is_allowed_jira_key(key: str) -> bool:
    """True iff key is a valid Jira key matching an allowed project prefix.

    Empty allowlist permits any syntactically valid key.
    """
    norm = normalize_jira_key(key)
    if not _JIRA_KEY_RE.match(norm):
        return False
    prefixes = allowed_jira_prefixes()
    if not prefixes:
        return True
    return norm.rsplit("-", 1)[0] in prefixes

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
