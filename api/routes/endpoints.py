"""Every Phase 1 endpoint. Human logic is reached only through the impl switches."""

from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from api.caller_ip import resolve_caller_ip, stamp_caller_ip
from api.deps import enrich_impl, impl_snapshot, not_ready, s1_impl, s2_impl
from api.routes.training import display_path, rl_run_path
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
from ingest import store
from memory.adapter import memory_mode, retrieve, store_correction
from memory.adapter import status as memory_status
from training.log import append_event
from mocks.loader import (
    ResourceUnit,
    ResourcesSnapshot,
    load_dispatch_resources,
    load_s1_stub,
    read_corrections,
)
from paths import ROOT
from router import ledger
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


class SessionStamp(BaseModel):
    caller_ip: str
    simulated: bool
    note: str


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
    memory: dict[str, Any]


class HoldView(BaseModel):
    """One ledger hold. API-only — does not change Dispatch / RouterDecision."""

    model_config = ConfigDict(extra="forbid")

    resource_id: str
    need: str
    status: Literal["provisional", "confirmed", "released"]


class DispatchActionResult(BaseModel):
    """Case-level confirm or cancel of current ledger holds (HANDOVER #7)."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    action: Literal["confirmed", "cancelled"]
    holds: list[HoldView]


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
    """Mubit gateway. Memory retrieval and the end-of-turn record write happen
    inside handle(). Stored corrections ride along on that record."""
    stored = get(case.case_id)
    corrections = list(stored.corrections) if stored is not None else []
    try:
        return handle(case, use_stubs=True, corrections=corrections)
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
    if store.available():
        for row in store.rows("source_status"):
            freshness[row["source"]] = {
                "fetched_at": row["fetched_at"],
                "row_count": row["row_count"],
                "status": row["status"],
            }
    return Health(
        status="ok",
        impl=impl_snapshot(),
        data_freshness=freshness,
        memory=memory_status(),
    )


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


@router.post("/session", response_model=SessionStamp)
def open_session(request: Request) -> SessionStamp:
    ip, simulated = resolve_caller_ip(request)
    if simulated:
        note = (
            f"Caller IP recorded · {ip} · DEMO. "
            "The request did not carry a public address, so this row uses a fixed Thai access-network stub."
        )
    else:
        note = f"Caller IP recorded · {ip}"
    return SessionStamp(caller_ip=ip, simulated=simulated, note=note)


@router.post("/cases", response_model=CaseCreated)
def create_case(body: CreateCase, request: Request) -> CaseCreated:
    if body.fixture_id:
        try:
            state = load_case(body.fixture_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=f"unknown fixture {body.fixture_id}") from exc
        existing = get(state.case_id)
        if existing is None:
            existing = put(StoredCase(state=state, fixture_id=body.fixture_id))
        stamp_caller_ip(existing.state, request)
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
    stamp_caller_ip(state, request)
    stored = put(StoredCase(state=state, fixture_id=None))
    return CaseCreated(case=stored.state, fixture_id=None)


@router.post("/cases/{case_id}/turns", response_model=TurnResult)
def add_turn(case_id: str, turn: TranscriptTurn, request: Request) -> TurnResult:
    stored = _require_case(case_id)
    stamp_caller_ip(stored.state, request)
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
        write_note = store_correction(correction)
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
            notes=write_note,
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


@router.post(
    "/cases/{case_id}/dispatches/confirm",
    response_model=DispatchActionResult,
)
def confirm_dispatches(case_id: str) -> DispatchActionResult:
    """Confirm this case's current ledger holds. Does not mutate RouterDecision."""
    _require_case(case_id)
    try:
        marked = ledger.confirm_case(case_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"no provisional holds for case {case_id}",
        ) from exc
    return DispatchActionResult(
        case_id=case_id,
        action="confirmed",
        holds=[
            HoldView(resource_id=rid, need=need, status="confirmed")
            for rid, need in sorted(marked)
        ],
    )


@router.post(
    "/cases/{case_id}/dispatches/cancel",
    response_model=DispatchActionResult,
)
def cancel_dispatches(case_id: str) -> DispatchActionResult:
    """Cancel and release this case's ledger holds. Does not mutate RouterDecision."""
    _require_case(case_id)
    try:
        released = ledger.cancel_case(case_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"no holds to cancel for case {case_id}",
        ) from exc
    return DispatchActionResult(
        case_id=case_id,
        action="cancelled",
        holds=[
            HoldView(resource_id=rid, need=need, status="released")
            for rid, need in sorted(released)
        ],
    )


@router.get("/context")
def context(
    district: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
) -> dict:
    if enrich_impl() == "off":
        return location_context(None, None, None) | {"enrich": "off"}
    return location_context(district, lat, lon)


def _with_ledger_availability(snapshot: ResourcesSnapshot) -> ResourcesSnapshot:
    """Subtract in-process holds so the UI does not always show full stock."""

    def adjust(unit: ResourceUnit) -> ResourceUnit:
        if unit.available is None:
            return unit
        free = max(0, unit.available - ledger.reserved_total(unit.id))
        return unit.model_copy(update={"available": free})

    return ResourcesSnapshot(
        boats=[adjust(u) for u in snapshot.boats],
        ambulances=[adjust(u) for u in snapshot.ambulances],
        shelters=[adjust(u) for u in snapshot.shelters],
        welfare_points=[adjust(u) for u in snapshot.welfare_points],
    )


@router.get("/resources")
def resources():
    return _with_ledger_availability(load_dispatch_resources())


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


