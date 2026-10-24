"""System 2 entry point. Owner: Melanie.

Delegates to the Nemotron orchestrator. The body does not decide a case.
"""

from __future__ import annotations

from contracts.models import CaseState, Outcome
from system2.orchestrator import orchestrate


def decide(case: CaseState) -> Outcome:
    try:
        return orchestrate(case)
    except NotImplementedError:
        raise
