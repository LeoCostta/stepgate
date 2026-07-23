"""stepgate command-line interface.

All commands are non-interactive by design (no prompts, no confirmations) so
they behave identically in a terminal, a desktop app, or an IDE side-panel
extension. User-facing errors are printed as clear messages, never as raw
Python tracebacks.
"""

from __future__ import annotations

import argparse
import sys

from stepgate import __version__
from stepgate.model import StepgateError


def _add_session_flags(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--agent", help="calling agent name (e.g. claude, codex)")
    parser.add_argument("--session", help="explicit session name to target")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stepgate",
        description=(
            "Step-gated micro-change protocol for coding agents: propose, "
            "approve, execute, verify - one small step at a time. stepgate "
            "structures the flow; it never blocks your code, your commits, "
            "or your git."
        ),
    )
    parser.add_argument("--version", action="version", version=f"stepgate {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create .stepgate/ and inject the agent instruction block")
    p.add_argument("--guardrails", help="path to an existing domain guardrails doc to reference")

    p = sub.add_parser("propose", help="register a micro-change plan (state: PENDING)")
    p.add_argument("--file", required=True, help="JSON file with the six plan fields")
    p.add_argument("--new-session", action="store_true", help="start a fresh session")
    _add_session_flags(p)

    p = sub.add_parser("show", help="show the active proposal rendered as prose")
    _add_session_flags(p)

    p = sub.add_parser("approve", aliases=["aprovar"], help="PENDING -> APPROVED")
    p.add_argument("--adjust", action="store_true", help="approve with an adjusted/reduced scope")
    p.add_argument("--scope", help="comma-separated adjusted scope (files/areas)")
    p.add_argument("--note", help="note describing the adjustment")
    _add_session_flags(p)

    p = sub.add_parser("reject", aliases=["rejeitar"], help="PENDING -> REJECTED")
    p.add_argument("--note", required=True, help="reason for rejection")
    _add_session_flags(p)

    p = sub.add_parser("exec-log", help="APPROVED -> EXECUTED (consolidated summary)")
    p.add_argument("--summary", required=True, help="what was done, consolidated")
    p.add_argument("--files", help="comma-separated files that were touched")
    _add_session_flags(p)

    p = sub.add_parser("verify", help="EXECUTED -> VERIFIED")
    p.add_argument("--evidence", required=True, help="tests/runs/evidence demonstrating the result")
    p.add_argument("--suggest", help="the natural next step for this cycle; 'close' surfaces it when the cycle is closed")
    _add_session_flags(p)

    p = sub.add_parser("close", aliases=["fechar"], help="VERIFIED -> CLOSED (surfaces the cycle's recorded next step)")
    _add_session_flags(p)

    p = sub.add_parser("abandon", help="any non-terminal state -> ABANDONED")
    p.add_argument("--reason", required=True, help="why the proposal is being abandoned")
    _add_session_flags(p)

    p = sub.add_parser("next", aliases=["proximo"], help="show or record a next-step suggestion (does not open a proposal)")
    p.add_argument("--suggest", help="the suggested next step; omit to show the current one")
    _add_session_flags(p)

    p = sub.add_parser("status", help="current session state + aggregated project view")
    _add_session_flags(p)

    p = sub.add_parser("history", help="chronological, cross-session log")
    p.add_argument("--session", help="filter by session name")
    p.add_argument("--since", help="filter by ISO date (e.g. 2026-07-09)")

    sub.add_parser("doctor", help="scan .stepgate/ and report problems (never fixes anything)")

    p = sub.add_parser("exit", aliases=["sair"], help="end the working session: list VERIFIED cycles awaiting close, suggest nothing")
    _add_session_flags(p)

    return parser


def main(argv: list[str] | None = None) -> int:
    # Consoles with limited encodings (e.g. cp1252 on legacy Windows) must
    # degrade output gracefully, never crash with a UnicodeEncodeError.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(errors="replace")
            except (OSError, ValueError):
                pass

    args = build_parser().parse_args(argv)

    from stepgate.commands import doctor, init_cmd, lifecycle, views

    handlers = {
        "init": init_cmd.cmd_init,
        "propose": lifecycle.cmd_propose,
        "show": views.cmd_show,
        "approve": lifecycle.cmd_approve,
        "reject": lifecycle.cmd_reject,
        "exec-log": lifecycle.cmd_exec_log,
        "verify": lifecycle.cmd_verify,
        "close": lifecycle.cmd_close,
        "abandon": lifecycle.cmd_abandon,
        "next": lifecycle.cmd_next,
        "status": views.cmd_status,
        "history": views.cmd_history,
        "doctor": doctor.cmd_doctor,
        "exit": lifecycle.cmd_exit,
    }
    # argparse fills args.command with the alias actually typed, so map the
    # convenience aliases back to their canonical command name.
    aliases = {
        "aprovar": "approve", "rejeitar": "reject", "fechar": "close",
        "proximo": "next", "sair": "exit",
    }
    command = aliases.get(args.command, args.command)
    try:
        return handlers[command](args)
    except StepgateError as exc:
        print(f"stepgate: error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
