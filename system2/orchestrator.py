"""Nemotron orchestrator interface. Owner: Melanie.

Nemotron is the System 2 orchestrator. It is not part of Mubit. When a human
has set the remaining System 2 decisions, this function would call llm.complete,
which only talks to Mubit. While those decisions are TODO_HUMAN it raises first
and does not call the network. It does not build an Outcome.

use_banyan_sapling is already true. The verifier does not run here. decide()
runs it on the outcome this function returns, and the gateway then builds the
Decision Router result.
"""

from __future__ import annotations

from config.settings import unset_decisions
from contracts.models import CaseState, Outcome
from llm.client import complete

_DECISIONS = [
    "system2.orchestrator_model",
    "system2.hosting",
    "system2.use_banyan_sapling",
    "system2.max_latency_ms",
]


def orchestrate(case: CaseState) -> Outcome:
    del case
    missing = unset_decisions(_DECISIONS)
    if missing:
        raise NotImplementedError(
            "not implemented yet — owner: Melanie. "
            "Unset TODO_HUMAN: " + ", ".join(missing) + "."
        )
    complete(
        [
            {
                "role": "system",
                "content": "System 2 orchestrator stub. Do not invent a decision.",
            },
            {
                "role": "user",
                "content": "Synthetic case. A human has not written the parser.",
            },
        ]
    )
    raise NotImplementedError(
        "not implemented yet — owner: Melanie. "
        "The Nemotron reply would come back through Mubit and is not parsed into an Outcome."
    )
