"""Data model and state machine for stepgate proposals.

The state machine governs the lifecycle of a *proposal*, never the code
itself. Editing code without an open proposal is a legitimate flow and is
never treated as an error by stepgate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Proposal states
PENDING = "PENDING"
APPROVED = "APPROVED"
EXECUTED = "EXECUTED"
VERIFIED = "VERIFIED"
CLOSED = "CLOSED"
REJECTED = "REJECTED"
ABANDONED = "ABANDONED"

TERMINAL_STATES = {CLOSED, REJECTED, ABANDONED}

# action -> (required current state, next state)
TRANSITIONS = {
    "approve": (PENDING, APPROVED),
    "reject": (PENDING, REJECTED),
    "exec-log": (APPROVED, EXECUTED),
    "verify": (EXECUTED, VERIFIED),
    "close": (VERIFIED, CLOSED),
}

PLAN_FIELDS = ("what", "why", "where", "how", "expected_result", "verification")

PLAN_FIELD_LABELS = {
    "what": "What",
    "why": "Why",
    "where": "Where",
    "how": "How",
    "expected_result": "Expected result",
    "verification": "Verification",
}


class StepgateError(Exception):
    """User-facing error. The CLI prints its message without a traceback."""


class InvalidTransitionError(StepgateError):
    pass


class CorruptStateError(StepgateError):
    """Raised when a state file on disk cannot be read or parsed."""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def validate_plan(raw: Any) -> dict[str, Any]:
    """Validate a plan document: all six fields present and non-empty.

    ``where`` may be a list of files/areas or a comma-separated string;
    it is normalized to a list. All other fields are free-flowing prose.
    """
    if not isinstance(raw, dict):
        raise StepgateError("The plan file must contain a JSON object.")
    plan: dict[str, Any] = {}
    missing = []
    for name in PLAN_FIELDS:
        value = raw.get(name)
        if name == "where":
            if isinstance(value, str):
                value = [p.strip() for p in value.split(",") if p.strip()]
            if not isinstance(value, list) or not value:
                missing.append(name)
                continue
            plan[name] = [str(v) for v in value]
        else:
            if not isinstance(value, str) or not value.strip():
                missing.append(name)
                continue
            plan[name] = value.strip()
    if missing:
        raise StepgateError(
            "The plan is missing required fields: "
            + ", ".join(missing)
            + ". A micro-change plan must cover all six points "
            "(what, why, where, how, expected_result, verification) "
            "written as natural, flowing prose."
        )
    unknown = [k for k in raw if k not in PLAN_FIELDS]
    if unknown:
        raise StepgateError(
            "The plan contains unknown fields: " + ", ".join(sorted(unknown))
        )
    return plan


@dataclass
class Proposal:
    plan: dict[str, Any]
    state: str = PENDING
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    events: list[dict[str, Any]] = field(default_factory=list)

    def apply(self, action: str, data: dict[str, Any] | None = None) -> str:
        """Apply a lifecycle action, validating the state machine."""
        if action == "abandon":
            if self.state in TERMINAL_STATES:
                raise InvalidTransitionError(
                    f"Cannot abandon a proposal in terminal state {self.state}."
                )
            new_state = ABANDONED
        else:
            if action not in TRANSITIONS:
                raise InvalidTransitionError(f"Unknown action: {action}")
            required, new_state = TRANSITIONS[action]
            if self.state != required:
                raise InvalidTransitionError(
                    f"'{action}' requires a proposal in state {required}, "
                    f"but the active proposal is {self.state}."
                )
        self.state = new_state
        self.updated_at = now_iso()
        self.events.append({"ts": self.updated_at, "action": action, "data": data or {}})
        return new_state

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan,
            "state": self.state,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "events": self.events,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Proposal":
        return cls(
            plan=raw["plan"],
            state=raw["state"],
            created_at=raw.get("created_at", now_iso()),
            updated_at=raw.get("updated_at", now_iso()),
            events=raw.get("events", []),
        )


@dataclass
class Session:
    name: str
    agent: str
    created_at: str = field(default_factory=now_iso)
    proposal: Proposal | None = None
    pending_suggestion: str | None = None
    closed_proposals: int = 0

    @property
    def has_active_proposal(self) -> bool:
        return self.proposal is not None and self.proposal.state not in TERMINAL_STATES

    def to_dict(self) -> dict[str, Any]:
        return {
            "session": self.name,
            "agent": self.agent,
            "created_at": self.created_at,
            "proposal": self.proposal.to_dict() if self.proposal else None,
            "pending_suggestion": self.pending_suggestion,
            "closed_proposals": self.closed_proposals,
        }

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "Session":
        for key in ("session", "agent"):
            if not isinstance(raw.get(key), str):
                raise KeyError(key)
        proposal = raw.get("proposal")
        return cls(
            name=raw["session"],
            agent=raw["agent"],
            created_at=raw.get("created_at", now_iso()),
            proposal=Proposal.from_dict(proposal) if proposal else None,
            pending_suggestion=raw.get("pending_suggestion"),
            closed_proposals=raw.get("closed_proposals", 0),
        )
