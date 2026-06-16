from slate.jira.scrub import scrub_identity, scrub_entries

BANNED = [
    "claude", "codex", "cursor", "kimi", "hermes", "copilot", "chatgpt",
    "anthropic", "openai", "gemini", "nvidia", "the agent", "the assistant",
]


def _assert_clean(text: str):
    low = text.lower()
    for term in BANNED:
        assert term not in low, f"{term!r} leaked: {text!r}"


def test_strips_tool_name_and_neutralizes():
    out = scrub_identity("Claude implemented JWT validation")
    _assert_clean(out)
    assert out == "Implemented JWT validation"


def test_strips_first_person_subject():
    assert scrub_identity("I fixed the login redirect") == "Fixed the login redirect"
    assert scrub_identity("We refactored the auth module") == "Refactored the auth module"


def test_strips_the_agent_framing():
    out = scrub_identity("The agent investigated the failing test")
    _assert_clean(out)
    assert out == "Investigated the failing test"


def test_possessive_cleanup():
    out = scrub_identity("Claude's analysis found a race condition")
    _assert_clean(out)
    assert "race condition" in out.lower()


def test_multiword_tool_removed_whole():
    _assert_clean(scrub_identity("Used Claude Code to build the parser"))
    _assert_clean(scrub_identity("Codex CLI generated the migration"))


def test_models_and_vendors_removed():
    for s in ["Asked GPT-4o for help", "Ran via OpenAI", "Powered by Anthropic Claude",
              "Gemini summarized the diff", "nemotron drafted notes"]:
        _assert_clean(scrub_identity(s))


def test_bullet_preserved():
    out = scrub_identity("- Claude added rate limiting")
    assert out.startswith("- ")
    _assert_clean(out)


def test_line_that_is_only_identity_is_dropped():
    out = scrub_identity("Claude\nImplemented caching")
    assert out == "Implemented caching"


def test_idempotent():
    once = scrub_identity("Claude implemented JWT validation")
    assert scrub_identity(once) == once


def test_empty_and_none_safe():
    assert scrub_identity("") == ""
    assert scrub_identity(None) is None


def test_scrub_entries_drops_empties():
    out = scrub_entries(["Claude", "Fixed bug", "  "])
    assert out == ["Fixed bug"]


def test_clean_text_unchanged_in_meaning():
    out = scrub_identity("Implemented JWT validation; fixed login redirect.")
    assert "JWT validation" in out
    assert "login redirect" in out
