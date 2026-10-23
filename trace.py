"""Append TraceEvent rows to traces.jsonl. One line per event."""

from __future__ import annotations

import os
from pathlib import Path

from contracts.models import TraceEvent
from paths import ROOT


def trace_path() -> Path:
    raw = os.environ.get("TRACE_PATH", "").strip()
    if raw:
        return Path(raw)
    return ROOT / "traces.jsonl"


def emit(event: TraceEvent, path: Path | None = None) -> None:
    target = path or trace_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as handle:
        handle.write(event.model_dump_json() + "\n")


def read_traces(case_id: str | None = None, path: Path | None = None) -> list[TraceEvent]:
    target = path or trace_path()
    if not target.exists():
        return []
    events: list[TraceEvent] = []
    for line in target.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        event = TraceEvent.model_validate_json(line)
        if case_id is None or event.case_id == case_id:
            events.append(event)
    return events
