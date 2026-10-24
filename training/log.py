"""Append-only training event log.

Lines live in training/events/*.jsonl. A line is never edited or deleted.
A second event with the same content_hash is not written. Dedup at export
uses the same hash. The path is TRAINING_EVENTS_PATH, or
training/events/events.jsonl when that variable is unset.
"""

from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from contracts.training import TrainingEvent
from paths import ROOT


@dataclass(frozen=True)
class AppendResult:
    path: Path
    written: bool
    event: TrainingEvent


def events_path() -> Path:
    raw = os.environ.get("TRAINING_EVENTS_PATH", "").strip()
    if raw:
        return Path(raw)
    return ROOT / "training" / "events" / "events.jsonl"


@contextmanager
def _locked(path: Path) -> Iterator[object]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield handle
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def _hashes(text: str) -> set[str]:
    found: set[str] = set()
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        token = row.get("content_hash")
        if isinstance(token, str) and token:
            found.add(token)
    return found


def append_event(event: TrainingEvent, *, path: Path | None = None) -> AppendResult:
    """Append one event. Skip when content_hash is already in the file.

    The file is opened for append. This function does not rewrite earlier lines.
    """

    target = path or events_path()
    line = event.model_dump_json() + "\n"
    with _locked(target) as handle:
        handle.seek(0)
        existing = handle.read()
        if event.content_hash in _hashes(existing):
            return AppendResult(path=target, written=False, event=event)
        handle.seek(0, os.SEEK_END)
        handle.write(line)
        handle.flush()
    return AppendResult(path=target, written=True, event=event)


def read_events(path: Path | None = None) -> list[TrainingEvent]:
    target = path or events_path()
    if not target.exists():
        return []
    with _locked(target) as handle:
        handle.seek(0)
        text = handle.read()
    events: list[TrainingEvent] = []
    for line in text.splitlines():
        if line.strip():
            events.append(TrainingEvent.model_validate_json(line))
    return events
