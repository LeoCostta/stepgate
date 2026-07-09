<!-- stepgate:start -->
## Micro-change protocol (stepgate)

This project uses `stepgate`, a CLI that structures work into small, approved
steps. It is your toolset for proposing and executing changes — the commands
below are the only legitimate channel for that flow.

**When it applies:** any change to code or behavior — implementation, bug fixes
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
   `stepgate next --suggest "..."`.

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
<!-- stepgate:end -->
