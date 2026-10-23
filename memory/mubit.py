"""Mubit read/write interface. Owner: Melanie.

Tonight the API uses mocks/loader.py when MEMORY_IMPL=mock. These functions
raise until a human wires Mubit. They do not call the network.
"""

from __future__ import annotations

import os

from config.settings import unset_decisions
from contracts.models import CaseState, Correction, MemoryItem, MemoryRecord

_DECISIONS = [
    "memory.mubit_project",
    "memory.retrieval_top_k",
    "memory.token_budget",
]


def _message() -> str:
    missing = unset_decisions(_DECISIONS)
    extra = ""
    if missing:
        extra = " Unset TODO_HUMAN: " + ", ".join(missing) + "."
    if not os.environ.get("MUBIT_API_KEY"):
        extra += " MUBIT_API_KEY is not set."
    return "not implemented yet — owner: Melanie." + extra


def retrieve(case: CaseState) -> list[MemoryItem]:
    del case
    raise NotImplementedError(_message())


def write(record: MemoryRecord) -> None:
    del record
    raise NotImplementedError(_message())


def write_correction(correction: Correction) -> None:
    del correction
    raise NotImplementedError(_message())
