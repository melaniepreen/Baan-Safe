"""Stub correction loop. `make demo-correction-loop`.

correction captured -> stored in memory -> SFT/LoRA JSONL -> training job stub
-> new model version -> replay before vs after.

The case is synthetic. Golden fixtures are not rewritten. This run does not
promote a rule into System 1 — pattern graduation lives in eval/rl/. No Mubit
or LLM call is made.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from config.settings import UNSET, unset_decisions
from contracts.models import (
    Correction,
    ModelVersion,
    Need,
    Outcome,
    Priority,
    Route,
    System,
    TraceEvent,
    TrainingJob,
)
from contracts.training import adapt_correction
from eval.compare import compare_runs
from memory.adapter import retrieve, store_correction
from paths import ROOT
from trace import emit
from training.log import append_event

CASE_ID = "CORR-LOOP-1"
CORRECTED_ROUTE = "welfare_distribution"
CALLER_TEXT = (
    "Synthetic caller in Mueang Lampang District. "
    "Three people. Drinking water requested. Ground is dry. No danger signs."
)


def run(out_dir: Path | None = None) -> dict:
    out = out_dir or (ROOT / "eval" / "out")
    out.mkdir(parents=True, exist_ok=True)
    previous_corrections = os.environ.get("MOCK_CORRECTIONS_PATH")
    previous_trace = os.environ.get("TRACE_PATH")
    os.environ["MOCK_CORRECTIONS_PATH"] = str(out / "corrections.jsonl")
    os.environ["TRACE_PATH"] = str(out / "traces.jsonl")
    try:
        return _run(out)
    finally:
        _restore("MOCK_CORRECTIONS_PATH", previous_corrections)
        _restore("TRACE_PATH", previous_trace)


def _restore(name: str, previous: str | None) -> None:
    if previous is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = previous


def _run(out: Path) -> dict:
    started = datetime.now(timezone.utc)
    before = _outcome(
        route=Route.information_only,
        priority=Priority.P4,
        reason="Stub before the correction: the call was labelled information only.",
        latency_ms=20,
        version="stub-0",
    )
    correction = Correction(
        correction_id="corr-loop-stub",
        case_id=CASE_ID,
        corrected_by="operator",
        field="route",
        old_value="information_only",
        new_value=CORRECTED_ROUTE,
        reason="Synthetic water request with a district. The information-only label was wrong.",
        created_at=started,
        schema_version=1,
        task="s1_triage",
        group_id=CASE_ID,
        lang="en",
        policy_ids=["SPHERE-WASH-15L"],
        memory_ref="runtime:corr-loop-stub",
        output_model=None,
        output_correct="sphere_water_short",
        source="human",
        model_version="s1@stub-0",
    )
    # Route names stay on the memory row. The log stores the closed s1 label.
    event = adapt_correction(correction)
    store_correction(correction)
    logged = append_event(event)
    memory = retrieve(_bare_case())
    emit(
        TraceEvent(
            case_id=CASE_ID,
            stage="memory_write",
            started_at=started,
            latency_ms=0,
            notes=f"stub correction {correction.correction_id} stored via memory adapter",
        )
    )

    dataset = out / "sft.jsonl"
    row = {
        "messages": [
            {
                "role": "system",
                "content": (
                    "Label a synthetic flood-call route. "
                    "Reply with one route name. Do not invent a person."
                ),
            },
            {"role": "user", "content": CALLER_TEXT},
            {"role": "assistant", "content": CORRECTED_ROUTE},
        ]
    }
    dataset.write_text(json.dumps(row, ensure_ascii=False) + "\n", encoding="utf-8")

    job = TrainingJob(
        job_id="stub-job-1",
        status="stub",
        dataset_path=str(dataset),
        base_model="TODO_HUMAN",
        target_version_id="stub-1",
        notes="No weights were trained. The job records the JSONL path only.",
    )
    before_version = ModelVersion(
        version_id="stub-0",
        model_name="stub-extractor",
        role="system_1",
        notes="Registered before the correction. Not a chosen model.",
    )
    after_version = ModelVersion(
        version_id="stub-1",
        model_name="stub-extractor",
        role="system_1",
        parent_version_id="stub-0",
        training_job_id=job.job_id,
        notes="Registered from the stub training job. Not a chosen model.",
    )
    registry = {
        "versions": [
            before_version.model_dump(),
            after_version.model_dump(),
        ],
        "jobs": [job.model_dump()],
    }
    (out / "model_registry.json").write_text(
        json.dumps(registry, indent=2) + "\n",
        encoding="utf-8",
    )

    after = _outcome(
        route=Route.welfare_distribution,
        priority=Priority.P3,
        reason="Stub after the correction: the same call is labelled welfare distribution.",
        latency_ms=28,
        version="stub-1",
    )
    _emit_replay(before, "stub-0", tokens_in=80, tokens_out=12)
    _emit_replay(after, "stub-1", tokens_in=96, tokens_out=14)

    before_score = _score(before, "stub-0", 80, 12)
    after_score = _score(after, "stub-1", 96, 14)
    comparison = compare_runs(before_score, after_score)
    threshold = unset_decisions(["correction_loop.graduation_threshold"])
    comparison["graduation_threshold"] = UNSET if threshold else "set"
    comparison["promoted_to_system_1"] = False
    comparison["memory_items"] = len(memory)
    comparison["dataset"] = str(dataset)
    comparison["training_job"] = job.model_dump()
    comparison["training_event_id"] = logged.event.event_id
    comparison["training_event_written"] = logged.written
    (out / "comparison.json").write_text(
        json.dumps(comparison, indent=2) + "\n",
        encoding="utf-8",
    )
    _print(comparison, dataset)
    return comparison


def _bare_case():
    from contracts.models import CaseState, ExtractedFields

    return CaseState(
        case_id=CASE_ID,
        caller_id_hash="synthetic:corr-loop-1",
        transcript=[],
        fields=ExtractedFields(
            location="Mueang Lampang District, Lampang",
            people_count=3,
            needs=[Need.water],
        ),
        received_at=datetime.now(timezone.utc),
    )


def _outcome(
    route: Route,
    priority: Priority,
    reason: str,
    latency_ms: int,
    version: str,
) -> Outcome:
    del version
    return Outcome(
        system=System.system_1,
        outcome="fast_route",
        priority=priority,
        needs=[Need.water],
        route=route,
        confidence=0.5,
        reason=reason,
        reasoning=None,
        missing_evidence=[],
        next_question=None,
        requires_human=True,
        escalate=False,
        latency_ms=latency_ms,
    )


def _emit_replay(outcome: Outcome, version: str, tokens_in: int, tokens_out: int) -> None:
    emit(
        TraceEvent(
            case_id=CASE_ID,
            stage="system_1",
            started_at=datetime.now(timezone.utc),
            latency_ms=outcome.latency_ms or 0,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            model=None,
            model_version=version,
            outcome=outcome,
            notes=f"stub replay {version}",
        )
    )


def _score(outcome: Outcome, version: str, tokens_in: int, tokens_out: int) -> dict:
    return {
        "route_accuracy": 1.0 if outcome.route.value == CORRECTED_ROUTE else 0.0,
        "n": 1,
        "latency_ms": outcome.latency_ms,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "model_version": version,
    }


def _print(comparison: dict, dataset: Path) -> None:
    quality = comparison["quality"]
    latency = comparison["latency_ms"]
    print(f"correction captured corr-loop-stub on {CASE_ID}")
    print(f"memory stored via adapter; items now {comparison['memory_items']}")
    print(f"dataset {dataset} (1 SFT/LoRA messages row)")
    print(
        f"training event {comparison['training_event_id']} "
        f"written={comparison['training_event_written']}"
    )
    print("training job stub-job-1 status=stub (no weights trained)")
    print("model version stub-0 -> stub-1")
    print(
        "quality route_accuracy "
        f"{quality['before']} -> {quality['after']} "
        f"(n={quality['n']}, label={CORRECTED_ROUTE})"
    )
    print(f"latency_ms {latency['before']} -> {latency['after']}")
    print(f"cost_usd null ({comparison['cost_usd']['reason']})")
    print(
        f"graduation_threshold {comparison['graduation_threshold']} — "
        "this run does not promote a rule into System 1"
    )


def main() -> int:
    comparison = run()
    ok = (
        comparison["quality"]["before"] == 0.0
        and comparison["quality"]["after"] == 1.0
        and comparison["cost_usd"]["before"] is None
        and comparison["promoted_to_system_1"] is False
        and comparison["model_version"]["after"] == "stub-1"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
