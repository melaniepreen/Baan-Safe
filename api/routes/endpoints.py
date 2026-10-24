"""Every Phase 1 endpoint. Human logic is reached only through the impl switches."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from api.deps import enrich_impl, impl_snapshot, not_ready, s1_impl, s2_impl
from api.store import StoredCase, get, put
from contracts.models import (
    CaseState,
    Correction,
    ExtractedFields,
    MemoryItem,
    RouterDecision,
    TraceEvent,
    TranscriptTurn,
)
from contracts.training import (
    AdaptError,
    InputRef,
    Lang,
    Source,
    Task,
    adapt_correction,
    correction_is_v1,
)
from enrich.context import location_context
from eval.replay import replay
from fixtures.load import all_ids, list_entries, load_case, load_fixture
from config.settings import DecisionRequired
from gateway.route import handle
from ingest.db import DB_PATH, connect
from memory.adapter import retrieve, store_correction
from training.log import append_event
from mocks.loader import (
    load_dispatch_resources,
    load_s1_stub,
    read_corrections,
)
from paths import ROOT
from system1 import decide as system1
from system2 import decide as system2
from trace import emit, read_traces

router = APIRouter()


class CreateCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_id: str | None = None
    transcript: list[TranscriptTurn] | None = None
    fields: ExtractedFields | None = None
    caller_id_hash: str | None = None


class CaseCreated(BaseModel):
    case: CaseState
    fixture_id: str | None = None


class TurnResult(BaseModel):
    case: CaseState
    decision: RouterDecision


class CaseDetail(BaseModel):
    case: CaseState
    latest_decision: RouterDecision | None
    decision_history: list[RouterDecision]


class CorrectionIn(BaseModel):
    """Legacy correction body, plus optional TrainingEvent v1 fields.

    A body that only sends corrected_by, field, old_value, new_value, and
    reason still validates. v1 fields are copied onto Correction and then
    through adapt_correction. input_ref, when set, supplies the case link
    and overrides the flat turn_ids, lang, policy_ids, and memory_ref.
    """

    model_config = ConfigDict(extra="forbid")

    corrected_by: Literal["operator", "supervisor", "caseworker"]
    field: str = Field(min_length=1)
    old_value: Any = None
    new_value: Any = None
    reason: str = Field(min_length=1)
    task: Task | None = None
    group_id: str | None = None
    turn_ids: list[str] = Field(default_factory=list)
    lang: Lang | None = None
    policy_ids: list[str] = Field(default_factory=list)
    memory_ref: str | None = None
    input_ref: InputRef | None = None
    output_model: str | None = None
    output_correct: str | None = None
    source: Source | None = None
    weight: float | None = Field(default=None, ge=0)
    model_version: str | None = None
    policy_version: str | None = None


class CorrectionResult(BaseModel):
    correction: Correction
    decision: RouterDecision
    memory_context: list[MemoryItem]


class ReplayIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fixture_ids: list[str] | None = None
    s1_impl: Literal["stub", "real"] = "stub"
    s2_impl: Literal["stub", "real"] = "stub"


class Health(BaseModel):
    status: str
    impl: dict[str, str]
    data_freshness: dict[str, Any]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _require_case(case_id: str) -> StoredCase:
    stored = get(case_id)
    if stored is None:
        raise HTTPException(status_code=404, detail=f"unknown case {case_id}")
    return stored


def _refresh_memory(stored: StoredCase) -> None:
    try:
        stored.state.memory_context = retrieve(stored.state)
    except NotImplementedError:
        return


def execute(case: CaseState) -> RouterDecision:
    """Mubit gateway. Memory retrieval happens inside handle(), not before it."""
    try:
        return handle(case, use_stubs=True)
    except NotImplementedError as exc:
        owner = "Melanie" if "Melanie" in str(exc) else "Moly"
        raise not_ready(owner, exc) from exc
    except DecisionRequired as exc:
        raise not_ready("Moly", exc) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/health", response_model=Health)
def health() -> Health:
    freshness: dict[str, Any] = {}
    if DB_PATH.exists():
        with connect() as conn:
            for row in conn.execute(
                "SELECT source, fetched_at, row_count, status FROM source_status"
            ):
                freshness[row["source"]] = {
                    "fetched_at": row["fetched_at"],
                    "row_count": row["row_count"],
                    "status": row["status"],
                }
    return Health(status="ok", impl=impl_snapshot(), data_freshness=freshness)


@router.get("/fixtures")
def fixtures() -> dict:
    return {"fixtures": list_entries()}


@router.get("/fixtures/{fixture_id}")
def fixture_one(fixture_id: str) -> dict:
    try:
        return load_fixture(fixture_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown fixture {fixture_id}") from exc


@router.get("/fixtures/{fixture_id}/stream")
async def fixture_stream(fixture_id: str, pace: float = Query(default=1.0, ge=0, le=20)):
    try:
        payload = load_fixture(fixture_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"unknown fixture {fixture_id}") from exc

    async def events():
        previous = 0
        for turn in payload["transcript_stream"]:
            delta = turn["t_ms"] - previous
            previous = turn["t_ms"]
            if pace and delta > 0:
                await asyncio.sleep(delta / 1000 * pace)
            yield f"event: turn\ndata: {json.dumps(turn)}\n\n"
        yield "event: done\ndata: {}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


@router.post("/cases", response_model=CaseCreated)
def create_case(body: CreateCase) -> CaseCreated:
    if body.fixture_id:
        try:
            state = load_case(body.fixture_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown fixture {body.fixture_id}") from exc
        existing = get(state.case_id)
        if existing is None:
            existing = put(StoredCase(state=state, fixture_id=body.fixture_id))
        _refresh_memory(existing)
        return CaseCreated(case=existing.state, fixture_id=body.fixture_id)
    if not body.transcript:
        raise HTTPException(status_code=422, detail="provide fixture_id or transcript")
    case_id = "case-" + uuid.uuid4().hex[:8]
    state = CaseState(
        case_id=case_id,
        caller_id_hash=body.caller_id_hash or f"synthetic:{case_id}",
        transcript=body.transcript,
        fields=body.fields or ExtractedFields(),
        memory_context=[],
        policy_flags=[],
        resources={},
        received_at=_now(),
    )
    stored = put(StoredCase(state=state, fixture_id=None))
    return CaseCreated(case=stored.state, fixture_id=None)


@router.post("/cases/{case_id}/turns", response_model=TurnResult)
def add_turn(case_id: str, turn: TranscriptTurn) -> TurnResult:
    stored = _require_case(case_id)
    if turn.t_ms < stored.state.transcript[-1].t_ms if stored.state.transcript else False:
        raise HTTPException(status_code=422, detail="t_ms must not go backwards")
    stored.state.transcript.append(turn)
    decision = execute(stored.state)
    stored.decisions.append(decision)
    return TurnResult(case=stored.state, decision=decision)


@router.get("/cases/{case_id}", response_model=CaseDetail)
def read_case(case_id: str) -> CaseDetail:
    stored = _require_case(case_id)
    _refresh_memory(stored)
    latest = stored.decisions[-1] if stored.decisions else None
    return CaseDetail(
        case=stored.state,
        latest_decision=latest,
        decision_history=list(stored.decisions),
    )


@router.post("/triage", response_model=RouterDecision)
def triage(case: CaseState) -> RouterDecision:
    return execute(case)


def _correction_from_body(case_id: str, body: CorrectionIn) -> Correction:
    turn_ids = list(body.turn_ids)
    lang = body.lang
    policy_ids = list(body.policy_ids)
    memory_ref = body.memory_ref
    if body.input_ref is not None:
        if body.input_ref.case_id != case_id:
            raise HTTPException(status_code=422, detail="input_ref.case_id must match the case")
        turn_ids = list(body.input_ref.turn_ids)
        lang = body.input_ref.lang
        policy_ids = list(body.input_ref.policy_ids)
        memory_ref = body.input_ref.memory_ref
    correction = Correction(
        correction_id="corr-" + uuid.uuid4().hex[:10],
        case_id=case_id,
        corrected_by=body.corrected_by,
        field=body.field,
        old_value=body.old_value,
        new_value=body.new_value,
        reason=body.reason,
        created_at=_now(),
        task=body.task,
        group_id=body.group_id,
        turn_ids=turn_ids,
        lang=lang,
        policy_ids=policy_ids,
        memory_ref=memory_ref,
        output_model=body.output_model,
        output_correct=body.output_correct,
        source=body.source,
        weight=body.weight,
        model_version=body.model_version,
        policy_version=body.policy_version,
    )
    if correction_is_v1(correction):
        correction = correction.model_copy(update={"schema_version": 1})
    return correction


@router.post("/cases/{case_id}/corrections", response_model=CorrectionResult)
def correct(case_id: str, body: CorrectionIn) -> CorrectionResult:
    stored = _require_case(case_id)
    correction = _correction_from_body(case_id, body)
    event = None
    try:
        event = adapt_correction(correction)
    except AdaptError as exc:
        if correction_is_v1(correction):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        store_correction(correction)
    except NotImplementedError as exc:
        raise not_ready("Melanie", exc) from exc
    stored.corrections.append(correction)
    if event is not None:
        append_event(event)
    emit(
        TraceEvent(
            case_id=case_id,
            stage="memory_write",
            started_at=_now(),
            latency_ms=0,
            notes=f"mock correction {correction.correction_id}",
        )
    )
    decision = execute(stored.state)
    stored.decisions.append(decision)
    return CorrectionResult(
        correction=correction,
        decision=decision,
        memory_context=list(stored.state.memory_context),
    )


@router.get("/cases/{case_id}/trace", response_model=list[TraceEvent])
def case_trace(case_id: str) -> list[TraceEvent]:
    _require_case(case_id)
    return read_traces(case_id)


@router.get("/context")
def context(
    district: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> dict:
    if enrich_impl() == "off":
        return location_context(None, None, None) | {"enrich": "off"}
    return location_context(district, lat, lon)


@router.get("/resources")
def resources():
    return load_dispatch_resources()


def _geojson(path: Path) -> dict:
    if not path.exists():
        return {
            "type": "FeatureCollection",
            "features": [],
            "properties": {"note": f"{path.name} is not available yet"},
        }
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/map/flood")
def map_flood() -> dict:
    return _geojson(ROOT / "data" / "processed" / "flood.geojson")


@router.get("/map/facilities")
def map_facilities() -> dict:
    return _geojson(ROOT / "data" / "processed" / "facilities.geojson")


@router.post("/replay")
def replay_endpoint(body: ReplayIn) -> dict:
    if body.s1_impl == "real" or s1_impl() == "real":
        try:
            system1.decide(CaseState.model_validate(load_case(all_ids()[0]).model_dump()))
        except NotImplementedError as exc:
            raise not_ready("Moly", exc) from exc
    if body.s2_impl == "real" or s2_impl() == "real":
        try:
            system2.decide(CaseState.model_validate(load_case(all_ids()[0]).model_dump()))
        except NotImplementedError as exc:
            raise not_ready("Melanie", exc) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    ids = body.fixture_ids or all_ids()
    for fixture_id in ids:
        if fixture_id not in all_ids():
            raise HTTPException(status_code=404, detail=f"unknown fixture {fixture_id}")

    def s1_system(case: CaseState):
        return load_s1_stub(case.case_id)

    def s2_system(case: CaseState):
        from mocks.loader import has_s2_stub, load_s2_stub

        if not has_s2_stub(case.case_id):
            raise HTTPException(status_code=404, detail=f"no s2 stub for {case.case_id}")
        return load_s2_stub(case.case_id)

    s1_ids = [fid for fid in ids if load_fixture(fid)["expected"]["system"] == "system_1"]
    s2_ids = [fid for fid in ids if load_fixture(fid)["expected"]["system"] == "system_2"]
    return {
        "system_1": replay(s1_system, s1_ids),
        "system_2": replay(s2_system, s2_ids),
    }


@router.get("/aid/eligibility")
def aid_eligibility(case_id: str = Query(min_length=1)) -> dict:
    """Melanie's System 1 aid stub. Never approves a payment."""
    try:
        if case_id in all_ids():
            case = load_case(case_id)
        else:
            case = _require_case(case_id).state
        from system1.aid_eligibility import check

        check(case)
    except NotImplementedError as exc:
        raise not_ready("Melanie", exc) from exc
    raise not_ready("Melanie")


