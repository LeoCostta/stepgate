# stepgate

[![PyPI version](https://img.shields.io/pypi/v/stepgate)](https://pypi.org/project/stepgate/)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://pypi.org/project/stepgate/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)

**A step-gated micro-change protocol for coding agents.**

Coding agents (Claude Code, Codex, …) working on large or loosely-scoped tasks
tend to mix contexts, silently expand scope, touch files unrelated to the
original request, or declare success without real evidence. `stepgate` makes
the correct workflow — investigate, propose, wait for approval, execute only
what was approved, verify, suggest the next step — **the single natural path
of action**, so that deviating from it is visible and recorded, never silent.

`stepgate` is *not* an enforcement tool. It never blocks your code, your
editor, your commits, or git. You can always edit anything, commit anything,
and cancel any agent session at any time. What it gives you is structure and
an honest, append-only trail of what was proposed, approved, executed, and
verified — across every agent working on the repo, even concurrently.

## Install

```bash
pipx install stepgate   # recommended: one global install per machine
# or: pip install stepgate
```

Then, at the root of any project:

```bash
stepgate init
```

This creates `.stepgate/` (state + append-only history) and injects an
instruction block into `AGENTS.md`/`CLAUDE.md` telling agents to use the
protocol. It is idempotent and never overwrites anything you wrote in those
files — only the text between its own markers is ever touched. If your
project already has a domain guardrails document, point to it with
`--guardrails GUARDRAILS.md` and the generated block will reference it.

## The protocol

Every micro-change is a proposal moving through a state machine, validated by
the CLI itself:

```
PENDING ──approve──► APPROVED ──exec-log──► EXECUTED ──verify──► VERIFIED ──close──► CLOSED
   │
   └─reject──► REJECTED          (any non-terminal state) ──abandon──► ABANDONED
```

A proposal covers six points, each written as natural flowing prose (not a
telegraphic form): **what** will change now, **why** this step comes first,
**where** (files/contracts/flows touched), **how** it will be implemented,
the **expected result**, and the **verification** that will demonstrate it.

Key rule: *a micro-change reduces the scope of execution, never the depth of
investigation* — the agent still investigates everything it needs to
understand before proposing, even if it will only implement a small piece.

## A real cycle

You ask your agent to fix a race condition. It investigates, then proposes:

```bash
stepgate propose --agent claude --file plan.json
```

You read it rendered as prose, and approve with a tweak:

```bash
stepgate show
stepgate approve --adjust --note "rename the function to apply_sanity_loss_atomic"
```

The agent implements **only** what was approved, logs it (a `git diff --stat`
is captured automatically as objective evidence), and verifies:

```bash
stepgate exec-log --summary "atomic decrement migration + typing" --files "migrations/013.sql,types.ts"
stepgate verify --evidence "type-check ok, simulated concurrency test passed"
```

You close the cycle; the agent suggests — but does not start — the next step:

```bash
stepgate close
stepgate next --suggest "wire SalaJogo.tsx to the new function via supabase.rpc(...)"
```

The suggestion stays visible in `stepgate status` until a new proposal is
opened. The full trail lives in `stepgate history` — chronological, across
all sessions and agents, append-only.

## Commands

| Command | Purpose |
| --- | --- |
| `stepgate init` | Create `.stepgate/`, inject the agent instruction block |
| `stepgate propose --agent X --file plan.json` | Register a micro-change plan (PENDING) |
| `stepgate show` | Render the active proposal as readable prose |
| `stepgate approve [--adjust --scope ... --note ...]` | Approve (optionally with reduced scope) |
| `stepgate reject --note "..."` | Reject a pending proposal |
| `stepgate exec-log --summary "..." --files "..."` | Record execution (+ automatic `git diff --stat`) |
| `stepgate verify --evidence "..."` | Record verification evidence |
| `stepgate close` | Close a verified micro-change |
| `stepgate abandon --reason "..."` | Cleanly abandon from any non-terminal state |
| `stepgate next --suggest "..."` | Record a next-step suggestion (opens nothing) |
| `stepgate status` | Current session + aggregated project view |
| `stepgate history [--session X] [--since DATE]` | Append-only, cross-session log |
| `stepgate doctor` | Report corrupted/invalid state files (fixes nothing) |

Multiple agents can work concurrently: each session has its own state file
(`.stepgate/sessions/claude-2026-07-09-1.json` — human-readable names, not
hashes), writes are file-locked, and `propose`/`status` warn — informationally,
never blockingly — when two active proposals touch the same files.

## Design principles

- **Never block.** No git hooks, no file locks on your code, no commit gates.
  The file lock in `.stepgate/` protects only stepgate's own state files.
- **Never act silently.** No auto-repair, no auto-expiry of stale sessions,
  no rewriting of history. `doctor` diagnoses; a human decides.
- **Non-interactive by design.** No prompts or confirmations, so it behaves
  identically in a terminal, a desktop app, or an IDE side-panel extension.
- **Structure when you opt in.** Editing code without a proposal is a
  legitimate flow, not an error. The state machine gives shape to the agent
  workflow — it is never a requirement for the code to change.

## License

[MIT](LICENSE) © Leo Costta
