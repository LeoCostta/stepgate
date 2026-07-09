import json

import pytest

from stepgate.cli import main


PLAN = {
    "what": "Create an atomic Postgres function for the Sanity decrement.",
    "why": "Concurrent losses currently overwrite each other; this must land before any UI change.",
    "where": ["migrations/013_sanity.sql", "src/types.ts"],
    "how": "Follow the same pattern already used in user_can_access_mesa.",
    "expected_result": "Concurrent sanity losses no longer overwrite each other.",
    "verification": "Simulated concurrency test, type-check, npm test.",
}


@pytest.fixture
def project(tmp_path, monkeypatch):
    """An initialized stepgate project in a temp dir, with cwd set to it."""
    monkeypatch.chdir(tmp_path)
    assert main(["init"]) == 0
    return tmp_path


@pytest.fixture
def plan_file(project):
    path = project / "plan.json"
    path.write_text(json.dumps(PLAN), encoding="utf-8")
    return path


def run(*argv: str) -> int:
    return main(list(argv))
