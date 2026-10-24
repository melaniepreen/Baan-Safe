"""System 2 entry point. Owner: Melanie.

Nemotron reasons first. The Sapling verifier then runs on aid-eligibility
and denial outcomes, and the caller hands the result to the Decision Router.
`orchestrate` still raises NotImplementedError while a System 2 decision is
TODO_HUMAN; that raise passes through unchanged.
"""

from __future__ import annotations

from contracts.models import CaseState, Outcome
from system2.orchestrator import orchestrate
from system2.sapling import verify_before_router


def decide(
    case: CaseState,
    handoff: Outcome | None = None,
    recommendation: dict | None = None,
) -> Outcome:
    try:
        outcome = orchestrate(case, handoff=handoff, recommendation=recommendation)
    except NotImplementedError:
        raise
    return verify_before_router(case, outcome)
