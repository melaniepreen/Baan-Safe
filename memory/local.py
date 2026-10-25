"""BaanSafe's own memory store. Owner: Moly (Melanie reviews the record shape).

MEMORY_IMPL=local selects this module via memory.adapter. Current Mubit is an
LLM gateway with no memory API, so the case records, corrections, and
policy lessons that the gateway used to send to `/v2/control/*` live here:
an append-only JSONL file at MEMORY_LOCAL_PATH (default `var/memory.jsonl`,
gitignored; `/data/memory.jsonl` on the Modal volume), written under an
exclusive file lock like training/log.py.

One row per line:

    {id, kind, lane, content, source_case_id, location, needs, vulnerable,
     danger, priority, route, next_action, created_at, metadata}

`kind` is the entry type (`fact`, `lesson`, `rule`); the MemoryItem kind
comes from the lane (`baansafe-case` -> similar_case, `baansafe-correction`
-> correction, `baansafe-policy` -> policy). `content` is the summary from
memory/content.py: fields plus decision, never transcript text and never
`CaseState.resources`.

Retrieval scores every row against the case:

    +3  normalised location token overlap (lower-case, punctuation stripped,
        generic words such as "district" ignored)
    +2  per overlapping need
    +1  per overlapping vulnerable or danger token
    +1  a policy or correction row whose content mentions one of the case's
        needs or flags
   -inf a row whose source_case_id is the case being triaged

Rows scoring 0 are dropped. relevance = max(0.5, min(1, score / 6)). A
`baansafe-case` row whose location matched and that shares at least one need
is a repeat caller and is clamped to at least DUPLICATE_RELEVANCE so System 1
can `duplicate_merge` (5 / 6 alone would fall short). Top
`memory.retrieval_top_k` rows are returned.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from config.settings import require_decision
from contracts.models import CaseState, Correction, MemoryItem, MemoryRecord
from memory.content import (
    KIND_BY_LANE,
    LANE_CASE,
    LANE_CORRECTION,
    MemoryKind,
    correction_content,
    correction_task,
    record_content,
    source_case_id_from,
)
from paths import ROOT

# Mirrors system1.decide.DUPLICATE_RELEVANCE; tests pin the two together so
# memory/ does not import system1/.
DUPLICATE_RELEVANCE = 0.9

LOCATION_SCORE = 3
NEED_SCORE = 2
FLAG_SCORE = 1
MENTION_SCORE = 1
SCORE_SCALE = 6.0
MIN_RELEVANCE = 0.5

# Words that appear in most Thai addresses and say nothing about which one.
_GENERIC_LOCATION_WORDS = frozenset(
    {
        "district",
        "subdistrict",
        "sub",
        "province",
        "soi",
        "road",
        "rd",
        "street",
        "st",
        "khet",
        "khwaeng",
        "amphoe",
        "tambon",
        "moo",
        "village",
        "the",
        "of",
        "in",
        "near",
        "at",
    }
)
_NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)

ROW_FIELDS = (
    "id",
    "kind",
    "lane",
    "content",
    "source_case_id",
    "location",
    "needs",
    "vulnerable",
    "danger",
    "priority",
    "route",
    "next_action",
    "created_at",
    "metadata",
)

_CACHE: dict[str, Any] = {"path": None, "stamp": None, "rows": []}


def store_path() -> Path:
    raw = os.environ.get("MEMORY_LOCAL_PATH", "").strip()
    if raw:
        return Path(raw)
    return ROOT / "var" / "memory.jsonl"


def _top_k() -> int:
    value = int(require_decision("memory.retrieval_top_k"))
    return max(1, min(value, 50))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@contextmanager
def _locked(path: Path) -> Iterator[Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield handle
    finally:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        handle.close()


def normalise_tokens(text: str | None) -> set[str]:
    """Lower-case word tokens with punctuation stripped. Generic address words
    are removed so "X District, Bangkok" and "Y District, Bangkok" do not
    share "district"."""
    if not text:
        return set()
    cleaned = _NON_WORD.sub(" ", str(text).lower())
    return {token for token in cleaned.split() if token and token not in _GENERIC_LOCATION_WORDS}


def _row(
    *,
    kind: str,
    lane: str,
    content: str,
    source_case_id: str | None,
    location: str | None = None,
    needs: list[str] | None = None,
    vulnerable: list[str] | None = None,
    danger: list[str] | None = None,
    priority: str | None = None,
    route: str | None = None,
    next_action: str | None = None,
    metadata: dict[str, Any] | None = None,
    row_id: str | None = None,
) -> dict[str, Any]:
    return {
        "id": row_id or f"mem-{uuid.uuid4().hex[:12]}",
        "kind": kind,
        "lane": lane,
        "content": str(content)[:800],
        "source_case_id": source_case_id,
        "location": location,
        "needs": list(needs or []),
        "vulnerable": list(vulnerable or []),
        "danger": list(danger or []),
        "priority": priority,
        "route": route,
        "next_action": next_action,
        "created_at": _now(),
        "metadata": dict(metadata or {}),
    }


def append_rows(rows: list[dict[str, Any]], *, path: Path | None = None) -> Path:
    """Append rows under an exclusive lock. Lines are never edited or removed."""
    target = path or store_path()
    if not rows:
        return target
    text = "".join(json.dumps(row, ensure_ascii=False, default=str) + "\n" for row in rows)
    with _locked(target) as handle:
        handle.seek(0, os.SEEK_END)
        handle.write(text)
        handle.flush()
    return target


def load_rows(path: Path | None = None) -> list[dict[str, Any]]:
    """Every row in the file. Cached until the file's mtime or size changes."""
    target = path or store_path()
    if not target.exists():
        _CACHE.update(path=target, stamp=None, rows=[])
        return []
    stat = target.stat()
    stamp = (stat.st_mtime_ns, stat.st_size)
    if _CACHE["path"] == target and _CACHE["stamp"] == stamp:
        return list(_CACHE["rows"])
    with _locked(target) as handle:
        handle.seek(0)
        text = handle.read()
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict) and row.get("content"):
            rows.append(row)
    _CACHE.update(path=target, stamp=stamp, rows=rows)
    return list(rows)


