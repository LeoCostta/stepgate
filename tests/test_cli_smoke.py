"""End-to-end smoke test following the narrated scenario from the planning
document (section 11): propose -> show -> approve --adjust -> exec-log ->
verify -> close -> next --suggest -> status."""

import json

from stepgate.store import Store
from tests.conftest import PLAN, run


def read_state(project, agent="claude"):
    store = Store.find(project)
    session = store.latest_session_for_agent(agent)
    return session


def test_full_cycle(project, plan_file, capsys):
    assert run("propose", "--agent", "claude", "--file", str(plan_file)) == 0
    assert read_state(project).proposal.state == "PENDING"

    assert run("show", "--agent", "claude") == 0
    out = capsys.readouterr().out
    assert PLAN["what"] in out.replace("\n", " ")  # rendered as prose, not raw JSON
    assert '"what"' not in out

    assert run(
        "approve", "--agent", "claude", "--adjust",
        "--note", "rename the function to apply_sanity_loss_atomic",
    ) == 0
    assert read_state(project).proposal.state == "APPROVED"

    assert run(
        "exec-log", "--agent", "claude",
        "--summary", "migration + typing with the adjusted name",
        "--files", "migrations/013_sanity.sql,src/types.ts",
    ) == 0
    assert read_state(project).proposal.state == "EXECUTED"

    assert run("verify", "--agent", "claude", "--evidence", "type-check ok, concurrency test passed") == 0
    assert read_state(project).proposal.state == "VERIFIED"

    assert run("close", "--agent", "claude") == 0
    session = read_state(project)
    assert session.proposal.state == "CLOSED"
    assert session.closed_proposals == 1

    assert run("next", "--agent", "claude", "--suggest", "wire SalaJogo.tsx via supabase.rpc") == 0
    capsys.readouterr()
    assert run("status") == 0
    assert "supabase.rpc" in capsys.readouterr().out

    # suggestion is cleared by the next propose
    assert run("propose", "--agent", "claude", "--file", str(plan_file)) == 0
    assert read_state(project).pending_suggestion is None


def test_cannot_skip_states_via_cli(project, plan_file, capsys):
    run("propose", "--agent", "claude", "--file", str(plan_file))
    assert run("exec-log", "--agent", "claude", "--summary", "sneaky") == 1
    err = capsys.readouterr().err
    assert "APPROVED" in err and "PENDING" in err


def test_propose_without_agent_falls_back_to_unknown(project, plan_file):
    assert run("propose", "--file", str(plan_file)) == 0
    store = Store.find(project)
    session = store.latest_session_for_agent("unknown")
    assert session is not None
    assert session.proposal.state == "PENDING"


def test_second_propose_in_active_session_fails_clearly(project, plan_file, capsys):
    run("propose", "--agent", "claude", "--file", str(plan_file))
    assert run("propose", "--agent", "claude", "--file", str(plan_file)) == 1
    assert "active proposal" in capsys.readouterr().err


def test_concurrent_sessions_and_overlap_warning(project, plan_file, capsys):
    run("propose", "--agent", "claude", "--file", str(plan_file))
    assert run("propose", "--agent", "codex", "--file", str(plan_file)) == 0
    err = capsys.readouterr().err
    assert "overlap" in err
    # both sessions exist independently
    store = Store.find(project)
    names = {s.name for s in store.iter_sessions()}
    assert any(n.startswith("claude-") for n in names)
    assert any(n.startswith("codex-") for n in names)


def test_abandon_via_cli(project, plan_file):
    run("propose", "--agent", "claude", "--file", str(plan_file))
    run("approve", "--agent", "claude")
    assert run("abandon", "--agent", "claude", "--reason", "session interrupted") == 0
    assert read_state(project).proposal.state == "ABANDONED"


def test_reject_requires_note_and_records_it(project, plan_file):
    run("propose", "--agent", "claude", "--file", str(plan_file))
    assert run("reject", "--agent", "claude", "--note", "wrong approach") == 0
    store = Store.find(project)
    events = store.read_history()
    assert events[-1]["event"] == "reject"
    assert events[-1]["data"]["note"] == "wrong approach"


def test_history_filters(project, plan_file, capsys):
    run("propose", "--agent", "claude", "--file", str(plan_file))
    session_name = read_state(project).name
    capsys.readouterr()
    assert run("history", "--session", session_name) == 0
    assert session_name in capsys.readouterr().out
    assert run("history", "--session", "nope-2020-01-01-9") == 0
    assert "No history entries" in capsys.readouterr().out


def test_doctor_reports_corruption_without_fixing(project, plan_file, capsys):
    run("propose", "--agent", "claude", "--file", str(plan_file))
    store = Store.find(project)
    victim = next(store.sessions_dir.glob("claude-*.json"))
    victim.write_text("broken", encoding="utf-8")
    capsys.readouterr()
    assert run("doctor") == 1
    out = capsys.readouterr().out
    assert victim.name in out
    assert victim.read_text(encoding="utf-8") == "broken"  # untouched

    victim.write_text(json.dumps({"session": victim.stem, "agent": "claude"}), encoding="utf-8")
    assert run("doctor") == 0


def test_approve_adjust_scope_narrows_where(project, plan_file):
    run("propose", "--agent", "claude", "--file", str(plan_file))
    assert run(
        "approve", "--agent", "claude", "--adjust",
        "--scope", "migrations/013_sanity.sql", "--note", "migration only",
    ) == 0
    assert read_state(project).proposal.plan["where"] == ["migrations/013_sanity.sql"]
