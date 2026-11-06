from slate.jira.scrub import (
    scrub_identity, scrub_entries, clean_entry, is_trivial, format_jira_comment,
)

BANNED = [
    "claude", "codex", "cursor", "kimi", "hermes", "copilot", "the agent", "the assistant",
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


def test_product_model_names_kept():
    # The team builds AI products: model and vendor names describe the work.
    for t in ["Ran gpt-5-nano staging test", "Disabled LLM query expansion",
              "Enabled the Anthropic diagnosis path", "Evaluated Claude Tag vs Cursor Slack",
              "Per-campaign email via Claude"]:
        assert scrub_identity(t) == t


def test_claude_removed_in_tool_usage_form():
    assert scrub_identity("Paired with Claude on the migration") == "Paired on the migration"
    assert scrub_identity("Found Codex's BX-1 work already merged") == "Found BX-1 work already merged"


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


def test_unchanged_text_keeps_case_and_punctuation():
    for t in ["2nd PR review: guarded null user", "e2e validated flag", "knex ? binding",
              "known_names deny-list wired", "Opened .xlsb parser"]:
        assert scrub_identity(t) == t
        assert clean_entry(t) == t


def test_owner_name_only_dropped_as_leading_subject():
    assert scrub_identity("Guru spotted the stale cache") == "Spotted the stale cache"
    assert scrub_identity("Pushed feat/guru/bx-1 signed in as gurupriyan") == (
        "Pushed feat/guru/bx-1 signed in as gurupriyan")


def test_word_boundaries_and_cursor_case():
    assert scrub_identity("Fixed pagination cursor reset") == "Fixed pagination cursor reset"
    assert scrub_identity("Added precursor step") == "Added precursor step"
    assert scrub_identity("Cursor generated the stub") == "Generated the stub"


def test_status_polls_are_trivial():
    for t in ["Checked PR status", "what is PR status", "Checked the latest PR review comments and CI state",
              "Reviewed the comments", "Started BX-3681 fix", "Time correction: add 90m",
              "Updated monorepo PR title to match existing BX title format"]:
        assert is_trivial(t), t


def test_real_work_is_not_trivial():
    for t in ["Reviewed PR #7287 FHPL master-claim consolidation",
              "Checked PR CI: unit tests failing on null org id",
              "Started the full 346-PDF comparison of markitdown vs pdfplumber extraction paths",
              "Reworked the rejection-reason prompt twice",
              "Thread-safety verified for the memory session store"]:
        assert not is_trivial(t), t


def test_clean_entry_drops_only_trivial_clauses():
    out = clean_entry("Checked PR status; fixed the null org id crash in the ecard handler")
    assert out == "Fixed the null org id crash in the ecard handler."
    assert clean_entry("Recovered BX-4229 handoff; copied the banner checks") == (
        "Copied the banner checks.")


def test_format_jira_comment():
    assert format_jira_comment(["Fixed X", "Fixed X", "Checked PR status"]) == "Fixed X"
    assert format_jira_comment(["Fixed X", "Added Y"]) == "- Fixed X" + chr(10) + "- Added Y"
    # all trivial: keep the originals so logged time never goes up blank
    assert format_jira_comment(["Checked PR status"]) == "Checked PR status"
