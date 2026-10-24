"""Metric signatures for the held-out correction scoreboard.

Functions score held-out rows only. Under-triage of critical calls is the
headline. None means that seed held out no critical call. None is not zero.
"""

from __future__ import annotations

from dataclasses import dataclass

URGENCY = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}


@dataclass(frozen=True)
class ScoredRow:
    seed: int
    arm: str
    group_id: str
    language: str
    critical: bool
    gold_priority: str
    gold_route: str
    gold_action: str
    pred_priority: str
    pred_route: str
    pred_action: str
    sapling: str

    @property
    def label_correct(self) -> bool:
        return (
            self.pred_priority == self.gold_priority
            and self.pred_route == self.gold_route
        )


@dataclass(frozen=True)
class ArmScore:
    name: str
    accuracy: float
    macro_f1: float
    under_triage: float | None
    route_accuracy: float
    safe_action_rate: float
    sapling_unsure_rate: float
    repeat_errors: tuple[str, ...]
    regressions: tuple[str, ...]
    paired_accuracy: float | None
    paired_under_triage: float | None


def accuracy(rows: list[ScoredRow] | tuple[ScoredRow, ...]) -> float:
    """Share of rows whose priority and route both match the label."""
    if not rows:
        return 0.0
    return sum(1 for row in rows if row.label_correct) / len(rows)


def macro_f1(rows: list[ScoredRow] | tuple[ScoredRow, ...]) -> float:
    """Macro-F1 over priority labels that appear in the gold or the prediction."""
    if not rows:
        return 0.0
    labels = sorted({row.gold_priority for row in rows} | {row.pred_priority for row in rows})
    scores: list[float] = []
    for label in labels:
        tp = sum(
            1
            for row in rows
            if row.gold_priority == label and row.pred_priority == label
        )
        fp = sum(
            1
            for row in rows
            if row.gold_priority != label and row.pred_priority == label
        )
        fn = sum(
            1
            for row in rows
            if row.gold_priority == label and row.pred_priority != label
        )
        precision = tp / (tp + fp) if tp + fp else 0.0
        recall = tp / (tp + fn) if tp + fn else 0.0
        scores.append(
            0.0 if precision + recall == 0 else 2 * precision * recall / (precision + recall)
        )
    return sum(scores) / len(scores)


def under_triage(rows: list[ScoredRow] | tuple[ScoredRow, ...]) -> float | None:
    """Fraction of critical held-out calls predicted less urgent than the label.

    P1 is the most urgent rank. Returns None when this seed held out no
    critical call. Callers must not treat that None as zero.
    """
    critical = [row for row in rows if row.critical]
    if not critical:
        return None
    under = 0
    for row in critical:
        if URGENCY[row.pred_priority] > URGENCY[row.gold_priority]:
            under += 1
    return under / len(critical)


def route_accuracy(rows: list[ScoredRow] | tuple[ScoredRow, ...]) -> float:
    if not rows:
        return 0.0
    return sum(1 for row in rows if row.pred_route == row.gold_route) / len(rows)


def safe_action_rate(rows: list[ScoredRow] | tuple[ScoredRow, ...]) -> float:
    if not rows:
        return 0.0
    return sum(1 for row in rows if row.pred_action == row.gold_action) / len(rows)


def sapling_unsure_rate(rows: list[ScoredRow] | tuple[ScoredRow, ...]) -> float:
    if not rows:
        return 0.0
    return sum(1 for row in rows if row.sapling == "unsure") / len(rows)


def repeat_errors(rows: list[ScoredRow] | tuple[ScoredRow, ...]) -> list[str]:
    """Groups wrong in every language variant, when the group has two or more."""
    grouped: dict[str, list[ScoredRow]] = {}
    for row in rows:
        grouped.setdefault(row.group_id, []).append(row)
    found: list[str] = []
    for group_id in sorted(grouped):
        items = grouped[group_id]
        if len(items) >= 2 and all(not item.label_correct for item in items):
            found.append(group_id)
    return found


def regressions(
    baseline: list[ScoredRow] | tuple[ScoredRow, ...],
    candidate: list[ScoredRow] | tuple[ScoredRow, ...],
) -> list[str]:
    """Candidate wrong where the baseline was right. Keyed by seed, group, language."""
    base = {(row.group_id, row.language): row for row in baseline}
    keys: list[str] = []
    for row in candidate:
        previous = base[(row.group_id, row.language)]
        if previous.label_correct and not row.label_correct:
            keys.append(f"{row.seed}:{row.group_id}:{row.language}")
    return sorted(keys)


def paired_difference(candidate: float | None, baseline: float | None) -> float | None:
    """Candidate minus baseline for one seed. None if either side is None.

    For under-triage, a negative difference is the safer direction.
    """
    if candidate is None or baseline is None:
        return None
    return candidate - baseline


def score_arm(
    name: str,
    rows: list[ScoredRow] | tuple[ScoredRow, ...],
    baseline: list[ScoredRow] | tuple[ScoredRow, ...],
) -> ArmScore:
    acc = accuracy(rows)
    ut = under_triage(rows)
    return ArmScore(
        name=name,
        accuracy=acc,
        macro_f1=macro_f1(rows),
        under_triage=ut,
        route_accuracy=route_accuracy(rows),
        safe_action_rate=safe_action_rate(rows),
        sapling_unsure_rate=sapling_unsure_rate(rows),
        repeat_errors=tuple(repeat_errors(rows)),
        regressions=tuple(regressions(baseline, rows)),
        paired_accuracy=paired_difference(acc, accuracy(baseline)),
        paired_under_triage=paired_difference(ut, under_triage(baseline)),
    )
