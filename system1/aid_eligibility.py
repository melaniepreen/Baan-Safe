"""Aid eligibility fast check. Owner: Melanie.

This is the System 1 aid stub. It does not approve a payment and it does not
read a baht amount. gateway.route does not call it.
"""

from __future__ import annotations

from config.settings import unset_decisions
from contracts.models import AidEligibility, CaseState


def check(case: CaseState) -> AidEligibility:
    del case
    missing = unset_decisions(["system1.extraction_method"])
    extra = ""
    if missing:
        extra = " Unset TODO_HUMAN: " + ", ".join(missing) + "."
    raise NotImplementedError(
        "not implemented yet — owner: Melanie. "
        "Aid eligibility is unset and must not auto-approve a payment." + extra
    )
