"""Read-only views: show, status, history."""

from __future__ import annotations

from datetime import datetime

from rich.table import Table
from rich.text import Text

from stepgate import render
from stepgate.commands.lifecycle import resolve_session
from stepgate.model import APPROVED, PENDING, StepgateError, TERMINAL_STATES
from stepgate.store import Store


def cmd_show(args) -> int:
    store = Store.find()
    session = resolve_session(store, args, active_only=False)
    if session.proposal is None:
        raise StepgateError(f"Session '{session.name}' has no proposal to show.")
    render.console.print(render.proposal_panel(session.name, session.proposal.to_dict()))
    return 0


def _overlaps(sessions) -> list[str]:
    active = [s for s in sessions if s.has_active_proposal and s.proposal.state in (PENDING, APPROVED)]
    messages = []
    for i, a in enumerate(active):
        for b in active[i + 1:]:
            shared = set(a.proposal.plan["where"]) & set(b.proposal.plan["where"])
            if shared:
                messages.append(
                    f"sessions '{a.name}' and '{b.name}' both touch: "
                    + ", ".join(sorted(shared))
                )
    return messages


def cmd_status(args) -> int:
    store = Store.find()
    sessions = list(store.iter_sessions())
    if not sessions:
        render.info("No sessions yet. Start one with 'stepgate propose'.")
        return 0

    table = Table(title="stepgate — project status", border_style="dim")
    table.add_column("Session", style="magenta")
    table.add_column("State")
    table.add_column("Closed", justify="right")
    table.add_column("Last activity", style="dim")
    for session in sessions:
        if session.proposal is None:
            state = Text("no proposal", style="dim")
            last = session.created_at
        else:
            state = render.state_text(session.proposal.state)
            last = session.proposal.updated_at
        table.add_row(session.name, state, str(session.closed_proposals), last)
    render.console.print(table)

    focus = None
    if getattr(args, "session", None) or args.agent:
        focus = resolve_session(store, args, active_only=False)
    elif len(sessions) == 1:
        focus = sessions[0]
    if focus is not None:
        if focus.pending_suggestion:
            render.console.print(
                Text.assemble(
                    ("Suggested next step", "bold green"),
                    (f" ({focus.name}): ", "dim"),
                    focus.pending_suggestion,
                )
            )
        if focus.proposal and focus.proposal.state not in TERMINAL_STATES:
            render.console.print(render.proposal_panel(focus.name, focus.proposal.to_dict()))
    else:
        for session in sessions:
            if session.pending_suggestion:
                render.console.print(
                    Text.assemble(
                        ("Suggested next step", "bold green"),
                        (f" ({session.name}): ", "dim"),
                        session.pending_suggestion,
                    )
                )

    for message in _overlaps(sessions):
        render.warn("scope overlap — " + message + ". Informational only, nothing is blocked.")
    return 0


def cmd_history(args) -> int:
    store = Store.find()
    entries = store.read_history()
    if args.session:
        entries = [e for e in entries if e.get("session") == args.session]
    if args.since:
        try:
            since = datetime.fromisoformat(args.since)
        except ValueError as exc:
            raise StepgateError(
                f"--since must be an ISO date like 2026-07-09 (got '{args.since}')."
            ) from exc
        if since.tzinfo is None:
            since = since.astimezone()
        entries = [
            e for e in entries
            if datetime.fromisoformat(e["ts"]) >= since
        ]
    if not entries:
        render.info("No history entries match.")
        return 0
    table = Table(title="stepgate — history (append-only)", border_style="dim")
    table.add_column("When", style="dim", no_wrap=True)
    table.add_column("Session", style="magenta", no_wrap=True)
    table.add_column("Event")
    table.add_column("Detail", overflow="fold")
    for entry in entries:
        data = entry.get("data") or {}
        detail = (
            data.get("summary") or data.get("evidence") or data.get("note")
            or data.get("reason") or data.get("suggestion")
            or (data.get("plan", {}).get("what") if isinstance(data.get("plan"), dict) else "")
            or ""
        )
        table.add_row(entry["ts"], entry["session"], entry["event"], detail)
    render.console.print(table)
    return 0
