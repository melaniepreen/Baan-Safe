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


_LAST_ERROR: str | None = None


def memory_mode() -> str:
    return os.environ.get("MEMORY_IMPL", "mock").strip().lower() or "mock"


def last_retrieve_error() -> str | None:
    """Why the last mubit retrieve returned []. None after a clean call.

    The gateway puts this on the `memory` trace stage so an empty context is
    never mistaken for an empty workspace. The text never carries the key.
    """
    return _LAST_ERROR


def retrieve(case: CaseState) -> list[MemoryItem]:
    global _LAST_ERROR
    if memory_mode() == "mubit":
        try:
            items = mubit.retrieve(case)
        except Exception as exc:
            # Live demo: empty context beats a failed turn if control plane errs.
            text = str(exc)
            key = os.environ.get("MUBIT_API_KEY", "").strip()
            if key:
                text = text.replace(key, "<redacted>")
            _LAST_ERROR = f"{type(exc).__name__}: {text[:160]}"
            return []
        _LAST_ERROR = None
        return items
    _LAST_ERROR = None
    return load_memory(case.case_id)


def store_correction(correction: Correction) -> str:
    """Store one correction. Returns a short note for the memory_write trace.

    In mubit mode the lesson goes to the control plane. When that write fails
    the correction is kept in the local correction log instead of being lost
    with an HTTP 500, and the note says so (never the key).
    """
    if memory_mode() == "mubit":
        try:
            mubit.write_correction(correction)
        except Exception as exc:
            append_correction(correction)
            text = str(exc)
            key = os.environ.get("MUBIT_API_KEY", "").strip()
            if key:
                text = text.replace(key, "<redacted>")
            return (
                f"mubit lesson ingest failed ({type(exc).__name__}: {text[:160]}); "
                f"correction {correction.correction_id} kept in the local log"
            )
        return f"mubit lesson ingested for correction {correction.correction_id}"
    append_correction(correction)
    return f"mock correction {correction.correction_id}"


def store_record(record: MemoryRecord) -> None:
    if memory_mode() == "mubit":
        mubit.write(record)
        return
    raise NotImplementedError(
        "not implemented yet — owner: Melanie. "
        "Mock mode stores corrections only. A full MemoryRecord write is the Mubit path."
    )
