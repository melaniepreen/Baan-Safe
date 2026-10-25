"""BaanSafe's own memory store (MEMORY_IMPL=local): JSONL round trip, scoring,
own-case exclusion, the repeat-caller duplicate merge through the API, and
the `/metrics` memory block. No network, no Mubit key."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.main import app
from contracts.models import (
    CaseState,
    Correction,
    ExtractedFields,
    MemoryRecord,
    NextAction,
    Outcome,
    Priority,
    Route,
    RouterDecision,
    System,
    TranscriptTurn,
)
from memory import adapter, local
from memory.content import LANE_CASE, LANE_CORRECTION, LANE_POLICY
from system1.decide import DUPLICATE_RELEVANCE


@pytest.fixture
def store(monkeypatch, tmp_path) -> Path:
    path = tmp_path / "memory.jsonl"
    monkeypatch.setenv("MEMORY_IMPL", "local")
    monkeypatch.setenv("MEMORY_LOCAL_PATH", str(path))
    return path


def _case(
    case_id: str = "case-a",
    *,
    location: str | None = "Mae Mo District, Lampang",
    needs=("water",),
    vulnerable=(),
    danger=(),
    flags=(),
) -> CaseState:
    return CaseState(
        case_id=case_id,
        caller_id_hash=f"synthetic:{case_id}",
        transcript=[TranscriptTurn(t_ms=0, speaker="caller", text="We need help.")],
        fields=ExtractedFields(
            location=location,
            location_confidence=0.94,
            people_count=3,
            vulnerable=list(vulnerable),
            medical=False,
            danger=list(danger),
            needs=list(needs),
        ),
        policy_flags=list(flags),
        received_at=datetime.now(timezone.utc),
    )


def _record(case: CaseState, corrections=()) -> MemoryRecord:
    outcome = Outcome(
        system=System.system_1,
        outcome="fast_route",
        priority=Priority.P3,
        needs=case.fields.needs,
        route=Route.welfare_distribution,
        confidence=0.9,
        reason="Clear fast-path request.",
        requires_human=False,
        escalate=False,
    )
    decision = RouterDecision(
        case_id=case.case_id,
        next_action=NextAction.create_provisional_dispatch,
        final_priority=Priority.P3,
        final_route=Route.welfare_distribution,
        requires_human=False,
        source_outcomes=[outcome],
    )
    return MemoryRecord(
        record_id=f"rec-{case.case_id}-1",
        case_id=case.case_id,
        case_summary="system_1 fast_route after 1 turn(s).",
        evidence=case.fields,
        decision=decision,
        corrections=list(corrections),
    )


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_duplicate_relevance_matches_system1():
    assert local.DUPLICATE_RELEVANCE == DUPLICATE_RELEVANCE


def test_write_then_retrieve_round_trip(store):
    first = _case("case-a")
    assert adapter.store_record(_record(first)) is True
    rows = _rows(store)
    assert len(rows) == 1
    row = rows[0]
    assert set(row) == set(local.ROW_FIELDS)
    assert row["lane"] == LANE_CASE
    assert row["kind"] == "fact"
    assert row["source_case_id"] == "case-a"
    assert row["location"] == "Mae Mo District, Lampang"
    assert row["needs"] == ["water"]
    assert row["route"] == "welfare_distribution"
    assert row["priority"] == "P3"
    assert row["next_action"] == "create_provisional_dispatch"
    assert row["content"].startswith("Case case-a: needs=water; location=Mae Mo District, Lampang;")
    # No transcript text and no resources in the stored row.
    assert "We need help" not in json.dumps(row)
    assert "caller_ip" not in json.dumps(row)

    second = _case("case-b")
    items = adapter.retrieve(second)
    assert adapter.last_retrieve_error() is None
    assert len(items) == 1
    item = items[0]
    assert item.kind == "similar_case"
    assert item.source_case_id == "case-a"
    assert item.memory_id == "rec-case-a-1"
    assert item.summary == row["content"][:500]
    assert item.relevance >= DUPLICATE_RELEVANCE


def test_repeat_caller_same_location_and_need_is_duplicate_eligible(store):
    adapter.store_record(_record(_case("case-first", needs=("water",))))
    repeat = _case("case-second", needs=("water", "food"))
    items = local.retrieve(repeat)
    assert items and items[0].kind == "similar_case"
    assert items[0].source_case_id == "case-first"
    assert items[0].relevance >= DUPLICATE_RELEVANCE
    # Same district, different need: a neighbour, not a repeat caller.
    neighbour = _case("case-third", needs=("shelter",))
    items = local.retrieve(neighbour)
    assert items and items[0].relevance == pytest.approx(0.5)
    assert items[0].relevance < DUPLICATE_RELEVANCE
    # Same need, different district: not a repeat caller either.
    elsewhere = _case("case-fourth", location="Vadhana District, Bangkok", needs=("water",))
    items = local.retrieve(elsewhere)
    assert items and items[0].relevance < DUPLICATE_RELEVANCE


def test_scoring_orders_rows_and_drops_zero_scores(store):
    # Rows: full match (location + need + vulnerable), need only, nothing shared.
    adapter.store_record(_record(_case("case-full", vulnerable=["elderly"])))
    adapter.store_record(_record(_case("case-need", location="Vadhana District, Bangkok")))
    adapter.store_record(
        _record(_case("case-none", location="Hat Yai District, Songkhla", needs=("shelter",)))
    )
    case = _case("case-now", vulnerable=["elderly"])
    scores = {row["source_case_id"]: local.score_row(row, case)[0] for row in local.load_rows()}
    assert scores["case-full"] == local.LOCATION_SCORE + local.NEED_SCORE + local.FLAG_SCORE
    assert scores["case-need"] == local.NEED_SCORE
    assert scores["case-none"] == 0
    items = local.retrieve(case)
    assert [item.source_case_id for item in items] == ["case-full", "case-need"]
    assert items[0].relevance == pytest.approx(1.0)
    assert items[1].relevance == pytest.approx(0.5)
    assert items[0].relevance > items[1].relevance


def test_generic_location_words_do_not_match(store):
    adapter.store_record(_record(_case("case-a", location="Vadhana District, Bangkok")))
    other = _case("case-b", location="Khlong Toei District, Bangkok", needs=("food",))
    # "district" is generic; "bangkok" is a real shared token (+3) but no need overlaps.
    items = local.retrieve(other)
    assert items and items[0].relevance == pytest.approx(0.5)
    assert items[0].relevance < DUPLICATE_RELEVANCE
    assert local.normalise_tokens("Khlong Toei District, Bangkok.") == {"khlong", "toei", "bangkok"}


def test_own_case_rows_are_excluded(store):
    case = _case("case-self")
    adapter.store_record(_record(case))
    assert local.retrieve(case) == []
    score, repeat = local.score_row(local.load_rows()[0], case)
    assert score == float("-inf") and repeat is False
    # Another case at the same place still sees it.
    assert local.retrieve(_case("case-other"))[0].source_case_id == "case-self"


def test_top_k_limits_the_result(store):
    for index in range(8):
        adapter.store_record(_record(_case(f"case-{index}")))
    items = local.retrieve(_case("case-new"))
    assert len(items) == 5  # memory.retrieval_top_k


def test_policy_lessons_surface_by_need_and_flag(store):
    adapter.ingest_items(
        [
            {
                "type": "rule",
                "content": "[policy:SPHERE-WASH-15L] 15 litres of water per person per day is not a ceiling.",
                "lane": LANE_POLICY,
                "metadata": {"policy_id": "SPHERE-WASH-15L"},
            },
            {
                "type": "lesson",
                "content": "[policy:IFRC-PGI-CHILD-DEFINITION] A safeguarding flag always requires a human.",
                "lane": LANE_POLICY,
            },
            {
                "type": "rule",
                "content": "[policy:MOF-2569-CASH-DISCRETION] Cash assistance is a human decision.",
                "lane": LANE_POLICY,
            },
        ]
    )
    rows = _rows(store)
    assert all(row["lane"] == LANE_POLICY and row["source_case_id"] is None for row in rows)
    items = local.retrieve(_case("case-w", needs=("water",)))
    assert [item.kind for item in items] == ["policy"]
    assert "SPHERE-WASH-15L" in items[0].summary
    assert items[0].relevance == pytest.approx(0.5)
    items = local.retrieve(_case("case-s", needs=("food",), flags=("safeguarding",)))
    assert [item.kind for item in items] == ["policy"]
    assert "IFRC-PGI-CHILD-DEFINITION" in items[0].summary
    assert local.retrieve(_case("case-x", needs=("shelter",))) == []


def test_correction_round_trip_and_note(store):
    correction = Correction(
        correction_id="corr-1",
        case_id="case-a",
        corrected_by="operator",
        field="priority",
        old_value="P3",
        new_value="P2",
        reason="elderly in the household need water",
        created_at=datetime.now(timezone.utc),
    )
    note = adapter.store_correction(correction)
    assert note.startswith("status=ok; kind=correction; mode=local; id=corr-1")
    row = _rows(store)[0]
    assert row["lane"] == LANE_CORRECTION
    assert row["kind"] == "lesson"
    assert row["source_case_id"] == "case-a"
    assert row["metadata"]["correction_id"] == "corr-1"
    # Another case asking for water sees the lesson; the corrected case does not.
    items = local.retrieve(_case("case-b", needs=("water",)))
    assert [item.kind for item in items] == ["correction"]
    assert items[0].source_case_id == "case-a"
    assert local.retrieve(_case("case-a")) == []


def test_write_error_soft_fails_in_adapter(store, monkeypatch):
    def boom(*args, **kwargs):
        raise OSError("disk full at /secret/path")

    monkeypatch.setattr(local, "append_rows", boom)
    with pytest.raises(OSError):
        adapter.store_record(_record(_case("case-a")))
    correction = Correction(
        correction_id="corr-err",
        case_id="case-a",
        corrected_by="operator",
        field="priority",
        old_value="P3",
        new_value="P2",
        reason="kept locally",
        created_at=datetime.now(timezone.utc),
    )
    note = adapter.store_correction(correction)
    assert note.startswith("status=error; kind=correction; mode=local; id=corr-err")
    assert "kept in the local log" in note
    from mocks.loader import read_corrections

    assert any(row.correction_id == "corr-err" for row in read_corrections())

    monkeypatch.setattr(local, "load_rows", boom)
    assert adapter.retrieve(_case("case-b")) == []
    assert adapter.last_retrieve_error() == "OSError: disk full at /secret/path"


def test_concurrent_appends_keep_every_line(store):
    def worker(start: int) -> None:
        for index in range(start, start + 20):
            local.write(_record(_case(f"case-{index}")))

    threads = [threading.Thread(target=worker, args=(base,)) for base in (0, 100, 200, 300)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    rows = _rows(store)
    assert len(rows) == 80
    assert len({row["id"] for row in rows}) == 80


def test_cache_follows_the_file(store):
    adapter.store_record(_record(_case("case-a")))
    assert len(local.load_rows()) == 1
    assert len(local.load_rows()) == 1  # cached
    adapter.store_record(_record(_case("case-b")))
    assert len(local.load_rows()) == 2
    assert local.load_rows(Path(str(store) + ".missing")) == []


def test_mock_mode_ignores_the_local_file(monkeypatch, tmp_path):
    monkeypatch.setenv("MEMORY_IMPL", "mock")
    monkeypatch.setenv("MEMORY_LOCAL_PATH", str(tmp_path / "memory.jsonl"))
    assert adapter.store_record(_record(_case("case-a"))) is False
    assert not (tmp_path / "memory.jsonl").exists()
    with pytest.raises(RuntimeError, match="MEMORY_IMPL=local or mubit"):
        adapter.ingest_items([{"type": "rule", "content": "x", "lane": LANE_POLICY}])


def test_seed_memory_writes_the_local_file(store, capsys):
    from scripts import seed_memory

    assert seed_memory.run(["--json", "--case-fact", "case-seed"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["mode"] == "local"
    assert report["ingested"] == report["count"]
    rows = _rows(store)
    assert len(rows) == report["count"]
    assert sum(row["lane"] == LANE_POLICY for row in rows) == report["count"] - 1
    fact = [row for row in rows if row["lane"] == LANE_CASE][0]
    assert fact["source_case_id"] == "case-seed"
    assert fact["location"] == "Watthana District, Bangkok"
    # Second run: every policy tag is present, only the case fact is written.
    assert seed_memory.run(["--json", "--case-fact", "case-seed"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["skipped"] == report["count"] - 1
    assert report["ingested"] == 1
    assert len(_rows(store)) == len(rows) + 1
    # --path overrides MEMORY_LOCAL_PATH.
    other = store.parent / "other.jsonl"
    assert seed_memory.run(["--json", "--path", str(other)]) == 0
    assert other.exists()


def test_seed_memory_refuses_mock_mode_and_names_both_backends(monkeypatch, capsys):
    from scripts import seed_memory

    monkeypatch.setenv("MEMORY_IMPL", "mock")
    assert seed_memory.run([]) == 2
    err = capsys.readouterr().err
    assert "MEMORY_IMPL=local" in err and "MEMORY_IMPL=mubit" in err


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_api_two_cases_same_location_duplicate_merge_and_metrics(client, store, monkeypatch):
    monkeypatch.setenv("S1_IMPL", "real")
    # Case 1: fixture F01 (water, Mae Mo District, Lampang). Turn 1 writes its record.
    client.post("/cases", json={"fixture_id": "F01"})
    first = client.post(
        "/cases/F01/turns",
        json={"t_ms": 90000, "speaker": "operator", "text": "Noted the water request."},
    )
    assert first.status_code == 200
    assert first.json()["decision"]["final_route"] == "welfare_distribution"
    trace = client.get("/cases/F01/trace").json()
    memory_stages = [e for e in trace if e["stage"] == "memory"]
    assert memory_stages and "mode=local; items=0" in memory_stages[-1]["notes"]
    writes = [e for e in trace if e["stage"] == "memory_write"]
    assert len(writes) == 1
    assert "status=ok" in writes[0]["notes"] and "mode=local" in writes[0]["notes"]
    assert len(_rows(store)) == 1

    # F01's own turn 2 sees only its own record, which is excluded: no merge.
    own = client.post(
        "/cases/F01/turns",
        json={"t_ms": 95000, "speaker": "caller", "text": "Still here."},
    )
    assert own.json()["decision"]["final_route"] == "welfare_distribution"
    assert own.json()["case"]["memory_context"] == []
    assert len(_rows(store)) == 2

    # Case 2: a different case id at the same location with the same need.
    # Explicit fields keep the extractor off and no System 2 trigger fires.
    created = client.post(
        "/cases",
        json={
            "transcript": [
                {"t_ms": 0, "speaker": "caller", "text": "We still need drinking water."}
            ],
            "fields": {
                "location": "Mae Mo District, Lampang",
                "location_confidence": 0.94,
                "people_count": 3,
                "vulnerable": [],
                "medical": False,
                "danger": [],
                "needs": ["water"],
            },
        },
    )
    assert created.status_code == 200
    case_id = created.json()["case"]["case_id"]
    assert case_id != "F01"
    second = client.post(
        f"/cases/{case_id}/turns",
        json={"t_ms": 5000, "speaker": "operator", "text": "Which house?"},
    )
    assert second.status_code == 200
    decision = second.json()["decision"]
    assert decision["final_route"] == "duplicate_merge"
    assert decision["source_outcomes"][0]["system"] == "system_1"
    assert "F01" in decision["source_outcomes"][0]["reason"]
    context = second.json()["case"]["memory_context"]
    assert context and context[0]["kind"] == "similar_case"
    assert context[0]["source_case_id"] == "F01"
    assert context[0]["relevance"] >= DUPLICATE_RELEVANCE

    trace = client.get(f"/cases/{case_id}/trace").json()
    memory_stages = [e for e in trace if e["stage"] == "memory"]
    assert memory_stages
    items = int(memory_stages[-1]["notes"].split("items=")[1].split(";")[0])
    assert items >= 1
    assert "retrieve_error" not in memory_stages[-1]["notes"]
    # Turn 2 wrote its own record too; the file now holds both cases.
    rows = _rows(store)
    assert [row["source_case_id"] for row in rows] == ["F01", "F01", case_id]

    memory = client.get("/metrics").json()["memory"]
    assert memory["mode"] == "local"
    assert memory["retrieve_count"] >= 2
    assert memory["hit_count"] >= 1
    assert memory["item_total"] >= 1
    assert memory["write_count"] == 3
    assert memory["write_error_count"] == 0
    assert memory["avg_write_latency_ms"] is not None
    assert memory["duplicate_merge_count"] == 1
