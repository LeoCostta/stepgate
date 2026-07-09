import pytest

from stepgate.model import (
    ABANDONED,
    APPROVED,
    CLOSED,
    EXECUTED,
    PENDING,
    REJECTED,
    VERIFIED,
    InvalidTransitionError,
    Proposal,
    StepgateError,
    validate_plan,
)
from tests.conftest import PLAN


def make_proposal() -> Proposal:
    return Proposal(plan=validate_plan(PLAN))


def test_happy_path():
    p = make_proposal()
    assert p.state == PENDING
    assert p.apply("approve") == APPROVED
    assert p.apply("exec-log", {"summary": "done"}) == EXECUTED
    assert p.apply("verify", {"evidence": "tests pass"}) == VERIFIED
    assert p.apply("close") == CLOSED
    assert [e["action"] for e in p.events] == ["approve", "exec-log", "verify", "close"]


def test_reject_from_pending_only():
    p = make_proposal()
    assert p.apply("reject", {"note": "no"}) == REJECTED
    p2 = make_proposal()
    p2.apply("approve")
    with pytest.raises(InvalidTransitionError):
        p2.apply("reject", {"note": "too late"})


@pytest.mark.parametrize("action", ["exec-log", "verify", "close"])
def test_cannot_skip_steps(action):
    p = make_proposal()
    with pytest.raises(InvalidTransitionError):
        p.apply(action)


def test_abandon_from_any_non_terminal():
    for steps in ([], ["approve"], ["approve", "exec-log"], ["approve", "exec-log", "verify"]):
        p = make_proposal()
        for step in steps:
            p.apply(step)
        assert p.apply("abandon", {"reason": "session ended"}) == ABANDONED


def test_abandon_from_terminal_fails():
    p = make_proposal()
    p.apply("reject", {"note": "no"})
    with pytest.raises(InvalidTransitionError):
        p.apply("abandon", {"reason": "x"})


def test_plan_validation_requires_all_six_fields():
    for missing in PLAN:
        incomplete = {k: v for k, v in PLAN.items() if k != missing}
        with pytest.raises(StepgateError, match=missing):
            validate_plan(incomplete)


def test_plan_where_accepts_comma_separated_string():
    raw = dict(PLAN, where="a.ts, b.sql")
    assert validate_plan(raw)["where"] == ["a.ts", "b.sql"]


def test_plan_rejects_unknown_fields():
    with pytest.raises(StepgateError, match="unknown"):
        validate_plan(dict(PLAN, extra="nope"))
