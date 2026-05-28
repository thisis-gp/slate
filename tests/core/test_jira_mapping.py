from slate.jira.mapping import (
    DEFAULT_STATE_MAP,
    resolve_state_map,
    find_transition_id,
    format_worklog_started,
)


def test_resolve_state_map_with_none_returns_defaults():
    result = resolve_state_map(None)
    assert result == DEFAULT_STATE_MAP


def test_resolve_state_map_merges_overrides():
    override_json = '{"done": "Completed", "qa": "UAT"}'
    result = resolve_state_map(override_json)
    assert result["done"] == "Completed"
    assert result["qa"] == "UAT"
    assert result["todo"] == DEFAULT_STATE_MAP["todo"]


def test_resolve_state_map_ignores_invalid_json():
    result = resolve_state_map("not-json")
    assert result == DEFAULT_STATE_MAP


def test_find_transition_id_matches_to_name():
    transitions = [
        {"id": "11", "name": "Start", "to": {"name": "In Progress"}},
        {"id": "21", "name": "Close", "to": {"name": "Done"}},
    ]
    assert find_transition_id(transitions, "In Progress") == "11"
    assert find_transition_id(transitions, "Done") == "21"


def test_find_transition_id_is_case_insensitive():
    transitions = [{"id": "5", "name": "Mark Done", "to": {"name": "Done"}}]
    assert find_transition_id(transitions, "done") == "5"
    assert find_transition_id(transitions, "DONE") == "5"


def test_find_transition_id_returns_none_when_not_found():
    transitions = [{"id": "1", "name": "Start", "to": {"name": "In Progress"}}]
    assert find_transition_id(transitions, "Nonexistent") is None


def test_find_transition_id_empty_list_returns_none():
    assert find_transition_id([], "Done") is None


def test_format_worklog_started_produces_jira_format():
    result = format_worklog_started(0.0)
    assert result == "1970-01-01T00:00:00.000+0000"


def test_format_worklog_started_uses_utc():
    result = format_worklog_started(1748422800.0)
    assert result.endswith("+0000")
    assert "T" in result
    assert result.count(":") >= 2
