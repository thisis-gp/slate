"""Obsidian vault integration — one markdown doc per Jira issue.

An Obsidian vault is just a folder of markdown, so there is no API: Slate reads
and writes files directly. Layout is a **central vault with per-repo subfolders**:

    <vault>/<subfolder>/<JIRA_KEY>.md      e.g. ~/ObsidianVault/slate/BX-3023.md

Each doc has a **Slate-managed block** delimited by HTML-comment markers. Slate
owns only what's between the markers (status, worklogs, decisions, state history,
regenerated on every sync); everything outside is freeform, authored by agents and
humans, and Slate never touches it. This lets the doc be both a reliable mirror of
Slate's facts and a living scratchpad.

Config resolution (root default, per-project override):
  1. ``.agents/slate.json`` -> ``{"vault_path": "..."}`` walking up from CWD (project)
  2. ``SLATE_VAULT_PATH`` env var (root/global default)
Returns None if neither is set — callers should treat Obsidian as disabled then.
"""
from __future__ import annotations
import json
import os
import re
from pathlib import Path
from typing import Optional

BEGIN = "<!-- SLATE:BEGIN (managed — do not edit this block by hand) -->"
END = "<!-- SLATE:END -->"
_MANAGED_RE = re.compile(
    re.escape(BEGIN) + r".*?" + re.escape(END), re.DOTALL
)
_SAFE_KEY_RE = re.compile(r"[^A-Za-z0-9._-]")


def find_project_override(start: Optional[Path] = None) -> Optional[str]:
    """Walk up from ``start`` (or CWD) for ``.agents/slate.json`` with vault_path."""
    here = (start or Path.cwd()).resolve()
    for d in [here, *here.parents]:
        cfg = d / ".agents" / "slate.json"
        if cfg.is_file():
            try:
                data = json.loads(cfg.read_text(encoding="utf-8"))
            except Exception:
                return None
            vp = (data.get("vault_path") or "").strip()
            return vp or None
    return None


def resolve_vault_path(start: Optional[Path] = None) -> Optional[Path]:
    """Project ``.agents/slate.json`` override wins over the ``SLATE_VAULT_PATH`` env."""
    override = find_project_override(start)
    raw = override or os.getenv("SLATE_VAULT_PATH", "").strip()
    if not raw:
        return None
    return Path(raw).expanduser()


def _safe(component: str) -> str:
    """Sanitize a path component so a key/subfolder can't escape the vault."""
    return _SAFE_KEY_RE.sub("_", (component or "").strip()) or "_"


def issue_doc_path(
    jira_key: str, subfolder: str = "slate", *, start: Optional[Path] = None,
    vault: Optional[Path] = None,
) -> Optional[Path]:
    base = vault or resolve_vault_path(start)
    if not base:
        return None
    return base / _safe(subfolder) / f"{_safe(jira_key)}.md"


def _render_managed(ctx: dict, jira_key: str) -> str:
    task = ctx.get("task") or {}
    lines = [BEGIN, ""]
    lines.append(f"- **Jira:** {jira_key}")
    if task.get("state"):
        lines.append(f"- **Status:** {task['state']}")
    if task.get("assigned_to"):
        lines.append(f"- **Assignee:** {task['assigned_to']}")
    if task.get("priority"):
        lines.append(f"- **Priority:** {task['priority']}")

    decisions = ctx.get("decisions") or []
    if decisions:
        lines += ["", "### Decisions"]
        lines += [f"- {d['body']} _(— {d.get('author', '?')})_" for d in decisions]

    worklogs = ctx.get("worklogs") or []
    if worklogs:
        lines += ["", "### Worklog"]
        for w in worklogs[-20:]:
            mins = (w.get("time_spent_seconds") or 0) // 60
            lines.append(f"- {w['summary']} _({mins}m)_")

    transitions = ctx.get("transitions") or []
    if transitions:
        lines += ["", "### State history"]
        for t in transitions:
            frm = t.get("from_state") or "—"
            lines.append(f"- {frm} → {t['to_state']} _(by {t.get('changed_by', '?')})_")

    lines += ["", END]
    return "\n".join(lines)


def write_issue_doc(
    jira_key: str,
    ctx: dict,
    *,
    title: Optional[str] = None,
    subfolder: str = "slate",
    start: Optional[Path] = None,
    vault: Optional[Path] = None,
) -> Optional[Path]:
    """Create or update the issue doc, replacing only the Slate-managed block.

    Returns the path written, or None if no vault is configured. Freeform content
    the user/agents wrote outside the markers is preserved verbatim.
    """
    path = issue_doc_path(jira_key, subfolder, start=start, vault=vault)
    if not path:
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    managed = _render_managed(ctx, jira_key)

    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if _MANAGED_RE.search(existing):
            new = _MANAGED_RE.sub(lambda _: managed, existing, count=1)
        else:
            # File exists but has no managed block — prepend one, keep their content.
            new = f"{managed}\n\n{existing.lstrip()}"
    else:
        heading = f"# {jira_key}" + (f" — {title}" if title else "")
        new = f"{heading}\n\n{managed}\n\n## Notes\n\n"
    path.write_text(new, encoding="utf-8")
    return path


def read_issue_doc(
    jira_key: str, subfolder: str = "slate", *,
    start: Optional[Path] = None, vault: Optional[Path] = None,
) -> Optional[str]:
    """Return the full markdown for a Jira key, or None if absent/unconfigured."""
    path = issue_doc_path(jira_key, subfolder, start=start, vault=vault)
    if not path or not path.exists():
        return None
    return path.read_text(encoding="utf-8")
