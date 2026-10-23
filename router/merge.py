"""Router merge. Owner: Moly.

Stub gateway copies a stub Outcome into a RouterDecision. It does not call
this function. A human writes the merge policy here.
"""

from __future__ import annotations

from contracts.models import Outcome, RouterDecision


def merge(outcomes: list[Outcome], policy_flags: list[str]) -> RouterDecision:
    del outcomes, policy_flags
    raise NotImplementedError(
        "not implemented yet — owner: Moly. "
        "router/merge.py has no merge policy."
    )
