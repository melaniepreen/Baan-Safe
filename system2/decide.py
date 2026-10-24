"""System 2 entry point. Owner: Melanie.

Nemotron reasons first. The Sapling verifier then runs on aid-eligibility
and denial outcomes, and the caller hands the result to the Decision Router.
The body still raises while the orchestrator is unimplemented.
"""

from __future__ import annotations

from contracts.models import CaseState, Outcome
from system2.orchestrator import orchestrate
from system2.sapling import verify_before_router


def decide(case: CaseState) -> Outcome:
    try:
        outcome = orchestrate(case)
    except NotImplementedError:
        raise
    return verify_before_router(case, outcome)
