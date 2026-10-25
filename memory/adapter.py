"""Mubit memory client adapter. Owner: Melanie.

MEMORY_IMPL=mock (default) reads mocks/loader.py. MEMORY_IMPL=mubit calls
memory.mubit against the Mubit control plane (/v2/control/query + ingest).
The gateway is the only retrieval caller.
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
        try:
            return mubit.retrieve(case)
        except Exception:
            # Live demo: empty context beats a failed turn if control plane errs.
            return []
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
