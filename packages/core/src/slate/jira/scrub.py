"""Identity scrubbing for Jira-bound worklog text.

Slate is a memory layer shared by several AI tools (Claude Code, Codex, Cursor,
Kimi, Hermes, …). Worklogs synced to Jira must read as the human's own work — no
tool, agent, or vendor names, and no "the agent did X" framing. We enforce this in
TWO layers:

  1. Entries go to Jira verbatim (no LLM rewrite); trivial lines are dropped by
     ``format_jira_comment`` below.
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
# Only the coding tools the owner works WITH. Model and vendor names (gpt-5-nano,
# LLM, Anthropic, Gemini) are left alone: the team builds AI products, so those
# words describe the work itself (calibrated on 734 real worklogs, 2026-11-06).
#
# "Claude" and "Cursor" are also product names here ("Claude Tag", "email via
# Claude", "Cursor Slack"), so bare mentions of them stay; they are removed only
# in tool-usage form: sentence subject, possessive, or "with/using Claude".
_IDENTITY_TERMS = [
    r"used\s+(?:claude\s+code|claude-code|claude|codex(?:\s+cli)?)\s+to",
    r"claude\s+code", r"claude-code",
    r"codex\s+cli", r"codex",
    r"kimi", r"hermes", r"copilot",
    r"ai\s+assistant", r"coding\s+agent",
    r"the\s+agent", r"this\s+agent", r"as\s+an\s+ai",
    # Product-name tools only in tool-usage form. "Cursor" only capitalized:
    # "pagination cursor" is engineering.
    r"(?:claude|(?-i:Cursor))['’]s",
    r"(?:with|using|by|asked|told|had|let)\s+(?:claude|(?-i:Cursor))",
]
# Boundaries on every term: "precursor", "feat/codex-x" and "e-codex" survive.
_IDENTITY_RE = re.compile(
    "|".join(rf"(?<![\w/-])(?:{t})(?![\w/-])" for t in _IDENTITY_TERMS),
    re.IGNORECASE,
)

# Leading sentence subject to drop for a neutral, impersonal voice. Includes the
# worklog owner's own name ("Guru spotted X" -> "Spotted X"): Jira already
# attributes the entry to him. Mid-sentence uses (a login name, a branch
# "feat/guru/bx-1") are left alone, since removing them breaks the sentence.
_LEADING_SUBJECT_RE = re.compile(
    r"^(?:i|we|the\s+agent|the\s+assistant|guru(?:priyan)?|claude|(?-i:Cursor))"
    r"\s+(?=[a-z])",
    re.IGNORECASE,
)

_BULLET_RE = re.compile(r"^(\s*(?:[-*•]\s*)?)(.*)$")
_ORPHAN_POSSESSIVE_RE = re.compile(r"(^|\s)['’]s\b")


_PLAIN_WORD_RE = re.compile(r"^[a-z]+[,.:;]?$")


def _recapitalize(s: str) -> str:
    """Uppercase a plain leading word ("fixed" -> "Fixed").

    Identifiers are left as written: "e2e", "2nd", "known_names", "gp-dev".
    """
    head, sep, rest = s.partition(" ")
    if _PLAIN_WORD_RE.match(head):
        return head[0].upper() + head[1:] + sep + rest
    return s


def _scrub_body(body: str) -> str:
    if re.fullmatch(r"\s*(?:claude|cursor)\s*[.:]?\s*", body, re.IGNORECASE):
        return ""  # a line that is only the tool name
    if not (_IDENTITY_RE.search(body) or _LEADING_SUBJECT_RE.search(body)):
        return body.strip()  # nothing to remove: leave punctuation and case alone
    s = _IDENTITY_RE.sub("", body)
    # "Claude's analysis" -> after removal "'s analysis" -> drop the orphan possessive
    s = _ORPHAN_POSSESSIVE_RE.sub(" ", s)
    # Drop a leading subject pronoun for neutral voice ("I fixed" -> "fixed").
    s = _LEADING_SUBJECT_RE.sub("", s)
    # Tidy the punctuation/whitespace the removals leave behind.
    s = re.sub(r"\s+([,.;:!?])(?=\s|$)", r"\1", s)  # " ," -> "," (not " .xlsb")
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


# ── Trivial-entry filter ──────────────────────────────────────────────────────
# Jira gets the human's worklog text as written (scrubbed), never an LLM rewrite.
# What we DO remove is noise: session start markers, status polls with no
# outcome, and PR/commit housekeeping. Calibrated on real slate worklogs.

# An entry that reports a result is kept even if it opens with "checked".
_OUTCOME_RE = re.compile(
    r"[:;]|\b(?:found|fixed|failing|fails|failed|broken|root\s+cause|because|"
    r"due\s+to|caused|confirmed|missing|regress\w*|blocked|error)\b",
    re.IGNORECASE,
)
_CHECK_RE = re.compile(
    r"^(?:checked|check|checking|looked\s+(?:at|into)|look\s+at|fetched|viewed|"
    r"asked(?:\s+for)?|what\s+is|what's|status\s+of)\b"
    r".*\b(?:pr|prs|pull\s+requests?|ci|build|checks?|pipeline|status|comments?|state|"
    r"jira|ticket|branch|logs?)\b",
    re.IGNORECASE,
)
# "Reviewed PR #7287 FHPL consolidation" is a code review (real work); only
# reading the comments on a PR is a poll.
_READ_COMMENTS_RE = re.compile(
    r"^(?:reviewed|went\s+through|read)\b.*\bcomments?\b", re.IGNORECASE)
# A bare start marker ("Started BX-3681 fix") is intent; a long clause that
# opens with "Started" is describing the work, so the marker must be short.
_START_RE = re.compile(
    r"^(?:started|starting|start|began|beginning|picked\s+up|resumed|resuming)\b",
    re.IGNORECASE)
_START_MAX_WORDS = 6
_TRIVIAL_RES = [
    # PR / commit housekeeping.
    re.compile(r"\b(?:pr|commit)\s+(?:title|description|message)s?\b.*\b(?:format|match)",
               re.IGNORECASE),
    re.compile(r"\bcommit(?:-message)?\s+(?:history|format)\b", re.IGNORECASE),
    re.compile(r"^time\s+correction\b", re.IGNORECASE),
    # Vague whole-clause summaries banned by the worklog rules.
    re.compile(
        r"^(?:reviewed|addressed|handled|went\s+through|worked\s+on|made|did)\s+"
        r"(?:the\s+|some\s+)?(?:reviewer\s+|review\s+|pr\s+)?"
        r"(?:comments?|code|ticket|task|changes|feedback|stuff|work)\.?$",
        re.IGNORECASE,
    ),
]


# AI-workflow mechanics ("recovered the handoff"). "prompt" and "session" are
# NOT here: they are product words (BX-4003 is prompt work). Even these only
# remove a SHORT clause, never a substantive one.
_AI_WORKFLOW_RE = re.compile(
    r"\b(?:sub-?agents?|transcripts?|handoff|hand-off|compaction|"
    r"context\s+window)\b",
    re.IGNORECASE,
)
_AI_WORKFLOW_MAX_WORDS = 5
_CHECK_MAX_WORDS = 14

# Clause boundaries: "; " always, ". " only before a capital/digit (keeps "v1.2", "e.g.").
_CLAUSE_SPLIT_RE = re.compile(r";\s+|(?<=\.)\s+(?=[A-Z0-9#])")


def _is_trivial_clause(c: str) -> bool:
    s = c.strip().lstrip("-*• ").strip().rstrip(".;").strip()
    if not s:
        return True
    words = len(s.split())
    # A status poll is short; a long "Reviewed ..." clause is describing work.
    if words <= _CHECK_MAX_WORDS and not _OUTCOME_RE.search(s) and (
            _CHECK_RE.search(s) or _READ_COMMENTS_RE.search(s)):
        return True
    if words <= _START_MAX_WORDS and _START_RE.search(s):
        return True
    if _AI_WORKFLOW_RE.search(s) and words <= _AI_WORKFLOW_MAX_WORDS:
        return True
    return any(r.search(s) for r in _TRIVIAL_RES)


def clean_entry(entry: str) -> str:
    """Drop trivial clauses from one worklog entry; keep the rest word for word.

    Returns "" when nothing reportable is left.
    """
    s = (entry or "").strip()
    if not s:
        return ""
    clauses = [c for c in _CLAUSE_SPLIT_RE.split(s) if c.strip()]
    kept = [c.strip() for c in clauses if not _is_trivial_clause(c)]
    if len(kept) == len(clauses):
        return s  # untouched: preserve original punctuation exactly
    if not kept:
        return ""
    out = " ".join(k if k.endswith((".", "!", "?")) else k + "." for k in kept)
    return _recapitalize(out)


def is_trivial(entry: str) -> bool:
    """True for worklog lines that carry no reportable work (see patterns above)."""
    return clean_entry(entry) == ""


def format_jira_comment(entries: list[str], limit: int = 20) -> str:
    """Build the Jira worklog comment from already-scrubbed entries.

    Verbatim (no rewriting), de-duplicated, trivial clauses and lines dropped.
    If every line is trivial the originals are kept, so logged time never goes
    up blank. One entry is returned as a sentence; several as a bulleted list.
    """
    seen: set[str] = set()
    uniq: list[str] = []
    for e in entries:
        e = (e or "").strip()
        if e and e not in seen:
            seen.add(e)
            uniq.append(e)
    kept = [c for c in (clean_entry(e) for e in uniq) if c] or uniq
    kept = kept[:limit]
    if len(kept) == 1:
        return kept[0]
    return "\n".join(f"- {e}" for e in kept)


# ── Write-time check ──────────────────────────────────────────────────────────
# The push-time cleaner above is a backstop. The real fix is refusing a bad
# summary when it is written, so the agent rewrites it while it still knows
# what was done.

WORKLOG_MIN_WORDS = 6
WORKLOG_FORMAT_HINT = (
    "Write it for a manager reading Jira: what was done (specific), the key "
    "finding or root cause, artifacts (PR #, doc, query), outcome or next step. "
    "1-3 sentences, no tool or model names, no first person, no status checks."
)


def worklog_problems(summary: str) -> list[str]:
    """Reasons a worklog summary is not fit for Jira. Empty list means fine."""
    s = (summary or "").strip()
    problems: list[str] = []
    if len(s.split()) < WORKLOG_MIN_WORDS:
        problems.append(f"too short: say what was done in at least {WORKLOG_MIN_WORDS} words")
    for line in s.splitlines():
        body = _BULLET_RE.match(line).group(2)
        hit = _IDENTITY_RE.search(body) or _LEADING_SUBJECT_RE.search(body)
        if hit:
            problems.append(
                f"names a tool or person ({hit.group(0).strip()!r}): state the work itself")
            break
    if s and not problems and is_trivial(s):
        problems.append(
            "only status checks, start markers or PR/commit housekeeping: no reportable work")
    return problems
