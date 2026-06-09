"""Multi-provider LLM summarizer for slate's Jira worklog sync.

Tries providers in order — Moonshot/Kimi (primary), then NVIDIA Nemotron, then
Gemini — each via an OpenAI-compatible ``/chat/completions`` endpoint. If no key is
configured or every provider fails, falls back to a plain de-duplicated bullet list,
so the daily sync never blocks on the LLM.

Configure via env (only the primary key is required; the rest are fallbacks):
    MOONSHOT_API_KEY   (+ optional MOONSHOT_BASE_URL / MOONSHOT_MODEL)
    NVIDIA_API_KEY     (+ optional NVIDIA_BASE_URL   / NVIDIA_MODEL)
    GEMINI_API_KEY     (+ optional GEMINI_BASE_URL   / GEMINI_MODEL)
"""
from __future__ import annotations
import os
import re
import httpx
from slate.jira.scrub import scrub_identity

_SYSTEM = (
    "You summarize a software engineer's day of work on a single Jira issue into one "
    "concise worklog note (3-6 lines). Be factual and specific; merge related items; "
    "drop duplicates and noise. Do not invent or inflate work beyond the notes given. "
    "VOICE: write in a neutral, impersonal voice that states the work itself — e.g. "
    "'Implemented JWT validation; fixed the login redirect.' Do NOT use a subject: no "
    "'I', no 'we', no 'the engineer'. NEVER mention any AI tool, assistant, agent, "
    "model, or vendor by name (e.g. Claude, Codex, Cursor, Kimi, Hermes, GPT, "
    "ChatGPT, Copilot, Anthropic, OpenAI) and never write 'the agent'/'the assistant' "
    "— the reader must see only human engineering work. "
    "CRITICAL: output ONLY the note text itself — never start with 'Here is', 'Sure', "
    "'Below is' or any preamble; no headings, no surrounding quotes, no sign-off."
)


def _providers() -> list[tuple[str, str, str, str]]:
    """(name, api_key, base_url, model) — order = fallback priority."""
    return [
        ("moonshot", os.getenv("MOONSHOT_API_KEY", ""),
         os.getenv("MOONSHOT_BASE_URL", "https://api.moonshot.ai/v1"),
         os.getenv("MOONSHOT_MODEL", "kimi-k2-0905-preview")),
        ("nvidia", os.getenv("NVIDIA_API_KEY", ""),
         os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1"),
         os.getenv("NVIDIA_MODEL", "nvidia/llama-3.3-nemotron-super-49b-v1.5")),
        ("gemini", os.getenv("GEMINI_API_KEY", ""),
         os.getenv("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai"),
         os.getenv("GEMINI_MODEL", "gemini-2.0-flash")),
    ]


async def _chat(base: str, key: str, model: str, system: str, user: str) -> str:
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(
            f"{base.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
                "max_tokens": 400,
            },
        )
        r.raise_for_status()
        data = r.json()
        return (data["choices"][0]["message"]["content"] or "").strip()


def _plain(blocks: list[str]) -> str:
    seen: set[str] = set()
    out: list[str] = []
    for b in blocks:
        b = b.strip()
        if b and b not in seen:
            seen.add(b)
            out.append(f"- {b}")
    return "\n".join(out[:12])


def _clean(text: str) -> str:
    """Strip preamble lines / wrapping quotes that smaller models sometimes add."""
    t = (text or "").strip()
    lines = t.split("\n")
    if lines and re.match(r"(?i)^\s*(here(?:'s| is)|below is|sure[,!]?|okay|note)\b.*:?\s*$", lines[0]):
        lines = lines[1:]
    t = "\n".join(lines).strip()
    if len(t) >= 2 and t[0] in "\"'" and t[-1] in "\"'":
        t = t[1:-1].strip()
    return t


async def summarize_worklog(jira_key: str, entries: list[str], total_minutes: int) -> tuple[str, str]:
    """Summarize a day's run notes for one Jira issue.

    Returns ``(summary_text, provider_name)``. Never raises — on total failure it
    returns the plain concatenation with provider ``"concat"``.
    """
    if not entries:
        return "", "none"
    user = (
        f"Jira issue: {jira_key}\n"
        f"Total time logged today: {total_minutes} minutes\n\n"
        f"Raw run notes from agents:\n" + "\n".join(f"- {e}" for e in entries)
    )
    for name, key, base, model in _providers():
        if not key:
            continue
        try:
            out = scrub_identity(_clean(await _chat(base, key, model, _SYSTEM, user)))
            if out:
                return out, name
        except Exception:
            continue
    return scrub_identity(_plain(entries)), "concat"
