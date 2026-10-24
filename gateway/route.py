"""Mubit gateway. Owner: Moly.

One turn enriches the case, retrieves memory, records a policy pre-check, and
routes to System 1 or System 2 — never both. Mubit does not reason: the route
choice is the field precheck in gateway/chooser.py (the decided
`gateway.route_chooser`), and the RouterDecision comes from router/merge.py.

Extraction runs before enrichment when the case has no fields yet, or again on
a later turn once `keyword_extraction` is in policy_flags. Fixture cases carry
hand-filled fields, so they are never extracted.

use_stubs=True loads the stub for the chosen system. use_stubs=False, or
S1_IMPL=real / S2_IMPL=real on the chosen system, calls that system's decide()
and lets NotImplementedError through.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from config.settings import load_yaml
from contracts.models import (
    CaseState,
    ExtractedFields,
    Outcome,
    Priority,
    Route,
    RouterDecision,
    System,
    TraceEvent,
)
from enrich.context import location_context
from gateway.auth import status as auth_status
from gateway.chooser import choose
from gateway.graduation import apply as apply_graduations
from gateway.policy import precheck_notes
from memory.adapter import retrieve
from mocks.loader import has_s1_stub, has_s2_stub, load_s1_stub, load_s2_stub
import router.merge
from system1 import decide as system1
from system1.extract import extract
from system2 import decide as system2
from trace import emit


def handle(case: CaseState, use_stubs: bool = True) -> RouterDecision:
    started = _now()
    _extract(case)
    _enrich(case)
    case.memory_context = retrieve(case)
    graduations = apply_graduations(case)
    system, triggers = _choose(case)
    notes = [auth_status(), *precheck_notes()]
    emit(
        TraceEvent(
            case_id=case.case_id,
            stage="gateway",
            started_at=started,
            latency_ms=0,
            notes=(
                "mubit gateway: "
                + "; ".join(notes)
                + f"; memory via adapter; exclusive route {system.value}"
                + "; triggers: "
                + (", ".join(triggers) if triggers else "none")
                + (
                    "; graduated: " + ", ".join(g.label for g in graduations)
                    if graduations
                    else ""
                )
            ),
        )
    )
    outcome = _run(case, system, use_stubs=use_stubs)
    system_started = _now()
    emit(
        TraceEvent(
            case_id=case.case_id,
            stage=system.value,
            started_at=system_started,
            latency_ms=outcome.latency_ms or 0,
            model=None,
            outcome=outcome,
            notes="stub outcome" if use_stubs else "real interface",
        )
    )
    router_started = _now()
    decision = router.merge.merge(case, outcome, notes)
    emit(
        TraceEvent(
            case_id=case.case_id,
            stage="router",
            started_at=router_started,
            latency_ms=0,
            notes="router.merge ran on the single selected outcome",
        )
    )
    return decision


def choose_system(case: CaseState) -> System:
    """Pick System 1 or System 2. Never both.

    The chooser is the field precheck in gateway/chooser.py, read from
    config/escalation.yaml. Fixture ids no longer override it.
    """
    system, _triggers = _choose(case)
    return system


def _choose(case: CaseState) -> tuple[System, list[str]]:
    mode = load_yaml("routing.yaml").get("mode")
    if mode != "exclusive":
        raise RuntimeError(
            f"config/routing.yaml mode is {mode!r}. "
            "The gateway only implements exclusive routing "
            "(System 1 or System 2, not System 1 then System 2)."
        )
    return choose(case)


def _run(case: CaseState, system: System, use_stubs: bool) -> Outcome:
    real = (system is System.system_1 and _impl("S1_IMPL") == "real") or (
        system is System.system_2 and _impl("S2_IMPL") == "real"
    )
    if real or not use_stubs:
        if system is System.system_1:
            return system1.decide(case)
        return system2.decide(case)
    if system is System.system_1:
        if has_s1_stub(case.case_id):
            return load_s1_stub(case.case_id)
        return _fallback_outcome(case.case_id, System.system_1)
    if has_s2_stub(case.case_id):
        return load_s2_stub(case.case_id)
    return _fallback_outcome(case.case_id, System.system_2)


def _impl(name: str) -> str:
    return os.environ.get(name, "stub").strip().lower() or "stub"


def _extract(case: CaseState) -> None:
    """Keyword-extract fields so enrichment and the chooser can see them."""
    if not (
        case.fields == ExtractedFields() or "keyword_extraction" in case.policy_flags
    ):
        return
    fields, flags = extract(case.transcript)
    case.fields = fields
    for flag in ("keyword_extraction", *flags):
        _add(case.policy_flags, flag)


def _enrich(case: CaseState) -> None:
    from ingest.db import db_exists

    mode = os.environ.get("ENRICH_IMPL", "").strip().lower()
    if not mode:
        mode = "data" if db_exists() else "off"
    if mode == "off":
        return
    ctx = location_context(case.fields.location, None, None)
    case.resources = {**case.resources, "location_context": ctx}
    thresholds = load_yaml("escalation.yaml").get("enrichment_flags") or {}
    flags = list(case.policy_flags)
    if ctx.get("in_flood_extent_1d") or ctx.get("in_flood_extent_7d"):
        _add(flags, "in_active_flood_extent")
    if ctx.get("repeat_flood_area"):
        _add(flags, "repeat_flood_area")
    forecast = ctx.get("rainfall_forecast_24h_mm")
    limit = thresholds.get("heavy_rain_forecast_mm_24h")
    if forecast is not None and limit is not None and forecast >= float(limit):
        _add(flags, "heavy_rain_forecast")
    observed = ctx.get("rainfall_last_24h_mm")
    observed_limit = thresholds.get("heavy_rain_observed_mm_24h")
    if observed is not None and observed_limit is not None and observed >= float(observed_limit):
        _add(flags, "heavy_rain_observed")
    case.policy_flags = flags


def _add(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def _fallback_outcome(case_id: str, system: System = System.system_1) -> Outcome:
    return Outcome(
        system=system,
        outcome="escalate",
        priority=Priority.P2,
        needs=[],
        route=Route.supervisor_escalation,
        confidence=0.0,
        reason=(
            f"No stub outcome for {case_id}. "
            "Human decision logic is not implemented."
        ),
        reasoning=None,
        missing_evidence=["fixture_stub"],
        next_question=None,
        requires_human=True,
        escalate=system is System.system_1,
        latency_ms=0,
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)
