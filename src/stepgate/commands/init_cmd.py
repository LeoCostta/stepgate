"""stepgate init: create .stepgate/ and inject the agent instruction block.

Idempotent and never destructive: existing sessions/, history.jsonl and any
hand-written content in AGENTS.md/CLAUDE.md are always preserved. Only the
text between the stepgate markers is ever replaced.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from stepgate import render
from stepgate.store import DEFAULT_CONFIG, Store

START_MARKER = "<!-- stepgate:start -->"
END_MARKER = "<!-- stepgate:end -->"

INSTRUCTION_FILES = ("AGENTS.md", "CLAUDE.md")
GUARDRAILS_CANDIDATES = ("GUARDRAILS.md", "docs/GUARDRAILS.md")


def build_instruction_block(guardrails: str | None) -> str:
    guardrails_paragraph = (
        f"Domain knowledge for this project lives in `{guardrails}`. That document "
        "governs *what* is correct in this domain; stepgate governs *when* you may "
        "execute a change. Both apply, each in its own dimension — neither replaces "
        "the other.\n\n"
        if guardrails
        else ""
    )
    return f"""{START_MARKER}
## Micro-change protocol (stepgate)

This project uses `stepgate`, a CLI that structures work into small, approved
steps. It is your toolset for proposing and executing changes — the commands
below are the only legitimate channel for that flow.

{guardrails_paragraph}**When it applies:** any change to code or behavior — implementation, bug fixes
that edit code, refactoring, contract/schema changes. It does NOT apply to
read-only work: investigating, explaining, diagnosing without editing.

**The cycle.** Investigate as deeply as you need first — a micro-change reduces
the scope of *execution*, never the depth of *investigation*. Then:

1. `stepgate propose --agent <your-name> --file plan.json` — a JSON object with
   six fields (`what`, `why`, `where`, `how`, `expected_result`,
   `verification`), each written as natural, flowing prose (where is a list of
   files/areas). State becomes PENDING. Always pass `--agent` (e.g. `claude`,
   `codex`) so sessions stay readable.
2. Wait for the user to run `stepgate approve` (possibly `--adjust`) or
   `stepgate reject`. Never execute a PENDING proposal.
3. Execute **only** what was approved, then record it:
   `stepgate exec-log --summary "..." --files "a,b"`.
4. Verify with real evidence: `stepgate verify --evidence "npm test: 12 passed"`.
5. After the user runs `stepgate close`, suggest (don't start) the next step:
   `stepgate next --suggest "..."`. Running `stepgate next` with no `--suggest`
   just shows the currently recorded suggestion, without changing anything.

**Rules:**
- Approval is per micro-change, never cumulative. One approval is not a blanket
  pass for the rest of the task.
- If your environment has an "apply change" / "accept diff" button in the IDE
  UI, the same rule holds: only reach that point after the proposal was
  approved via stepgate.
- If a proposal becomes obsolete, close it out explicitly:
  `stepgate abandon --reason "..."`.
- Run `stepgate status`/`history` only when you actually need them (when
  proposing, or when closing a cycle) — not as a habitual check.
- stepgate never blocks edits, commits, or the user. It records and makes the
  flow visible; deviating from it is visible, never silent.
- The four flow verbs accept Portuguese aliases (English stays the default):
  `aprovar` = approve, `rejeitar` = reject, `fechar` = close, `proximo` = next.
{END_MARKER}"""


def inject_block(path: Path, block: str) -> str:
    """Create, append, or update-in-place the stepgate block. Returns the
    action taken. Never discards existing content."""
    if not path.exists():
        path.write_text(block + "\n", encoding="utf-8")
        return "created"
    content = path.read_text(encoding="utf-8")
    if START_MARKER in content and END_MARKER in content:
        start = content.index(START_MARKER)
        end = content.index(END_MARKER) + len(END_MARKER)
        path.write_text(content[:start] + block + content[end:], encoding="utf-8")
        return "updated"
    separator = "" if content.endswith("\n\n") else ("\n" if content.endswith("\n") else "\n\n")
    path.write_text(content + separator + block + "\n", encoding="utf-8")
    return "appended"


def detect_guardrails(root: Path) -> str | None:
    for candidate in GUARDRAILS_CANDIDATES:
        if (root / candidate).exists():
            return candidate
    return None


def cmd_init(args) -> int:
    root = Path.cwd()
    store = Store(root)
    store.ensure_layout()

    if not store.config_path.exists():
        config = dict(DEFAULT_CONFIG)
        config["project_name"] = root.name
        store.write_config(config)
        render.info(f"Created {store.config_path}")
    else:
        render.info(f"Kept existing {store.config_path}")

    guardrails = args.guardrails or detect_guardrails(root)
    if guardrails and not (root / guardrails).exists():
        render.warn(f"guardrails file '{guardrails}' does not exist; referencing it anyway.")
    block = build_instruction_block(guardrails)
    for name in INSTRUCTION_FILES:
        action = inject_block(root / name, block)
        render.info(f"{action.capitalize()} stepgate instruction block in {name}")
    if guardrails:
        render.info(f"Instruction block references domain guardrails: {guardrails}")

    if shutil.which("stepgate") is None:
        render.warn(
            "the 'stepgate' executable was not found on PATH from this "
            "environment. Agents running here will not be able to call it - "
            "check the installation (pipx install stepgate) or this "
            "environment's PATH."
        )
    render.info(
        f"[green]stepgate initialized in {store.dir}[/] "
        "(existing sessions and history, if any, were preserved)."
    )
    return 0
