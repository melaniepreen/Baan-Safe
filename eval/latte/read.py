"""Read latte-bench result files. Unknown fields are dropped, including secrets."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_SECRET = re.compile(r"mbt_[A-Za-z0-9_-]+|sk-[A-Za-z0-9_-]+|Bearer\s+\S+", re.I)

REFERENCE_FIELDS = (
    "mode",
    "task",
    "seed",
    "passed",
    "score",
    "shape_iou",
    "boundary_f1",
    "precision",
    "outcome",
    "api_calls",
    "calibration_ready",
    "commit",
)


def redact(value: str) -> str:
    return _SECRET.sub("[redacted]", value)


@dataclass(frozen=True)
class NotesRow:
    model: str
    no_notes_mean: float | None
    notes_mean: float | None
    no_notes_passes: int | None
    notes_passes: int | None


@dataclass(frozen=True)
class Study:
    present: bool
    commit: str | None
    tag: str | None
    rows: tuple[NotesRow, ...]
    incomplete: int
    note: str


def _mean(group: dict) -> float | None:
    curves = group.get("curves")
    if not isinstance(curves, list) or not curves:
        return None
    last = curves[-1]
    if not isinstance(last, dict):
        return None
    value = last.get("mean")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def _passes(group: dict) -> int | None:
    value = group.get("passes")
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def load_reference(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"mode": "calibrated-reference", "unreadable": True}
    if not isinstance(payload, dict):
        return {"mode": "calibrated-reference", "unreadable": True}
    kept: dict = {}
    for field in REFERENCE_FIELDS:
        if field not in payload:
            continue
        value = payload[field]
        if isinstance(value, str):
            kept[field] = redact(value)
        elif isinstance(value, (int, float, bool)) or value is None:
            kept[field] = value
    return kept


def load_study(path: Path) -> Study:
    if not path.is_file():
        return Study(False, None, None, (), 0, "The published comparison file is not in the checkout.")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return Study(True, None, None, (), 0, "The published comparison file could not be read.")
    if not isinstance(payload, dict):
        return Study(True, None, None, (), 0, "The published comparison file could not be read.")
    identity = payload.get("identity") if isinstance(payload.get("identity"), dict) else {}
    commit = identity.get("commit")
    tag = identity.get("tag")
    grouped: dict[str, dict[str, dict]] = {}
    incomplete_models: set[str] = set()
    for group in payload.get("groups") or []:
        if not isinstance(group, dict):
            continue
        mode = group.get("mode")
        if mode not in ("notes", "no-notes"):
            continue
        model = group.get("model")
        if not isinstance(model, str) or not model:
            continue
        if group.get("complete") is not True:
            incomplete_models.add(model)
            continue
        grouped.setdefault(model, {})[mode] = group
    rows: list[NotesRow] = []
    for model in sorted(grouped):
        pair = grouped[model]
        if "notes" not in pair or "no-notes" not in pair:
            incomplete_models.add(model)
            continue
        rows.append(
            NotesRow(
                model=redact(model),
                no_notes_mean=_mean(pair["no-notes"]),
                notes_mean=_mean(pair["notes"]),
                no_notes_passes=_passes(pair["no-notes"]),
                notes_passes=_passes(pair["notes"]),
            )
        )
    return Study(
        present=True,
        commit=redact(commit) if isinstance(commit, str) else None,
        tag=redact(tag) if isinstance(tag, str) else None,
        rows=tuple(rows),
        incomplete=len(incomplete_models),
        note="",
    )