def ingest(items: list[dict[str, Any]], *, path: Path | None = None) -> dict[str, Any]:
    """Append raw items in the shape `memory.mubit.ingest` accepts
    (`{type, content, lane, source_case_id?, metadata?}`). Used by
    `scripts/seed_memory.py` through the adapter."""
    rows = []
    for item in items:
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        meta = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        source = item.get("source_case_id") or meta.get("source_case_id") or source_case_id_from(content)
        rows.append(
            _row(
                kind=str(item.get("type") or "fact"),
                lane=str(item.get("lane") or LANE_CASE),
                content=content,
                source_case_id=str(source) if source else None,
                location=meta.get("location"),
                needs=meta.get("needs") if isinstance(meta.get("needs"), list) else None,
                priority=meta.get("priority"),
                route=meta.get("route"),
                next_action=meta.get("next_action"),
                metadata=meta,
            )
        )
    target = append_rows(rows, path=path)
    return {"path": str(target), "accepted": len(rows)}


def write(record: MemoryRecord) -> None:
    """Append one case row. Fields and the decision only."""
    fields = record.evidence
    decision = record.decision
    needs = [need.value for need in fields.needs]
    append_rows(
        [
            _row(
                row_id=record.record_id,
                kind="fact",
                lane=LANE_CASE,
                content=record_content(record),
                source_case_id=record.case_id,
                location=fields.location,
                needs=needs,
                vulnerable=list(fields.vulnerable),
                danger=list(fields.danger),
                priority=decision.final_priority.value,
                route=decision.final_route.value,
                next_action=decision.next_action.value,
                metadata={
                    "record_id": record.record_id,
                    "outcome_label": record.outcome_label,
                    "corrections": len(record.corrections),
                    "medical": fields.medical,
                },
            )
        ]
    )


