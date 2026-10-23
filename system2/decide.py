"""System 2 entry point. Owner: Melanie.

The body raises until a human writes the orchestrator. It reads
config/decisions.yaml and names every value that is still TODO_HUMAN.
"""

from __future__ import annotations

from config.settings import unset_decisions
from contracts.models import CaseState, Outcome

_DECISIONS = [
    "system2.orchestrator_model",
    "system2.hosting",
    "system2.use_banyan_sapling",
    "system2.max_latency_ms",
]


def decide(case: CaseState) -> Outcome:
    missing = unset_decisions(_DECISIONS)
    extra = ""
    if missing:
        extra = " Unset TODO_HUMAN: " + ", ".join(missing) + "."
    raise NotImplementedError(
        "not implemented yet — owner: Melanie." + extra
    )
