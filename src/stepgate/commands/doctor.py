"""stepgate doctor: scan .stepgate/ and report problems without fixing
anything. A diagnostic tool, never a repair tool — and never a gate: even
when it finds problems, nothing else is blocked."""

from __future__ import annotations

import json

from stepgate import render
from stepgate.model import Session
from stepgate.store import Store


def cmd_doctor(args) -> int:
    store = Store.find()
    problems: list[str] = []

    if store.config_path.exists():
        try:
            config = json.loads(store.config_path.read_text(encoding="utf-8"))
            for key in ("project_name", "agents", "verify_command"):
                if key not in config:
                    problems.append(f"{store.config_path}: missing expected key '{key}'")
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            problems.append(f"{store.config_path}: not valid JSON ({exc})")
    else:
        problems.append(f"{store.config_path}: missing (run 'stepgate init' to recreate it)")

    if store.sessions_dir.is_dir():
        for path in sorted(store.sessions_dir.glob("*.json")):
            try:
                Session.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError) as exc:
                problems.append(f"{path}: corrupted or invalid ({exc.__class__.__name__}: {exc})")
    else:
        problems.append(f"{store.sessions_dir}: missing directory")

    if store.history_path.exists():
        for i, line in enumerate(
            store.history_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                json.loads(line)
            except json.JSONDecodeError:
                problems.append(f"{store.history_path}: invalid JSON at line {i}")
    else:
        problems.append(f"{store.history_path}: missing file")

    if not problems:
        render.info(f"[green]doctor: no problems found in {store.dir}[/]")
        return 0
    render.info(f"[yellow]doctor: found {len(problems)} problem(s) in {store.dir}:[/]")
    for problem in problems:
        render.info(f"  - {problem}")
    render.info(
        "[dim]stepgate never repairs state automatically - please inspect the "
        "files above manually. Other sessions and normal project work are "
        "not blocked by this.[/]"
    )
    return 1
