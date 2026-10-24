"""Arm stubs. No model call, no memory write, no training job.

A keeps the base label. B and C apply a pattern only when that pattern is on
the correction side, so a held-out sibling can move and the corrected call
itself is not scored. The shuffled control permutes correction labels and
does not treat that permutation as a matched pattern, so its predictions
stay with A.
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from pathlib import Path

from eval.learning.cases import CallGroup, CallVariant
from eval.learning.metrics import ScoredRow


@dataclass(frozen=True)
class Arm:
    name: str
    mechanism: str
    memory_empty: bool
    learns_matched_patterns: bool
    sapling_from_memory: bool


@dataclass(frozen=True)
class Prediction:
    priority: str
    route: str
    action: str
    sapling: str
    learned: bool


ARMS: tuple[Arm, ...] = (
    Arm(
        name="A",
        mechanism="base, no feedback",
        memory_empty=True,
        learns_matched_patterns=False,
        sapling_from_memory=False,
    ),
    Arm(
        name="B",
        mechanism="corrections in Mubit memory",
        memory_empty=False,
        learns_matched_patterns=True,
        sapling_from_memory=True,
    ),
    Arm(
        name="C",
        mechanism="fine-tuned on correction JSONL, memory empty",
        memory_empty=True,
        learns_matched_patterns=True,
        sapling_from_memory=False,
    ),
    Arm(
        name="shuffled",
        mechanism="shuffled-corrections control",
        memory_empty=False,
        learns_matched_patterns=False,
        sapling_from_memory=False,
    ),
)


def arm_by_name(name: str) -> Arm:
    for item in ARMS:
        if item.name == name:
            return item
    raise KeyError(name)


def learned_patterns(arm: Arm, correction: list[CallGroup] | tuple[CallGroup, ...]) -> frozenset[str]:
    """Patterns B or C may apply. Shuffled feedback is never a matched pattern."""
    if not arm.learns_matched_patterns:
        return frozenset()
    return frozenset(group.pattern for group in correction if group.pattern)


def predict(
    arm: Arm,
    variant: CallVariant,
    correction: list[CallGroup] | tuple[CallGroup, ...],
    seed: int,
) -> Prediction:
    """Stub label for one held-out variant.

    `seed` is accepted so every arm shares a call shape. The shuffled control
    applies that seed when it permutes feedback rows. It does not use the
    permuted rows as a matched pattern, so the seed does not change this label.
    """
    _ = seed
    matched = bool(variant.pattern and variant.pattern in learned_patterns(arm, correction))
    if matched:
        priority, route, action = variant.priority, variant.route, variant.action
    else:
        priority = variant.base_priority
        route = variant.base_route
        action = variant.base_action
    sapling = variant.sapling
    if arm.sapling_from_memory and sapling == "unsure":
        # Stub distinction: B's memory holds a policy note. This is not a Sapling call.
        sapling = "supported"
    return Prediction(
        priority=priority,
        route=route,
        action=action,
        sapling=sapling,
        learned=matched,
    )


def score_variant(
    arm: Arm,
    variant: CallVariant,
    correction: list[CallGroup] | tuple[CallGroup, ...],
    seed: int,
) -> ScoredRow:
    pred = predict(arm, variant, correction, seed)
    return ScoredRow(
        seed=seed,
        arm=arm.name,
        group_id=variant.group_id,
        language=variant.language,
        critical=variant.critical,
        gold_priority=variant.priority,
        gold_route=variant.route,
        gold_action=variant.action,
        pred_priority=pred.priority,
        pred_route=pred.route,
        pred_action=pred.action,
        sapling=pred.sapling,
    )


def feedback_rows(
    arm: Arm,
    correction: list[CallGroup] | tuple[CallGroup, ...],
    seed: int,
) -> list[dict]:
    """Correction rows an arm would have seen. A has none. No weights are trained.

    The shuffled arm permutes the assistant label across correction groups.
    Scoring does not read those permuted labels back as patterns.
    """
    if arm.name == "A":
        return []
    labels = [(group.priority, group.route, group.pattern) for group in correction]
    if arm.name == "shuffled":
        random.Random(seed).shuffle(labels)
    rows: list[dict] = []
    for group, (priority, route, pattern) in zip(correction, labels):
        for language, text in (("en", group.en), ("th", group.th)):
            rows.append(
                {
                    "arm": arm.name,
                    "seed": seed,
                    "group_id": group.group_id,
                    "language": language,
                    "pattern": pattern,
                    "memory_empty": arm.memory_empty,
                    "messages": [
                        {
                            "role": "system",
                            "content": (
                                "Label a synthetic flood call. "
                                "Reply with a priority and a route. Do not invent a person."
                            ),
                        },
                        {"role": "user", "content": text},
                        {"role": "assistant", "content": f"{priority} {route}"},
                    ],
                }
            )
    return rows


def write_feedback(path: Path, rows: list[dict]) -> None:
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