def write_correction(correction: Correction) -> None:
    append_rows(
        [
            _row(
                row_id=f"corr-{correction.correction_id}",
                kind="lesson",
                lane=LANE_CORRECTION,
                content=correction_content(correction),
                source_case_id=correction.case_id,
                metadata={
                    "correction_id": correction.correction_id,
                    "task": correction_task(correction),
                    "field": correction.field,
                },
            )
        ]
    )


def _row_kind(row: dict[str, Any]) -> MemoryKind:
    lane = str(row.get("lane") or "").strip().lower()
    kind = KIND_BY_LANE.get(lane)
    if kind is not None:
        return kind
    raw = str(row.get("kind") or "").strip().lower()
    if raw == "lesson":
        return "correction"
    if raw == "rule":
        return "policy"
    if raw == "prior_failure":
        return "prior_failure"
    return "similar_case"


def _case_terms(case: CaseState) -> set[str]:
    """Words a policy or correction row has to mention to count."""
    fields = case.fields
    terms: set[str] = set()
    for need in fields.needs:
        terms |= normalise_tokens(need.value)
    for word in (*fields.vulnerable, *fields.danger, *case.policy_flags):
        terms |= normalise_tokens(str(word).replace(":", " ").replace("_", " "))
    if fields.medical:
        terms.add("medical")
    return terms


def score_row(row: dict[str, Any], case: CaseState) -> tuple[float, bool]:
    """(score, repeat_caller). -inf for the case's own rows."""
    source = row.get("source_case_id")
    if source and str(source) == case.case_id:
        return float("-inf"), False
    fields = case.fields
    score = 0.0
    location_hit = bool(normalise_tokens(row.get("location")) & normalise_tokens(fields.location))
    if location_hit:
        score += LOCATION_SCORE
    case_needs = {need.value for need in fields.needs}
    row_needs = {str(need) for need in (row.get("needs") or [])}
    shared_needs = case_needs & row_needs
    score += NEED_SCORE * len(shared_needs)
    case_flags: set[str] = set()
    for word in (*fields.vulnerable, *fields.danger):
        case_flags |= normalise_tokens(str(word).replace(":", " ").replace("_", " "))
    row_flags: set[str] = set()
    for word in (*(row.get("vulnerable") or []), *(row.get("danger") or [])):
        row_flags |= normalise_tokens(str(word).replace(":", " ").replace("_", " "))
    score += FLAG_SCORE * len(case_flags & row_flags)
    lane = str(row.get("lane") or "").strip().lower()
    if lane != LANE_CASE:
        content_tokens = normalise_tokens(row.get("content"))
        if content_tokens & _case_terms(case):
            score += MENTION_SCORE
    repeat_caller = lane == LANE_CASE and location_hit and bool(shared_needs)
    return score, repeat_caller


def retrieve(case: CaseState) -> list[MemoryItem]:
    """Top-k scored rows as MemoryItems. The case's own rows never return."""
    limit = _top_k()
    scored: list[tuple[float, bool, int, dict[str, Any]]] = []
    for index, row in enumerate(load_rows()):
        score, repeat_caller = score_row(row, case)
        if score <= 0:
            continue
        scored.append((score, repeat_caller, index, row))
    # Highest score first; newest row first on a tie.
    scored.sort(key=lambda entry: (entry[0], entry[2]), reverse=True)
    items: list[MemoryItem] = []
    for score, repeat_caller, _order, row in scored[:limit]:
        relevance = max(MIN_RELEVANCE, min(1.0, score / SCORE_SCALE))
        if repeat_caller:
            relevance = max(relevance, DUPLICATE_RELEVANCE)
        content = str(row.get("content") or "").strip()
        source = row.get("source_case_id") or source_case_id_from(content)
        items.append(
            MemoryItem(
                memory_id=str(row.get("id") or f"local-{len(items) + 1}")[:120],
                kind=_row_kind(row),
                summary=content[:500],
                relevance=relevance,
                source_case_id=str(source) if source else None,
            )
        )
    return items
