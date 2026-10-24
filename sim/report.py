"""Markdown for one stub simulation run. Not a measured result."""

from __future__ import annotations

from sim import PAPER_ID, PAPER_URL
from sim.callers.scripted import revelation_turns
from sim.env import Episode


def _turn(value: int | None) -> str:
    if value is None:
        return "n/a"
    return str(value)


def render(episodes: list[Episode] | tuple[Episode, ...], coach_rows: int) -> str:
    lines = [
        "# Caller simulation (stub)",
        "",
        "Scripted callers only. No model was loaded and nothing was promoted.",
        f"Ideas from MIMESIS, arXiv:{PAPER_ID}, {PAPER_URL}.",
        "No paper source is copied. Token-level self-distillation is future work.",
        "",
        "`sim.caller_model` and `sim.caller_gpu` are `TODO_HUMAN`.",
        "The model backend, if those keys are set, calls `llm/client.py` only.",
        "",
        "The environment calls `gateway.handle` once per turn. Synthetic case ids",
        "route through the field precheck and `router.merge` builds the decision.",
        "System 1 and System 2 are not both run. Sapling is not called on the",
        "stub gateway path.",
        "The operator lines are a fixed stub. They do not read the hidden persona",
        "or the private trace.",
        "",
        f"Coach rows written: {coach_rows}. `source=coach`. `promoted` is false.",
        "These rows are not human corrections.",
        "",
        "## Episodes",
        "",
        "| Caller | Traits | Gateway | Location turn | Urgency turn |",
        "| --- | --- | --- | --- | --- |",
    ]
    for episode in episodes:
        location_at, urgency_at = revelation_turns(episode.spec)
        blocked = episode.turns[0].pipeline["blocked_on"] or episode.turns[0].pipeline["system"]
        lines.append(
            "| {combo} | {traits} | {blocked} | {loc} | {urg} |".format(
                combo=episode.spec.combo_id,
                traits=", ".join(episode.spec.traits),
                blocked=blocked,
                loc=_turn(location_at),
                urg=_turn(urgency_at),
            )
        )
    lines.extend(
        [
            "",
            "## Hidden truth and public transcript",
            "",
            "The hidden block is the simulator's record. It is not the CaseState.",
            "",
        ]
    )
    sample = episodes[0]
    hidden = sample.hidden()
    lines.append(f"### {sample.spec.combo_id}")
    lines.append("")
    lines.append("Hidden urgency: " + hidden["true_urgency"] + ".")
    lines.append("")
    lines.append("Hidden needs: " + ", ".join(hidden["true_needs"]) + ".")
    lines.append("")
    lines.append("Hidden location: " + hidden["location"] + ".")
    lines.append("")
    lines.append("Vulnerable household: " + ", ".join(hidden["vulnerable"]) + ".")
    lines.append("")
    lines.append("Private traces:")
    lines.append("")
    for trace in hidden["private_traces"]:
        lines.append(f"- {trace}")
    lines.extend(["", "Public transcript:", ""])
    for turn in sample.turns:
        lines.append(f"- caller: {turn.caller.public_text}")
        lines.append(f"- operator: {turn.operator_text}")
    lines.append("")
    return "\n".join(lines)
