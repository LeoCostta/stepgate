import json

import pytest

from stepgate.model import CorruptStateError, Session, StepgateError
from stepgate.store import Store
from tests.conftest import run


def test_find_walks_up_to_parent(project):
    nested = project / "src" / "deep"
    nested.mkdir(parents=True)
    store = Store.find(nested)
    assert store.root == project


def test_find_without_init_raises(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(StepgateError, match="stepgate init"):
        Store.find()


def test_session_name_allocation_is_sequential(project):
    store = Store.find(project)
    first = store.new_session_name("claude")
    assert first.startswith("claude-") and first.endswith("-1")
    store.save_session(Session(name=first, agent="claude"))
    assert store.new_session_name("claude").endswith("-2")
    # other agents are numbered independently
    assert store.new_session_name("codex").endswith("-1")


def test_corrupt_session_file_gives_clear_error(project, capsys, plan_file):
    store = Store.find(project)
    run("propose", "--agent", "claude", "--file", str(plan_file))
    victim = next(store.sessions_dir.glob("claude-*.json"))
    victim.write_text("{ not json", encoding="utf-8")
    with pytest.raises(CorruptStateError) as exc:
        store.load_session(victim.stem)
    assert str(victim) in str(exc.value)
    assert "manually" in str(exc.value)


def test_corrupt_session_via_cli_exits_1_without_traceback(project, plan_file, capsys):
    run("propose", "--agent", "claude", "--file", str(plan_file))
    store = Store.find(project)
    victim = next(store.sessions_dir.glob("claude-*.json"))
    victim.write_text("{ not json", encoding="utf-8")
    assert run("approve", "--agent", "claude") == 1
    err = capsys.readouterr().err
    assert "stepgate: error:" in err
    assert "Traceback" not in err


def test_history_is_append_only(project, plan_file):
    store = Store.find(project)
    run("propose", "--agent", "claude", "--file", str(plan_file))
    before = store.history_path.read_text(encoding="utf-8")
    run("approve", "--agent", "claude")
    after = store.history_path.read_text(encoding="utf-8")
    assert after.startswith(before)  # old lines never rewritten
    events = [json.loads(l)["event"] for l in after.splitlines() if l.strip()]
    assert events == ["propose", "approve"]


def test_config_created_by_init_has_minimum_fields(project):
    store = Store.find(project)
    config = json.loads(store.config_path.read_text(encoding="utf-8"))
    assert set(config) >= {"project_name", "agents", "verify_command"}
    assert config["project_name"] == project.name
