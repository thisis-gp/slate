"""Identity scrubbing for Jira-bound worklog text.

Slate is a memory layer shared by several AI tools (Claude Code, Codex, Cursor,
Kimi, Hermes, …). Worklogs synced to Jira must read as the human's own work — no
tool, agent, or vendor names, and no "the agent did X" framing. We enforce this in
TWO layers:

  1. The LLM summarizer is *prompted* to write in a neutral, impersonal voice.
  2. Whatever the model (or the deterministic fallback) produces is then run
     through ``scrub_identity`` here, which is a hard guarantee: a banned token
     can never survive this pass, even if the model ignores its instructions or
     the LLM times out and we fall back to raw concatenation.

The voice is *neutral/impersonal*: leading subjects ("I", "we", "the agent") are
dropped so the note states the work itself — "Implemented JWT validation", not
"I implemented…" or "Claude implemented…".
"""
from __future__ import annotations
import re

# Tool / agent / vendor / model identifiers that must never reach Jira.
# Order matters: multi-word forms first so "claude code" is removed whole before
# "claude" would match it. Matched case-insensitively on word boundaries.
_IDENTITY_TERMS = [
    r"claude\s+code", r"claude-code", r"claude",
    r"codex\s+cli", r"codex",
    r"cursor", r"kimi", r"hermes", r"copilot",
    r"chatgpt", r"gpt-?\d+(?:\.\d+)?(?:-\w+)?", r"\bgpt\b",
    r"\bllm\b", r"\bai\s+assistant\b", r"\bassistant\b",
    r"anthropic", r"openai", r"moonshot", r"gemini", r"nvidia", r"nemotron",
    r"the\s+agent", r"this\s+agent", r"the\s+ai\b", r"as\s+an\s+ai\b",
]
_IDENTITY_RE = re.compile("|".join(_IDENTITY_TERMS), re.IGNORECASE)

# Leading sentence subject to drop for a neutral, impersonal voice.
_LEADING_SUBJECT_RE = re.compile(
    r"^(?:i|we|the\s+agent|the\s+assistant)\s+(?=[a-z])",
    re.IGNORECASE,
)

_BULLET_RE = re.compile(r"^(\s*(?:[-*•]\s*)?)(.*)$")
_ORPHAN_POSSESSIVE_RE = re.compile(r"(^|\s)['’]s\b")


def _recapitalize(s: str) -> str:
    """Uppercase the first alphabetic character (scrubbing often exposes a new one)."""
    for i, ch in enumerate(s):
        if ch.isalpha():
            return s[:i] + ch.upper() + s[i + 1:]
    return s


def _scrub_body(body: str) -> str:
    s = _IDENTITY_RE.sub("", body)
    # "Claude's analysis" -> after removal "'s analysis" -> drop the orphan possessive
    s = _ORPHAN_POSSESSIVE_RE.sub(" ", s)
    # Drop a leading subject pronoun for neutral voice ("I fixed" -> "fixed").
    s = _LEADING_SUBJECT_RE.sub("", s)
    # Tidy the punctuation/whitespace the removals leave behind.
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)        # " ," -> ","
    s = re.sub(r"([,;:])(?:\s*\1)+", r"\1", s)     # ", ," -> ","
    s = re.sub(r"\s{2,}", " ", s)                  # collapse runs of spaces
    s = re.sub(r"^[\s,;:.\-]+", "", s)             # leading junk
    return _recapitalize(s.strip())


def scrub_identity(text: str) -> str:
    """Remove tool/agent/vendor identity and neutralize voice.

    Idempotent and never raises. Preserves a leading bullet marker per line so a
    bulleted fallback summary stays bulleted.
    """
    if not text:
        return text
    out: list[str] = []
    for line in text.split("\n"):
        m = _BULLET_RE.match(line)
        prefix, body = m.group(1), m.group(2)
        scrubbed = _scrub_body(body)
        # Drop a line that became empty (e.g. it was only a tool name).
        if not scrubbed:
            continue
        out.append(f"{prefix}{scrubbed}" if prefix.strip() else scrubbed)
    return "\n".join(out).strip()


def scrub_entries(entries: list[str]) -> list[str]:
    """Scrub a list of raw worklog entries, dropping any that scrub to empty."""
    cleaned = [scrub_identity(e) for e in entries]
    return [c for c in cleaned if c]
