"""scripts/mubit_requests.py: request ids from mubit_chat traces, joined to the
case's latest system_2 outcome. Temp trace file, no network."""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from contracts.models import Need, Outcome, Priority, Route, System, TraceEvent
from trace import emit

ROOT = Path(__file__).resolve().parents[1]
MREQ_A = "mreq_" + "a" * 32
MREQ_B = "mreq_" + "b" * 32


def _load():
    spec = importlib.util.spec_from_file_location("mubit_requests", ROOT / "scripts" / "mubit_requests.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _at(minute: int, second: int = 0) -> datetime:
    return datetime(2026, 10, 25, 4, minute, second, tzinfo=timezone.utc)


def _chat(case_id: str, when: datetime, note: str, latency: int = 500) -> TraceEvent:
    return TraceEvent(
        case_id=case_id,
        stage="mubit_chat",
        started_at=when,
        latency_ms=latency,
        model="nvidia/nemotron-3-nano-30b-a3b",
        notes=note,
    )


def _s2_outcome() -> Outcome:
    return Outcome(
        system=System.system_2,
        outcome="reasoned_recommendation",
        priority=Priority.P2,
        needs=[Need.rescue],
        route=Route.rescue_coordination,
        confidence=0.8,
        reason="Synthetic household on the roof with rising water.",
        reasoning="Nemotron proposed rescue coordination.",
        requires_human=False,
        escalate=False,
        latency_ms=900,
    )


@pytest.fixture
def traces(tmp_path) -> Path:
    path = tmp_path / "traces.jsonl"
    # Live hop with an id (oldest), then a cache replay of a recorded id (newest),
    # then a hop that carried no id. Written out of time order on purpose.
    emit(_chat("C-live", _at(0), f"mubit chat host=api.mubit.ai status=ok request_id={MREQ_A}"), path=path)
    emit(_chat("C-noid", _at(1), "mubit chat host=api.mubit.ai status=http_429", latency=300), path=path)
    emit(
        _chat("C-live", _at(2), f"mubit chat host=s2_cache status=cache_hit request_id={MREQ_B} (recorded)", latency=0),
        path=path,
    )
    emit(
        TraceEvent(
            case_id="C-live",
            stage="system_2",
            started_at=_at(0, 1),
            latency_ms=900,
            model="nvidia/nemotron-3-nano-30b-a3b",
            outcome=_s2_outcome(),
        ),
        path=path,
    )
    return path


def test_parse_note_splits_id_status_and_recorded_marker():
    mod = _load()
    assert mod.parse_note(f"mubit chat host=api.mubit.ai status=ok request_id={MREQ_A}") == (MREQ_A, "ok", False)
    assert mod.parse_note(f"mubit chat host=s2_cache status=cache_hit request_id={MREQ_B} (recorded)") == (
        MREQ_B,
        "cache_hit",
        True,
    )
    assert mod.parse_note("mubit chat host=api.mubit.ai status=timeout") == (None, "timeout", False)
    assert mod.parse_note(None) == (None, None, False)


def test_json_lists_request_rows_joined_to_the_case_outcome(traces, capsys):
    mod = _load()
    assert mod.main(["--path", str(traces), "--json"]) == 0
    captured = capsys.readouterr()
    rows = json.loads(captured.out)
    assert len(rows) == 2
    assert [row["request_id"] for row in rows] == [MREQ_A, MREQ_B]
    assert [row["recorded"] for row in rows] == [False, True]
    assert [row["status"] for row in rows] == ["ok", "cache_hit"]
    assert [row["latency_ms"] for row in rows] == [500, 0]
    assert [row["started_at"] for row in rows] == ["2026-10-25T04:00Z", "2026-10-25T04:02Z"]
    for row in rows:
        assert set(row) == {
            "started_at",
            "case_id",
            "request_id",
            "status",
            "recorded",
            "latency_ms",
            "priority",
            "route",
        }
        assert row["case_id"] == "C-live"
        assert row["priority"] == "P2"
        assert row["route"] == "rescue_coordination"
    assert "skipped 1 rows without request_id" in captured.err
    # Only parsed fields: the note's host never reaches stdout.
    assert "host=" not in captured.out
    assert "api.mubit.ai" not in captured.out
    assert str(traces.parent) not in captured.out + captured.err


def test_n_one_returns_the_latest_only(traces, capsys):
    mod = _load()
    assert mod.main(["--path", str(traces), "--n", "1", "--json"]) == 0
    rows = json.loads(capsys.readouterr().out)
    assert len(rows) == 1
    assert rows[0]["request_id"] == MREQ_B
    assert rows[0]["recorded"] is True


def test_table_has_header_rows_and_trailer(traces, capsys):
    mod = _load()
    assert mod.main(["--path", str(traces)]) == 0
    out = capsys.readouterr().out
    lines = out.strip().splitlines()
    assert lines[0].split() == [
        "started_at",
        "|",
        "case_id",
        "|",
        "request_id",
        "|",
        "status",
        "|",
        "recorded",
        "|",
        "latency_ms",
        "|",
        "priority",
        "|",
        "route",
    ]
    assert lines[-1] == "skipped 1 rows without request_id"
    body = lines[2:-1]
    assert len(body) == 2
    assert MREQ_A in body[0] and " no " in body[0] and "P2" in body[0]
    assert MREQ_B in body[1] and " yes " in body[1] and "rescue_coordination" in body[1]
    assert "host=" not in out


def test_missing_trace_file_exits_one_without_the_path(tmp_path, capsys):
    mod = _load()
    missing = tmp_path / "secret-dir" / "traces.jsonl"
    assert mod.main(["--path", str(missing)]) == 1
    err = capsys.readouterr().err
    assert "traces.jsonl" in err
    assert str(tmp_path) not in err


def test_no_outcome_for_the_case_leaves_priority_and_route_empty(tmp_path, capsys):
    mod = _load()
    path = tmp_path / "traces.jsonl"
    emit(_chat("C-alone", _at(5), f"mubit chat host=api.mubit.ai status=ok request_id={MREQ_A}"), path=path)
    assert mod.main(["--path", str(path), "--json"]) == 0
    captured = capsys.readouterr()
    rows = json.loads(captured.out)
    assert rows == [
        {
            "started_at": "2026-10-25T04:05Z",
            "case_id": "C-alone",
            "request_id": MREQ_A,
            "status": "ok",
            "recorded": False,
            "latency_ms": 500,
            "priority": None,
            "route": None,
        }
    ]
    assert "skipped 0 rows without request_id" in captured.err
