import json

import pytest

from stepgate.cli import main


PLAN = {
    "narrative": (
        "We'll create an atomic Postgres function for the Sanity decrement, "
        "because concurrent losses currently overwrite each other and this "
        "must land before any UI change. We'll follow the same pattern already "
        "used in user_can_access_mesa, so that concurrent sanity losses no "
        "longer overwrite each other, and confirm it with a simulated "
        "concurrency test, a type-check, and npm test."
    ),
    "where": ["migrations/013_sanity.sql", "src/types.ts"],
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
