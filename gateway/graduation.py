"""Correction graduation. Owner: Moly.

When `correction_loop.escalation_threshold` distinct cases share one
extracted-field pattern and a graduation label, that pattern is graduated:
affected cases stay in System 2, tagged `complex_situation`, and System 2 gets
a recommendation as a correction MemoryItem. Graduation never sets a priority
and never moves a pattern into System 1.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass

from config.settings import load_yaml, require_decision
from contracts.models import CaseState, MemoryItem
from fixtures.load import load_case
from training.log import read_events


@dataclass(frozen=True)
class Graduation:
    pattern: tuple
    label: str
    case_ids: tuple[str, ...]
    count: int


def pattern_of(case: CaseState) -> tuple:
    fields = case.fields
    return (
        tuple(sorted(need.value for need in fields.needs)),
        tuple(sorted(fields.vulnerable)),
        tuple(sorted(fields.danger)),
    )


def _default_resolve(case_id: str) -> CaseState | None:
    try:
        return load_case(case_id)
    except KeyError:
        pass
    from api.store import get

    stored = get(case_id)
    return stored.state if stored else None


def graduated_patterns(
    events=None,
    resolve: Callable[[str], CaseState | None] | None = None,
) -> list[Graduation]:
    threshold = int(require_decision("correction_loop.escalation_threshold"))
    labels = set(load_yaml("escalation.yaml").get("graduation_labels") or [])
    resolver = resolve or _default_resolve
    if events is None:
        events = read_events()
    groups: dict[tuple, set[str]] = {}
    for event in events:
        if event.task != "s1_triage" or event.source != "human":
            continue
        label = getattr(event.output_correct, "value", event.output_correct)
        if label not in labels:
            continue
        case = resolver(event.input_ref.case_id)
        if case is None:
            continue
        key = (pattern_of(case), label)
        groups.setdefault(key, set()).add(event.input_ref.case_id)
    return [
        Graduation(pattern=pattern, label=label, case_ids=tuple(sorted(ids)), count=len(ids))
        for (pattern, label), ids in groups.items()
        if len(ids) >= threshold
    ]


def _flag(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def apply(case: CaseState) -> list[Graduation]:
    matches = [
        graduation
        for graduation in graduated_patterns()
        if graduation.pattern == pattern_of(case)
    ]
    if not matches:
        return []
    _flag(case.policy_flags, "complex_situation")
    seen = {item.memory_id for item in case.memory_context}
    for graduation in matches:
        digest = hashlib.sha256(repr(graduation.pattern).encode()).hexdigest()[:8]
        memory_id = f"graduated-{graduation.label}-{digest}"
        if memory_id in seen:
            continue
        seen.add(memory_id)
        ids = ", ".join(graduation.case_ids)
        case.memory_context.append(
            MemoryItem(
                memory_id=memory_id,
                kind="correction",
                summary=(
                    f"Graduated pattern: {graduation.count} human corrections "
                    f"({ids}) labelled this pattern {graduation.label}. "
                    "Recommendation for System 2. This rule sets no priority."
                ),
                relevance=1.0,
                source_case_id=graduation.case_ids[0],
            )
        )
    return matches
