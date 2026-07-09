"""Terminal rendering helpers.

Proposals are rendered as flowing, readable prose — the same natural
language the agent wrote them in — never as a rigid telegraphic form.
"""

from __future__ import annotations

from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.text import Text

console = Console()
err_console = Console(stderr=True, style="yellow")

STATE_STYLES = {
    "PENDING": "bold yellow",
    "APPROVED": "bold cyan",
    "EXECUTED": "bold blue",
    "VERIFIED": "bold green",
    "CLOSED": "bold dim green",
    "REJECTED": "bold red",
    "ABANDONED": "bold dim",
}


def state_text(state: str) -> Text:
    return Text(state, style=STATE_STYLES.get(state, "bold"))


def plan_as_prose(plan: dict[str, Any]) -> Group:
    """Render the six plan fields as connected paragraphs of prose."""
    where = ", ".join(plan["where"])
    paragraphs = [
        Text(plan["what"]),
        Text(plan["why"], style="dim"),
        Text.assemble(("Touches: ", "italic"), where),
        Text(plan["how"]),
        Text.assemble(("Expected result — ", "italic"), plan["expected_result"]),
        Text.assemble(("Verification — ", "italic"), plan["verification"]),
    ]
    spaced: list[Any] = []
    for para in paragraphs:
        spaced.append(para)
        spaced.append(Text(""))
    return Group(*spaced[:-1])


def proposal_panel(session_name: str, proposal: dict[str, Any]) -> Panel:
    title = Text.assemble(
        ("Proposal · ", "bold"), (session_name, "bold magenta"), (" · ", "bold"),
        state_text(proposal["state"]),
    )
    body: list[Any] = [plan_as_prose(proposal["plan"])]
    notes = []
    for event in proposal.get("events", []):
        data = event.get("data") or {}
        if event["action"] == "approve" and (data.get("note") or data.get("scope")):
            note = data.get("note", "")
            scope = data.get("scope")
            detail = f"Approved with adjustment: {note}" if note else "Approved with adjusted scope"
            if scope:
                detail += f" (scope: {', '.join(scope)})"
            notes.append(detail)
        elif event["action"] == "reject":
            notes.append(f"Rejected: {data.get('note', '')}")
        elif event["action"] == "abandon":
            notes.append(f"Abandoned: {data.get('reason', '')}")
    if notes:
        body.append(Text(""))
        for note in notes:
            body.append(Text(f"• {note}", style="yellow"))
    return Panel(Group(*body), title=title, title_align="left", border_style="dim")


def warn(message: str) -> None:
    err_console.print(f"warning: {message}")


def info(message: str) -> None:
    console.print(message)
