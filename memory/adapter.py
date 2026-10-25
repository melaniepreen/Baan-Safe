"""Memory adapter. Owner: Melanie.

MEMORY_IMPL picks the backend:

- `mock` (developer default): fixture files via mocks/loader.py; corrections
  go to the local correction log; `store_record` is a no-op.
- `local` (hosted default): BaanSafe's own JSONL store, memory/local.py.
- `mubit`: memory/mubit.py against `/v2/control/*`. Dormant until Mubit
  exposes a memory API (the current product is an LLM gateway and answers
  404 `unknown_route` on those routes).

The gateway is the only retrieval caller and, at the end of every routed
turn, the only `store_record` caller.
"""

from __future__ import annotations

import os
from types import ModuleType
from typing import Any

from contracts.models import CaseState, Correction, MemoryItem, MemoryRecord
from memory import local, mubit
from mocks.loader import append_correction, load_memory

MODES = ("mock", "local", "mubit")

_LAST_ERROR: str | None = None


def memory_mode() -> str:
    return os.environ.get("MEMORY_IMPL", "mock").strip().lower() or "mock"


DORMANT_WARNING = (
    "MEMORY_IMPL=mubit is dormant: current Mubit is an LLM gateway with no "
    "memory API (/v2/control/* returns 404), so every turn retrieves nothing "
    "and every case-record write fails. Set MEMORY_IMPL=local."
)


def status() -> dict[str, Any]:
    """Mode plus whether it can hold memory. `GET /health` reports this so a
    stale `.env` is visible in one call instead of per-turn trace errors."""
    mode = memory_mode()
    dormant = mode == "mubit"
    return {"mode": mode, "dormant": dormant, "warning": DORMANT_WARNING if dormant else None}


def _backend() -> ModuleType | None:
    mode = memory_mode()
    if mode == "mubit":
        return mubit
    if mode == "local":
        return local
    return None


def _redact(text: str) -> str:
    key = os.environ.get("MUBIT_API_KEY", "").strip()
    return text.replace(key, "<redacted>") if key else text


def last_retrieve_error() -> str | None:
    """Why the last local or mubit retrieve returned []. None after a clean call.

    The gateway puts this on the `memory` trace stage so an empty context is
    never mistaken for an empty store. The text never carries the key.
    """
    return _LAST_ERROR


def retrieve(case: CaseState) -> list[MemoryItem]:
    global _LAST_ERROR
    backend = _backend()
    if backend is not None:
        try:
            items = backend.retrieve(case)
        except Exception as exc:
            # Live demo: empty context beats a failed turn if the store errs.
            _LAST_ERROR = f"{type(exc).__name__}: {_redact(str(exc))[:160]}"
            return []
        _LAST_ERROR = None
        return items
    _LAST_ERROR = None
    return load_memory(case.case_id)


def store_correction(correction: Correction) -> str:
    """Store one correction. Returns the note for the `memory_write` trace.

    Note shape: `status=ok|error; kind=correction; mode=<mode>; id=<id>; <detail>`
    so `GET /metrics` can count it with the case-record writes. In local or
    mubit mode a failed write keeps the correction in the local correction log
    instead of losing it with an HTTP 500, and the detail says so (never the
    key).
    """
    mode = memory_mode()
    head = f"kind=correction; mode={mode}; id={correction.correction_id}"
    backend = _backend()
    if backend is not None:
        try:
            backend.write_correction(correction)
        except Exception as exc:
            append_correction(correction)
            text = _redact(str(exc))[:160]
            return (
                f"status=error; {head}; error={type(exc).__name__}; "
                f"{mode} lesson ingest failed ({type(exc).__name__}: {text}); "
                f"correction {correction.correction_id} kept in the local log"
            )
        return f"status=ok; {head}; {mode} lesson ingested for correction {correction.correction_id}"
    append_correction(correction)
    return f"status=ok; {head}; mock correction {correction.correction_id}"


def store_record(record: MemoryRecord) -> bool:
    """Write one case record. Returns True when a write was sent.

    Local mode appends a `baansafe-case` row; mubit mode posts a fact. Both
    let errors propagate so the gateway can trace `status=error`. Mock mode is
    a no-op: fixture memory in `mocks/memory_context/` is hand-written and
    must not drift per run.
    """
    backend = _backend()
    if backend is None:
        return False
    backend.write(record)
    return True


def ingest_items(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Raw items (`{type, content, lane, source_case_id?, metadata?}`) for
    `scripts/seed_memory.py`. Not available in mock mode."""
    backend = _backend()
    if backend is None:
        raise RuntimeError(
            "MEMORY_IMPL=mock has no writable store; set MEMORY_IMPL=local or mubit."
        )
    return backend.ingest(items)