@router.post("/aid/exceptions")
def aid_exceptions(case: CaseState) -> dict:
    """Melanie's System 2 aid-exception stub. Never approves an exception."""
    try:
        from system2.aid_exceptions import propose

        propose(case)
    except NotImplementedError as exc:
        raise not_ready("Melanie", exc) from exc
    raise not_ready("Melanie")


@router.get("/rl/run")
def rl_run() -> dict:
    path = ROOT / "eval" / "out" / "rl" / "run.json"
    if not path.exists():
        raise HTTPException(
            status_code=404,
            detail="no RL run yet; run `make rl-loop` first",
        )
    return json.loads(path.read_text(encoding="utf-8"))


@router.get("/metrics")
def metrics() -> dict:
    events = read_traces()
    by_case: dict[str, set[str]] = {}
    latency: dict[str, list[int]] = {"system_1": [], "system_2": []}
    for event in events:
        by_case.setdefault(event.case_id, set()).add(event.stage)
        if event.stage in latency:
            latency[event.stage].append(event.latency_ms)
    handled_s2 = sum(1 for stages in by_case.values() if "system_2" in stages)
    handled_s1 = sum(
        1 for stages in by_case.values() if "system_1" in stages and "system_2" not in stages
    )
    total = handled_s1 + handled_s2
    correction_count = len(read_corrections())
    return {
        "cases_traced": len(by_case),
        "pct_handled_by_system_1": (handled_s1 / total) if total else 0.0,
        "pct_handled_by_system_2": (handled_s2 / total) if total else 0.0,
        "avg_latency_ms": {
            "system_1": _avg(latency["system_1"]),
            "system_2": _avg(latency["system_2"]),
        },
        "correction_count": correction_count,
        "enrich": enrich_impl(),
    }


def _avg(values: list[int]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)
