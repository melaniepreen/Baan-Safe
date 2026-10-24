"""Aid exception reasoning. Owner: Melanie.

System 2 stub for exception proposals. It does not approve an exception.
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


def propose(case: CaseState) -> Outcome:
    del case
    missing = unset_decisions(_DECISIONS)
    extra = ""
    if missing:
        extra = " Unset TODO_HUMAN: " + ", ".join(missing) + "."
    raise NotImplementedError(
        "not implemented yet — owner: Melanie. "
        "Aid exception reasoning is not implemented." + extra
    )
