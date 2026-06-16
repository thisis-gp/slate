import json
import pytest
from slate.obsidian import vault
from slate.obsidian.vault import (
    resolve_vault_path, find_project_override, write_issue_doc, read_issue_doc,
    issue_doc_path, BEGIN, END,
)

CTX = {
    "task": {"state": "in_progress", "assigned_to": "guru", "priority": "high"},
    "decisions": [{"body": "use SQLite", "author": "codex"}],
    "worklogs": [{"summary": "wired the parser", "time_spent_seconds": 1800}],
    "transitions": [{"from_state": "todo", "to_state": "in_progress", "changed_by": "guru"}],
}


def test_env_vault_path(monkeypatch, tmp_path):
    monkeypatch.setenv("SLATE_VAULT_PATH", str(tmp_path))
    assert resolve_vault_path(start=tmp_path) == tmp_path


def test_project_override_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("SLATE_VAULT_PATH", str(tmp_path / "env"))
    repo = tmp_path / "repo"
    (repo / ".agents").mkdir(parents=True)
    (repo / ".agents" / "slate.json").write_text(
        json.dumps({"vault_path": str(tmp_path / "proj")})
    )
    sub = repo / "src" / "deep"
    sub.mkdir(parents=True)
    assert resolve_vault_path(start=sub) == tmp_path / "proj"


def test_no_config_returns_none(monkeypatch, tmp_path):
    monkeypatch.delenv("SLATE_VAULT_PATH", raising=False)
    assert resolve_vault_path(start=tmp_path) is None


def test_write_creates_scaffold(tmp_path):
    p = write_issue_doc("BX-3023", CTX, title="Build importer", vault=tmp_path)
    assert p == tmp_path / "slate" / "BX-3023.md"
    text = p.read_text(encoding="utf-8")
    assert "# BX-3023 — Build importer" in text
    assert BEGIN in text and END in text
    assert "use SQLite" in text
    assert "wired the parser" in text
    assert "todo → in_progress" in text
    assert "## Notes" in text


def test_resync_replaces_managed_preserves_freeform(tmp_path):
    p = write_issue_doc("BX-1", CTX, vault=tmp_path)
    # user appends freeform content below the managed block
    text = p.read_text(encoding="utf-8")
    text += "\nMy private design note about the parser.\n"
    p.write_text(text, encoding="utf-8")

    ctx2 = {**CTX, "task": {"state": "done", "assigned_to": "guru"},
            "decisions": [{"body": "switched to PG", "author": "claude"}]}
    write_issue_doc("BX-1", ctx2, vault=tmp_path)
    out = p.read_text(encoding="utf-8")

    assert "My private design note about the parser." in out  # freeform kept
    assert "switched to PG" in out                            # managed updated
    assert "use SQLite" not in out                            # old managed gone
    assert "**Status:** done" in out
    assert out.count(BEGIN) == 1                              # exactly one block


def test_prepends_block_when_missing(tmp_path):
    path = issue_doc_path("BX-9", vault=tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("# Pre-existing notes\n\nstuff I wrote\n", encoding="utf-8")
    write_issue_doc("BX-9", CTX, vault=tmp_path)
    out = path.read_text(encoding="utf-8")
    assert BEGIN in out
    assert "stuff I wrote" in out


def test_path_traversal_sanitized(tmp_path):
    p = issue_doc_path("../../etc/passwd", subfolder="../x", vault=tmp_path)
    # The resolved path must stay inside the vault (no escape via .. or /).
    assert tmp_path.resolve() in p.resolve().parents
    assert "/" not in p.name and "\\" not in p.name


def test_read_missing_returns_none(tmp_path):
    assert read_issue_doc("BX-404", vault=tmp_path) is None
