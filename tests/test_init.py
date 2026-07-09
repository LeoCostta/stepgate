import json

from stepgate.commands.init_cmd import END_MARKER, START_MARKER
from stepgate.model import Session
from stepgate.store import Store
from tests.conftest import run


def test_init_creates_layout(project):
    assert (project / ".stepgate" / "config.json").exists()
    assert (project / ".stepgate" / "sessions").is_dir()
    assert (project / ".stepgate" / "history.jsonl").exists()
    for name in ("AGENTS.md", "CLAUDE.md"):
        content = (project / name).read_text(encoding="utf-8")
        assert START_MARKER in content and END_MARKER in content


def test_init_appends_to_existing_file_preserving_content(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    hand_written = "# My project rules\n\nNever touch the legacy folder.\n"
    (tmp_path / "AGENTS.md").write_text(hand_written, encoding="utf-8")
    assert run("init") == 0
    content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert content.startswith(hand_written.rstrip("\n") + "\n")
    assert "Never touch the legacy folder." in content
    assert START_MARKER in content


def test_init_is_idempotent_and_updates_only_marker_block(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert run("init") == 0
    path = tmp_path / "CLAUDE.md"
    content = path.read_text(encoding="utf-8")
    # user writes before and after the block
    path.write_text("BEFORE\n" + content + "\nAFTER\n", encoding="utf-8")
    assert run("init") == 0
    updated = path.read_text(encoding="utf-8")
    assert updated.startswith("BEFORE\n")
    assert updated.rstrip().endswith("AFTER")
    assert updated.count(START_MARKER) == 1


def test_init_preserves_sessions_and_history(project, plan_file):
    run("propose", "--agent", "claude", "--file", str(plan_file))
    store = Store.find(project)
    history_before = store.history_path.read_text(encoding="utf-8")
    assert run("init") == 0
    assert store.history_path.read_text(encoding="utf-8") == history_before
    assert store.latest_session_for_agent("claude") is not None


def test_init_keeps_existing_config(project):
    store = Store.find(project)
    config = json.loads(store.config_path.read_text(encoding="utf-8"))
    config["verify_command"] = "pytest"
    store.config_path.write_text(json.dumps(config), encoding="utf-8")
    assert run("init") == 0
    assert json.loads(store.config_path.read_text(encoding="utf-8"))["verify_command"] == "pytest"


def test_init_references_guardrails_when_present(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "GUARDRAILS.md").write_text("# Domain rules\n", encoding="utf-8")
    assert run("init") == 0
    content = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert "GUARDRAILS.md" in content
