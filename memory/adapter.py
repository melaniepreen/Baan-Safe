"""Mubit memory client adapter. Owner: Melanie.

MEMORY_IMPL=mock reads mocks/loader.py. MEMORY_IMPL=mubit calls memory.mubit,
which raises until a human wires the network client. The gateway is the only
retrieval caller. There is no retrieval step in front of the gateway.
"""

from __future__ import annotations

import os

from contracts.models import CaseState, Correction, MemoryItem, MemoryRecord
from memory import mubit
from mocks.loader import append_correction, load_memory


def memory_mode() -> str:
    return os.environ.get("MEMORY_IMPL", "mock").strip().lower() or "mock"


def retrieve(case: CaseState) -> list[MemoryItem]:
    if memory_mode() == "mubit":
        return mubit.retrieve(case)
    return load_memory(case.case_id)


def store_correction(correction: Correction) -> None:
    if memory_mode() == "mubit":
        mubit.write_correction(correction)
        return
    append_correction(correction)


def store_record(record: MemoryRecord) -> None:
    if memory_mode() == "mubit":
        mubit.write(record)
        return
    raise NotImplementedError(
        "not implemented yet — owner: Melanie. "
        "Mock mode stores corrections only. A full MemoryRecord write is the Mubit path."
    )
