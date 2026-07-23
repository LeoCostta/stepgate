"""On-disk state for stepgate: .stepgate/ directory, sessions, history.

The file lock protects only stepgate's own internal state under .stepgate/.
It never touches, locks, or otherwise restricts the project's source code,
the user's editor, or git.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any, Iterator

from filelock import FileLock

from stepgate.model import CorruptStateError, Session, StepgateError, now_iso

STEPGATE_DIR = ".stepgate"
SESSION_NAME_RE = re.compile(r"^(?P<agent>.+)-(?P<date>\d{4}-\d{2}-\d{2})-(?P<seq>\d+)$")
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _validate_name(value: str, *, label: str) -> str:
    """Reject values that could escape sessions_dir when used in a path."""
    if not SAFE_NAME_RE.match(value) or ".." in value:
        raise StepgateError(
            f"Invalid {label} '{value}': must contain only letters, digits, "
            "'.', '-', and '_', with no path separators or '..' segments."
        )
    return value

DEFAULT_CONFIG = {
    "project_name": "",
    "agents": ["claude", "codex"],
    "verify_command": "",
}


class Store:
    def __init__(self, root: Path):
        self.root = root
        self.dir = root / STEPGATE_DIR
        self.sessions_dir = self.dir / "sessions"
        self.history_path = self.dir / "history.jsonl"
        self.config_path = self.dir / "config.json"
        self.lock = FileLock(str(self.dir / ".lock"), timeout=10)

    # -- discovery ---------------------------------------------------------

    @classmethod
    def find(cls, start: Path | None = None) -> "Store":
        """Locate .stepgate/ in the current directory or any parent."""
        current = (start or Path.cwd()).resolve()
        for candidate in [current, *current.parents]:
            if (candidate / STEPGATE_DIR).is_dir():
                return cls(candidate)
        raise StepgateError(
            "No .stepgate/ directory found in this directory or any parent. "
            "Run 'stepgate init' at the root of the project first."
        )

    def ensure_layout(self) -> None:
        self.dir.mkdir(exist_ok=True)
        self.sessions_dir.mkdir(exist_ok=True)
        if not self.history_path.exists():
            self.history_path.touch()

    # -- config ------------------------------------------------------------

    def load_config(self) -> dict[str, Any]:
        if not self.config_path.exists():
            return dict(DEFAULT_CONFIG)
        try:
            return json.loads(self.config_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise CorruptStateError(
                f"Config file is not valid JSON: {self.config_path}\n"
                f"  ({exc})\n"
                "Please inspect and fix it manually; stepgate never rewrites "
                "state on its own."
            ) from exc

    def write_config(self, config: dict[str, Any]) -> None:
        with self.lock:
            self.config_path.write_text(
                json.dumps(config, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    # -- sessions ----------------------------------------------------------

    def session_path(self, name: str) -> Path:
        _validate_name(name, label="session name")
        return self.sessions_dir / f"{name}.json"

    def load_session(self, name: str) -> Session:
        path = self.session_path(name)
        if not path.exists():
            raise StepgateError(f"Session '{name}' does not exist under {self.sessions_dir}.")
        return self._read_session_file(path)

    def _read_session_file(self, path: Path) -> Session:
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            return Session.from_dict(raw)
        except (json.JSONDecodeError, UnicodeDecodeError, KeyError, TypeError) as exc:
            raise CorruptStateError(
                f"Session file is corrupted or invalid: {path}\n"
                f"  ({exc.__class__.__name__}: {exc})\n"
                "Please inspect it manually; stepgate never repairs or "
                "rewrites state on its own. Other sessions are unaffected."
            ) from exc

    def iter_sessions(self) -> Iterator[Session]:
        """Yield all sessions, sorted by name. Corrupt files raise."""
        for path in sorted(self.sessions_dir.glob("*.json")):
            yield self._read_session_file(path)

    def save_session(self, session: Session) -> None:
        with self.lock:
            self.session_path(session.name).write_text(
                json.dumps(session.to_dict(), indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

    def new_session_name(self, agent: str) -> str:
        """Allocate the next human-readable session name for today."""
        _validate_name(agent, label="agent name")
        today = date.today().isoformat()
        prefix = f"{agent}-{today}-"
        seqs = [
            int(m.group("seq"))
            for p in self.sessions_dir.glob(f"{agent}-{today}-*.json")
            if (m := SESSION_NAME_RE.match(p.stem)) and m.group("agent") == agent
        ]
        return f"{prefix}{max(seqs, default=0) + 1}"

    def latest_session_for_agent(self, agent: str) -> Session | None:
        _validate_name(agent, label="agent name")
        paths = sorted(
            (p for p in self.sessions_dir.glob(f"{agent}-*.json")
             if (m := SESSION_NAME_RE.match(p.stem)) and m.group("agent") == agent),
            key=lambda p: p.stat().st_mtime,
        )
        if not paths:
            return None
        return self._read_session_file(paths[-1])

    # -- history (append-only) ----------------------------------------------

    def append_history(self, session: str, agent: str, event: str, data: dict[str, Any]) -> None:
        """Append one event line. history.jsonl is never rewritten or edited."""
        line = json.dumps(
            {"ts": now_iso(), "session": session, "agent": agent, "event": event, "data": data},
            ensure_ascii=False,
        )
        with self.lock:
            with self.history_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    def read_history(self) -> list[dict[str, Any]]:
        if not self.history_path.exists():
            return []
        entries = []
        for i, line in enumerate(
            self.history_path.read_text(encoding="utf-8").splitlines(), start=1
        ):
            if not line.strip():
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise CorruptStateError(
                    f"History file has an invalid entry at line {i}: {self.history_path}\n"
                    f"  ({exc})\n"
                    "Please inspect it manually; stepgate never rewrites history."
                ) from exc
        return entries
