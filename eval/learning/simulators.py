"""Held-out caller trait combinations.

The split key is group_id, the same field as TrainingEvent.group_id. For
these rows the id is the simulator combo id. A trait combination is an
unseen user simulator, in addition to the held-out call groups. Seeds match
the rest of this package. Figures are the stub priority rule. No caller model is loaded.

Per-trait under-triage uses critical held-out combinations that carry the
trait. None means this seed held out no such combination. None is not zero.
Turns to location and turns to urgency count public caller turns. None means
the script never said that fact.
"""

from __future__ import annotations

from dataclasses import dataclass

from eval.learning.metrics import URGENCY
from eval.learning.split import SEEDS, split_groups
from sim import PAPER_ID, PAPER_URL
from sim.callers.catalog import CATALOG
from sim.callers.persona import CallerSpec
from sim.callers.scripted import revelation_turns

ARMS: tuple[str, ...] = ("A", "B", "C", "shuffled")
FOCUS_TRAITS: tuple[str, ...] = ("under_reports", "omits_location")


@dataclass(frozen=True)
class TraitRow:
    combo_id: str
    traits: tuple[str, ...]
    critical: bool
    gold: str
    pred: str


def public_priority(spec: CallerSpec) -> str:
    """Priority a stub reads off the public call, ignoring hidden urgency.

    Under-reporting and a missing district both land on P4. Over-reporting
    lands on P1. Any other combination keeps the hidden urgency.
    """
    traits = spec.traits
    if "under_reports" in traits or "omits_location" in traits:
        return "P4"
    if "over_reports" in traits:
        return "P1"
    return spec.persona.true_urgency


def predict_priority(
    arm: str,
    spec: CallerSpec,
    correction: list[CallerSpec] | tuple[CallerSpec, ...],
) -> str:
    """A and shuffled stay on the public priority. B and C copy a sibling pattern."""
    base = public_priority(spec)
    if arm in ("A", "shuffled"):
        return base
    if arm not in ("B", "C"):
        raise ValueError(f"unknown arm {arm}")
    if spec.pattern and any(spec.pattern == other.pattern for other in correction):
        return spec.persona.true_urgency
    return base


def trait_under_triage(rows: list[TraitRow] | tuple[TraitRow, ...], trait: str | None) -> float | None:
    """Fraction under-triaged. `trait` None scores every critical row."""
    chosen = [
        row
        for row in rows
        if row.critical and (trait is None or trait in row.traits)
    ]
    if not chosen:
        return None
    under = sum(1 for row in chosen if URGENCY[row.pred] > URGENCY[row.gold])
    return under / len(chosen)


def _by_id() -> dict[str, CallerSpec]:
    return {spec.combo_id: spec for spec in CATALOG}


def summarize() -> list[dict]:
    """One entry per fixed seed. Held-out group_id values only."""
    by_id = _by_id()
    group_ids = [spec.combo_id for spec in CATALOG]
    payload: list[dict] = []
    for seed in SEEDS:
        split = split_groups(group_ids, seed)
        correction = [by_id[group_id] for group_id in split.correction]
        held = [by_id[group_id] for group_id in split.held_out]
        arms: dict[str, dict] = {}
        for name in ARMS:
            rows = [
                TraitRow(
                    combo_id=spec.combo_id,
                    traits=spec.traits,
                    critical=spec.critical,
                    gold=spec.persona.true_urgency,
                    pred=predict_priority(name, spec, correction),
                )
                for spec in held
            ]
            arms[name] = {
                "under_triage": trait_under_triage(rows, None),
                "under_reports": trait_under_triage(rows, "under_reports"),
                "omits_location": trait_under_triage(rows, "omits_location"),
            }
        revealed = []
        for spec in held:
            location_at, urgency_at = revelation_turns(spec)
            revealed.append(
                {
                    "combo_id": spec.combo_id,
                    "traits": spec.traits,
                    "location_turn": location_at,
                    "urgency_turn": urgency_at,
                }
            )
        payload.append(
            {
                "seed": seed,
                "correction": split.correction,
                "held_out": split.held_out,
                "arms": arms,
                "revelation": revealed,
            }
        )
    return payload


def _fmt(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.3f}"


def _turn(value: int | None) -> str:
    if value is None:
        return "n/a"
    return str(value)


def render_trait_section() -> str:
    lines = [
        "## Held-out caller simulators",
        "",
        "Arms are scored on held-out trait combinations, not only on held-out calls.",
        "The split key is group_id. The combination is an unseen user simulator.",
        "The idea is from MIMESIS,",
        f"arXiv:{PAPER_ID}, {PAPER_URL}. No paper source is copied. No caller model",
        "was loaded. `sim.caller_model` and `sim.caller_gpu` stay `TODO_HUMAN`.",
        "",
        "Under-triage is the fraction of critical held-out combinations whose",
        "predicted priority is less urgent than the hidden urgency. The",
        "`under_reports` and `omits_location` columns count only critical",
        "held-out combinations that carry that trait. `n/a` means the seed held",
        "out none. `n/a` is not zero.",
        "",
        "Location turn and urgency turn are the first public caller turns that",
        "state the hidden district and the true urgency cue. `n/a` means the",
        "script never said it. The private trace is not read. The turns are a",
        "property of the scripted caller, so they are the same for every arm.",
        "",
        "A and shuffled use the public priority. Shuffled matches A: the control",
        "does not invent a matched trait pattern. B and C use the hidden urgency",
        "when a correction-side combination shares the pattern.",
        "",
        "| Seed | Arm | Under-triage | under_reports | omits_location |",
        "| --- | --- | --- | --- | --- |",
    ]
    rows = summarize()
    for seed in rows:
        for name in ARMS:
            score = seed["arms"][name]
            lines.append(
                f"| {seed['seed']} | {name} | {_fmt(score['under_triage'])} | "
                f"{_fmt(score['under_reports'])} | {_fmt(score['omits_location'])} |"
            )
    lines.extend(
        [
            "",
            "| Seed | Combination | Traits | Location turn | Urgency turn |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for seed in rows:
        for item in seed["revelation"]:
            lines.append(
                f"| {seed['seed']} | {item['combo_id']} | {', '.join(item['traits'])} | "
                f"{_turn(item['location_turn'])} | {_turn(item['urgency_turn'])} |"
            )
    lines.append("")
    return "\n".join(lines)