# Per-episode flags in run.json (eval/rl). `incorrect` is `not correct`.
EPISODE_FILTERS = (
    "critical_under",
    "under_triage",
    "missed_human",
    "s2_fell_back",
    "incorrect",
    "cascaded",
)


def _episode_matches(episode: dict, name: str) -> bool:
    if name == "incorrect":
        return not bool(episode.get("correct"))
    return bool(episode.get(name))


@router.get("/rl/run/episodes")
def rl_run_episodes(
    filter: str | None = Query(default=None),
    epoch: int | None = Query(default=None),
) -> dict:
    """Per-episode drill-down of the last RL run (HANDOVER E3).

    Reads `rl_run_path()` (RL_RUN_PATH, else eval/out/rl/run.json). `filter`
    keeps episodes with that flag set; `epoch` keeps one epoch. Rows come
    back sorted by (epoch, seq). `run_path` is the display form, never an
    absolute path.
    """
    if filter is not None and filter not in EPISODE_FILTERS:
        raise HTTPException(
            status_code=400,
            detail=f"unknown filter {filter!r}; allowed: {', '.join(EPISODE_FILTERS)}",
        )
    path = rl_run_path()
    if not path.is_file():
        raise HTTPException(
            status_code=404,
            detail="no RL run yet; run `make rl-loop` first",
        )
    try:
        run = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(
            status_code=404,
            detail="no RL run yet; run `make rl-loop` first",
        ) from exc
    raw = run.get("episodes") if isinstance(run, dict) else None
    episodes = [row for row in (raw or []) if isinstance(row, dict)]
    kept = episodes
    if epoch is not None:
        kept = [row for row in kept if row.get("epoch") == epoch]
    if filter is not None:
        kept = [row for row in kept if _episode_matches(row, filter)]
    kept = sorted(kept, key=lambda row: (_int_or_zero(row.get("epoch")), _int_or_zero(row.get("seq"))))
    return {
        "run_path": display_path(path),
        "filter": filter,
        "epoch": epoch,
        "total": len(episodes),
        "count": len(kept),
        "episodes": kept,
    }


def _int_or_zero(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


@router.get("/metrics")
def metrics() -> dict:
    events = read_traces()
    by_case: dict[str, set[str]] = {}
    latency: dict[str, list[int]] = {
        "system_1": [],
        "system_2": [],
        "mubit_chat": [],
    }
    mubit_ok = 0
    mubit_cache = 0
    mubit_error = 0
    mubit_models: dict[str, int] = {}
    memory_retrieve = 0
    memory_hit = 0
    memory_items = 0
    memory_write_ok = 0
    memory_write_error = 0
    memory_write_latency: list[int] = []
    duplicate_merges = 0
    for event in events:
        by_case.setdefault(event.case_id, set()).add(event.stage)
        if event.stage in latency:
            latency[event.stage].append(event.latency_ms)
        if event.stage == "mubit_chat":
            note = event.notes or ""
            if "status=ok" in note:
                mubit_ok += 1
            elif "status=cache_hit" in note:
                mubit_cache += 1
            else:
                mubit_error += 1
            if event.model:
                mubit_models[event.model] = mubit_models.get(event.model, 0) + 1
        elif event.stage == "memory":
            # Note shape: "memory via adapter mode=<mode>; items=<n>".
            memory_retrieve += 1
            count = _note_int(event.notes, "items")
            memory_items += count
            if count >= 1:
                memory_hit += 1
        elif event.stage == "memory_write":
            memory_write_latency.append(event.latency_ms)
            if "status=error" in (event.notes or ""):
                memory_write_error += 1
            else:
                memory_write_ok += 1
        elif (
            event.stage == "system_1"
            and event.outcome is not None
            and event.outcome.route.value == "duplicate_merge"
        ):
            duplicate_merges += 1
    handled_s2 = sum(1 for stages in by_case.values() if "system_2" in stages)
    handled_s1 = sum(
        1 for stages in by_case.values() if "system_1" in stages and "system_2" not in stages
    )
    total = handled_s1 + handled_s2
    correction_count = len(read_corrections())
    mubit_count = len(latency["mubit_chat"])
    return {
        "cases_traced": len(by_case),
        "pct_handled_by_system_1": (handled_s1 / total) if total else 0.0,
        "pct_handled_by_system_2": (handled_s2 / total) if total else 0.0,
        "avg_latency_ms": {
            "system_1": _avg(latency["system_1"]),
            "system_2": _avg(latency["system_2"]),
            "mubit_chat": _avg(latency["mubit_chat"]),
        },
        "mubit_chat": {
            "call_count": mubit_count,
            "ok_count": mubit_ok,
            "cache_hit_count": mubit_cache,
            "error_count": mubit_error,
            "avg_latency_ms": _avg(latency["mubit_chat"]),
            "models": mubit_models,
            "via": "api.mubit.ai",
        },
        "memory": {
            "mode": memory_mode(),
            "retrieve_count": memory_retrieve,
            "hit_count": memory_hit,
            "item_total": memory_items,
            "hit_rate": (memory_hit / memory_retrieve) if memory_retrieve else 0.0,
            "write_count": memory_write_ok,
            "write_error_count": memory_write_error,
            "avg_write_latency_ms": _avg(memory_write_latency),
            "duplicate_merge_count": duplicate_merges,
        },
        "correction_count": correction_count,
        "enrich": enrich_impl(),
    }


def _avg(values: list[int]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _note_int(note: str | None, key: str) -> int:
    """Read `key=<int>` from a `; `-separated trace note. Missing is 0."""
    for part in (note or "").split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name.strip() == key:
            try:
                return int(value.strip())
            except ValueError:
                return 0
    return 0
