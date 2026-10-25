"""Mubit gateway. Owner: Moly.

One turn enriches the case, retrieves memory, records a policy pre-check, and
routes by the field precheck in gateway/chooser.py (the decided
`gateway.route_chooser`). routing.yaml `mode: cascade` means a System 1
escalate hands the same turn to System 2; `mode: exclusive` keeps one system
per turn. Mubit does not reason: the RouterDecision comes from
router/merge.py.

Extraction runs before enrichment when the case has no fields yet, or again on
a later turn once `keyword_extraction` is in policy_flags. Fixture cases carry
hand-filled fields, so they are never extracted.

use_stubs=True loads the stub for the chosen system. use_stubs=False, or
S1_IMPL=real / S2_IMPL=real on the chosen system, calls that system's decide().
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
from gateway.overlay import Overlay, load_from_env, narrow_signature
from gateway.policy import precheck_notes
from memory.adapter import memory_mode, retrieve
from mocks.loader import (
    has_s1_stub,
    has_s2_stub,
    load_dispatch_resources,
    load_s1_stub,
    load_s2_stub,
)
import router.merge
from system1 import decide as system1
from system1.extract import extract
from system2 import decide as system2
from trace import emit

_MODES = ("exclusive", "cascade")


def handle(
    case: CaseState,
    use_stubs: bool = True,
    overlay: Overlay | None = None,
) -> RouterDecision:
    if overlay is None:
        overlay = load_from_env()
    started = _now()
    _extract(case)
    enrich_started = _now()
    enrich_note = _enrich(case)
    emit(
        TraceEvent(
            case_id=case.case_id,
            stage="enrich",
            started_at=enrich_started,
            latency_ms=0,
            notes=enrich_note,
        )
    )
    memory_started = _now()
    case.memory_context = retrieve(case)
    memory_ms = max(0, int((_now() - memory_started).total_seconds() * 1000))
    emit(
        TraceEvent(
            case_id=case.case_id,
            stage="memory",
            started_at=memory_started,
            latency_ms=memory_ms,
            notes=(
                f"memory via adapter mode={memory_mode()}; "
                f"items={len(case.memory_context)}"
            ),
        )
    )
    graduations = apply_graduations(case)
    mode = _mode()
    system, triggers = choose(case, overlay)
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
                + f"; memory via adapter; {mode} route {system.value}"
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
    outcome = _run(case, system, use_stubs=use_stubs, overlay=overlay)
    _trace_system(case.case_id, outcome, use_stubs)
    prior: list[Outcome] = []
    if mode == "cascade" and _should_cascade(system, outcome):
        prior.append(outcome)
        s2 = _run(
            case,
            System.system_2,
            use_stubs=use_stubs,
            overlay=overlay,
            handoff=outcome,
            recommendation=(
                overlay.recommendations.get(narrow_signature(case))
                if overlay is not None
                else None
            ),
        )
        _trace_system(case.case_id, s2, use_stubs)
        notes.append(
            f"cascade: system_1 handed off to system_2 ({outcome.reason})"
        )
        outcome = s2
    router_started = _now()
    decision = router.merge.merge(
        case, outcome, notes, resources=load_dispatch_resources(), prior=prior
    )
    emit(
        TraceEvent(
            case_id=case.case_id,
            stage="router",
            started_at=router_started,
            latency_ms=0,
            notes="router.merge ran on the selected outcome(s)",
        )
    )
    return decision


def choose_system(case: CaseState, overlay: Overlay | None = None) -> System:
    """Pick the entry-point system via the field precheck.

    Cascade mode may still continue to System 2 inside the same turn.
    """
    system, _triggers = choose(case, overlay)
    return system


def _mode() -> str:
    mode = load_yaml("routing.yaml").get("mode")
    if mode not in _MODES:
        raise RuntimeError(
            f"config/routing.yaml mode is {mode!r}. "
            f"Implemented modes: {', '.join(_MODES)}."
        )
    return mode


def _should_cascade(system: System, outcome: Outcome) -> bool:
    """A System 1 escalate continues to System 2. The no-stub fallback is
    'no S1 result', not low confidence, and never cascades."""
    return (
        system is System.system_1
        and outcome.escalate
        and outcome.missing_evidence != ["fixture_stub"]
    )


def _run(
    case: CaseState,
    system: System,
    use_stubs: bool,
    overlay: Overlay | None = None,
    handoff: Outcome | None = None,
    recommendation: dict | None = None,
) -> Outcome:
    real = (system is System.system_1 and _impl("S1_IMPL") == "real") or (
        system is System.system_2 and _impl("S2_IMPL") == "real"
    )
    if real or not use_stubs:
        if system is System.system_1:
            return system1.decide(case, overlay=overlay)
        return system2.decide(case, handoff=handoff, recommendation=recommendation)
    if system is System.system_1:
        if has_s1_stub(case.case_id):
            return load_s1_stub(case.case_id)
        return _fallback_outcome(case.case_id, System.system_1)
    if has_s2_stub(case.case_id):
        return load_s2_stub(case.case_id)
    return _fallback_outcome(case.case_id, System.system_2)


def _impl(name: str) -> str:
    return os.environ.get(name, "stub").strip().lower() or "stub"


def _trace_system(case_id: str, outcome: Outcome, use_stubs: bool) -> None:
    real = (outcome.system is System.system_1 and _impl("S1_IMPL") == "real") or (
        outcome.system is System.system_2 and _impl("S2_IMPL") == "real"
    )
    if real or not use_stubs:
        path = "real"
    else:
        path = "stub"
    note = f"{path} interface"
    if outcome.system is System.system_2 and path == "real":
        note = "real interface; mubit_chat hop traced in llm.complete"
    emit(
        TraceEvent(
            case_id=case_id,
            stage=outcome.system.value,
            started_at=_now(),
            latency_ms=outcome.latency_ms or 0,
            model=None,
            outcome=outcome,
            notes=note,
        )
    )


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


def _enrich(case: CaseState) -> str:
    from ingest import store

    mode = os.environ.get("ENRICH_IMPL", "").strip().lower()
    if not mode:
        mode = "data" if store.available() else "off"
    if mode == "off":
        return "enrich=off"
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
    # Data flags only. final_priority stays the outcome's priority.
    if ctx.get("near_flood_extent"):
        _add(flags, "near_flood_extent")
    case.policy_flags = flags
    return f"enrich={mode}"


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
