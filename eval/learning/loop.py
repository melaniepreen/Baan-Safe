"""Closed loop: a new model version runs the held-out eval, then a recommendation.

Promotion is applied nowhere in this module. `learning_eval.promotion` stays
TODO_HUMAN. A set value raises instead of promoting. Freezing Mubit
auto-adapters is the same shape: the stub records TODO_HUMAN and does not
call Mubit. A set value raises so a live run cannot pretend the adapters
were frozen.
"""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import UNSET, decisions, is_unset


@dataclass(frozen=True)
class SeedScore:
    seed: int
    accuracy: float
    under_triage: float | None


def recommend_promotion(
    current: list[SeedScore] | tuple[SeedScore, ...],
    candidate: list[SeedScore] | tuple[SeedScore, ...],
) -> dict:
    """Recommend only when every seed is strictly more accurate and under-triage does not rise.

    `promoted` is always false. None under-triage is not comparable to a
    number, or to another None, and blocks the recommendation.
    """
    current_by_seed = {item.seed: item for item in current}
    candidate_by_seed = {item.seed: item for item in candidate}
    reasons: list[str] = []
    recommend = True
    if not current_by_seed or set(current_by_seed) != set(candidate_by_seed):
        recommend = False
        reasons.append("current and candidate seeds do not match")
    for seed in sorted(current_by_seed):
        if seed not in candidate_by_seed:
            continue
        base = current_by_seed[seed]
        proposed = candidate_by_seed[seed]
        if not proposed.accuracy > base.accuracy:
            recommend = False
            reasons.append(f"seed {seed}: held-out accuracy did not rise")
        if base.under_triage is None or proposed.under_triage is None:
            recommend = False
            reasons.append(f"seed {seed}: under-triage is not comparable")
        elif proposed.under_triage > base.under_triage:
            recommend = False
            reasons.append(f"seed {seed}: under-triage rose")
    if recommend:
        reasons.append(
            "every seed rose on held-out accuracy and under-triage did not rise"
        )
    return {"recommend": recommend, "promoted": False, "reasons": reasons}


def freeze_gate() -> str:
    """Record TODO_HUMAN, or refuse if a human set the freeze without an implementation."""
    value = decisions()["learning_eval"]["freeze_mubit_auto_adapters"]
    if is_unset(value):
        return UNSET
    raise NotImplementedError(
        "Melanie: learning_eval.freeze_mubit_auto_adapters is set, but this "
        "skeleton does not freeze Mubit auto-adapters and must not pretend it did. "
        f"{UNSET}."
    )


def promotion_gate() -> str:
    """Record TODO_HUMAN, or refuse if a human set promotion without an implementation."""
    value = decisions()["learning_eval"]["promotion"]
    if is_unset(value):
        return UNSET
    raise NotImplementedError(
        "Melanie: learning_eval.promotion is set, but eval/learning does not "
        f"promote a model version. {UNSET}."
    )


def close_loop(
    version_id: str,
    current: list[SeedScore] | tuple[SeedScore, ...],
    candidate: list[SeedScore] | tuple[SeedScore, ...],
) -> dict:
    """New version, already scored, to a recommendation. Promotion stays unapplied.

    Call `freeze_gate` before scoring a live run. This function checks it
    again so a caller cannot recommend while skipping the freeze note.
    """
    if not version_id or is_unset(version_id):
        raise ValueError("version_id is required and must not be TODO_HUMAN")
    decision = recommend_promotion(current, candidate)
    decision["version_id"] = version_id
    decision["freeze_mubit_auto_adapters"] = freeze_gate()
    decision["promotion"] = promotion_gate()
    decision["promoted"] = False
    return decision
