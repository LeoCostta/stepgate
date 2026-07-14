"""Lifecycle commands: propose, approve, reject, exec-log, verify, close,
abandon, next. These validate the proposal state machine; they never block
or restrict edits to the project's own code."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rich.text import Text

from stepgate import render
from stepgate.model import (
    APPROVED,
    PENDING,
    Proposal,
    Session,
    StepgateError,
    validate_plan,
)
from stepgate.store import Store

UNKNOWN_AGENT = "unknown"


def _agent_or_fallback(args) -> str:
    return args.agent or UNKNOWN_AGENT


def resolve_session(store: Store, args, *, active_only: bool = True) -> Session:
    """Resolve which session a command targets.

    Priority: explicit --session > latest session of --agent > the single
    session with an active proposal, if there is exactly one.
    """
    if getattr(args, "session", None):
        return store.load_session(args.session)
    if args.agent:
        session = store.latest_session_for_agent(args.agent)
        if session is None:
            raise StepgateError(
                f"No session found for agent '{args.agent}'. "
                "Start one with 'stepgate propose'."
            )
        return session
    candidates = [s for s in store.iter_sessions() if not active_only or s.has_active_proposal]
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise StepgateError(
            "No session with an active proposal was found. "
            "Start one with 'stepgate propose'."
        )
    names = ", ".join(s.name for s in candidates)
    raise StepgateError(
        f"Multiple sessions are active ({names}). "
        "Pass --agent <name> or --session <name> to pick one."
    )


def _overlap_warnings(store: Store, current: Session) -> None:
    """Warn (never block) when active proposals across sessions share files."""
    if not current.has_active_proposal:
        return
    mine = set(current.proposal.plan["where"])
    for other in store.iter_sessions():
        if other.name == current.name or not other.has_active_proposal:
            continue
        if other.proposal.state not in (PENDING, APPROVED):
            continue
        shared = mine & set(other.proposal.plan["where"])
        if shared:
            render.warn(
                f"scope overlap with session '{other.name}' "
                f"({other.proposal.state}): {', '.join(sorted(shared))}. "
                "This is informational only - nothing is blocked."
            )


def _transition(store: Store, args, action: str, data: dict) -> Session:
    session = resolve_session(store, args)
    if session.proposal is None:
        raise StepgateError(
            f"Session '{session.name}' has no proposal. "
            "Start one with 'stepgate propose'."
        )
    new_state = session.proposal.apply(action, data)
    store.save_session(session)
    store.append_history(session.name, session.agent, action, data)
    render.info(
        f"[bold magenta]{session.name}[/] :: {action} -> "
        f"[{render.STATE_STYLES.get(new_state, 'bold')}]{new_state}[/]"
    )
    return session


# -- commands ---------------------------------------------------------------


def cmd_propose(args) -> int:
    store = Store.find()
    plan_path = Path(args.file)
    if not plan_path.exists():
        raise StepgateError(f"Plan file not found: {plan_path}")
    try:
        raw = json.loads(plan_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise StepgateError(f"Plan file is not valid JSON: {plan_path} ({exc})") from exc
    plan = validate_plan(raw)

    agent = _agent_or_fallback(args)
    if not args.agent:
        render.warn(
            "no --agent flag given; using the fallback session name "
            f"'{UNKNOWN_AGENT}-...'. Pass --agent claude|codex|... to keep "
            "session names readable."
        )

    session = None if args.new_session else store.latest_session_for_agent(agent)
    if session is not None and session.has_active_proposal:
        raise StepgateError(
            f"Session '{session.name}' already has an active proposal in state "
            f"{session.proposal.state}. Close, reject, or abandon it first - "
            "or pass --new-session to start a parallel session."
        )
    if session is None:
        session = Session(name=store.new_session_name(agent), agent=agent)

    session.proposal = Proposal(plan=plan)
    session.pending_suggestion = None
    store.save_session(session)
    store.append_history(session.name, session.agent, "propose", {"plan": plan})

    render.console.print(render.proposal_panel(session.name, session.proposal.to_dict()))
    render.info(
        f"Proposal registered as [bold yellow]PENDING[/] in session "
        f"[bold magenta]{session.name}[/]. Waiting for approval "
        "('stepgate approve' or 'stepgate reject')."
    )
    _overlap_warnings(store, session)
    return 0


def cmd_approve(args) -> int:
    store = Store.find()
    data: dict = {}
    if args.adjust:
        if args.scope:
            data["scope"] = [p.strip() for p in args.scope.split(",") if p.strip()]
        if args.note:
            data["note"] = args.note
        if not data:
            raise StepgateError("--adjust requires --scope and/or --note describing the adjustment.")
    session = _transition(store, args, "approve", data)
    if args.adjust and data.get("scope"):
        session.proposal.plan["where"] = data["scope"]
        store.save_session(session)
    render.info(
        "Approval covers this micro-change only - it is not a blanket "
        "approval for the rest of the task."
    )
    return 0


def cmd_reject(args) -> int:
    store = Store.find()
    _transition(store, args, "reject", {"note": args.note})
    return 0


def _git_diff_stat(root: Path) -> str | None:
    """Best-effort git diff --stat capture. Never raises, never blocks."""
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            cwd=root, capture_output=True, text=True, timeout=15,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        pass
    return None


def cmd_exec_log(args) -> int:
    store = Store.find()
    data: dict = {"summary": args.summary}
    if args.files:
        data["files"] = [p.strip() for p in args.files.split(",") if p.strip()]
    diff_stat = _git_diff_stat(store.root)
    if diff_stat is not None:
        data["git_diff_stat"] = diff_stat
    _transition(store, args, "exec-log", data)
    if diff_stat:
        render.console.print(
            "[dim]git diff --stat captured as objective evidence:[/]\n" + diff_stat
        )
    return 0


def cmd_verify(args) -> int:
    store = Store.find()
    _transition(store, args, "verify", {"evidence": args.evidence})
    return 0


def cmd_close(args) -> int:
    store = Store.find()
    session = _transition(store, args, "close", {})
    session.closed_proposals += 1
    store.save_session(session)
    render.info(
        "Micro-change closed. Suggest the next step with 'stepgate next "
        "--suggest \"...\"' - but do not start it without a new approved proposal."
    )
    return 0


def cmd_abandon(args) -> int:
    store = Store.find()
    _transition(store, args, "abandon", {"reason": args.reason})
    render.info(
        "Session left cleanly. Nothing in the project or in other sessions "
        "is affected."
    )
    return 0


def cmd_next(args) -> int:
    store = Store.find()
    session = resolve_session(store, args, active_only=False)
    if args.suggest is None:
        if session.pending_suggestion:
            render.console.print(
                Text.assemble(
                    ("Suggested next step", "bold green"),
                    (f" ({session.name}): ", "dim"),
                    session.pending_suggestion,
                )
            )
        else:
            render.info(
                f"No next-step suggestion recorded in session "
                f"[bold magenta]{session.name}[/]. Record one with "
                "'stepgate next --suggest \"...\"'."
            )
        return 0
    session.pending_suggestion = args.suggest
    store.save_session(session)
    store.append_history(session.name, session.agent, "next-suggest", {"suggestion": args.suggest})
    render.info(
        f"Next-step suggestion recorded in session [bold magenta]{session.name}[/]. "
        "It will stay visible in 'stepgate status' until a new proposal is opened."
    )
    return 0
