"""`read_traces` streams the file and prefilters by case id."""

from __future__ import annotations

from datetime import datetime, timezone

from contracts.models import TraceEvent
from trace import emit, read_traces


def _event(case_id: str) -> TraceEvent:
    return TraceEvent(
        case_id=case_id,
        stage="gateway",
        started_at=datetime.now(timezone.utc),
        latency_ms=0,
        notes="x",
    )


def test_read_traces_prefilters_without_prefix_leak(tmp_path):
    path = tmp_path / "t.jsonl"
    for case_id in ("A", "AB", "B"):
        emit(_event(case_id), path=path)

    only_a = read_traces("A", path=path)
    assert [event.case_id for event in only_a] == ["A"]
    assert len(read_traces(path=path)) == 3
    assert read_traces("missing", path=path) == []
