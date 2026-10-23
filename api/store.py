"""In-memory case store for the overnight service. Not the production database."""

from __future__ import annotations

from dataclasses import dataclass, field

from contracts.models import CaseState, Correction, RouterDecision


@dataclass
class StoredCase:
    state: CaseState
    fixture_id: str | None = None
    decisions: list[RouterDecision] = field(default_factory=list)
    corrections: list[Correction] = field(default_factory=list)


CASES: dict[str, StoredCase] = {}


def reset() -> None:
    CASES.clear()


def put(case: StoredCase) -> StoredCase:
    CASES[case.state.case_id] = case
    return case


def get(case_id: str) -> StoredCase | None:
    return CASES.get(case_id)
