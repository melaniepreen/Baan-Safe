"""System 1 entry point. Owner: Moly.

The body raises until a human writes the rules. It reads config/decisions.yaml
and names every value that is still TODO_HUMAN.
"""

from __future__ import annotations

from config.settings import unset_decisions
from contracts.models import CaseState, Outcome

_DECISIONS = [
    "system1.extraction_method",
    "system1.extraction_model",
]


def decide(case: CaseState) -> Outcome:
    missing = unset_decisions(_DECISIONS)
    extra = ""
    if missing:
        extra = " Unset TODO_HUMAN: " + ", ".join(missing) + "."
    raise NotImplementedError(
        "not implemented yet — owner: Moly." + extra
    )
