"""RL loop runner. `python -m eval.rl --s2 live|replay|fake`.

Off the live path. Episodes per epoch: every theme variant, fixtures
F01-F18, C01-a/b, G01-G04 (truth = expected), and the sim CATALOG callers
turn by turn like sim/env.py but with use_stubs=False, scoring only the
final turn. A seeded shuffle orders episodes inside each epoch.

Live S2 calls go only through `llm.complete` (Mubit). Cache hits emit the
same TraceEvent stage `mubit_chat` with `status=cache_hit`. Replay never
opens a socket; a miss raises and scores as a System 2 fallback.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from config.settings import require_decision, unset_decisions
from contracts.models import (
    CaseState,
    ExtractedFields,
    RouterDecision,
    TranscriptTurn,
)
from contracts.training import InputRef, S1Label, S2Action, TrainingEvent, current_policy_version
from eval.rl.learner import EpisodeContext, Learner
from eval.rl.reward import (
    gold_outcome,
    s1_label,
    score,
    truth_for_sim,
    truth_from_expected,
)
from eval.rl.themes import THEMES, Truth, lookup_by_text, variant_case
from fixtures.load import load_case, load_fixture
from gateway.overlay import Overlay, save as save_overlay
import router.ledger
from router.merge import _next_action
from sim.callers import CATALOG, N_TURNS, speak
from sim.env import OPERATOR_LINES, RECEIVED_AT
from system2 import orchestrator
from training.export import export_datasets
from training.log import append_event

OUT_DIR = Path(__file__).resolve().parents[1] / "out" / "rl"
RUN_SCHEMA = "baansafe.rl_run.v1"
CACHE_NAME = "s2_cache.jsonl"


@dataclass
class EpisodeSpec:
    kind: str  # theme | fixture | sim
    key: str
    theme: Any = None
    variant: Any = None
    fixture_id: str | None = None
    spec: Any = None


def episodes() -> list[EpisodeSpec]:
    items: list[EpisodeSpec] = []
    for theme in THEMES:
        for variant in theme.variants:
            items.append(
                EpisodeSpec("theme", variant.case_id, theme=theme, variant=variant)
            )
    for fixture_id in [
        *[f"F{i:02d}" for i in range(1, 19)],
        "C01-a",
        "C01-b",
        *[f"G{i:02d}" for i in range(1, 5)],
    ]:
        items.append(EpisodeSpec("fixture", fixture_id, fixture_id=fixture_id))
    for spec in CATALOG:
        items.append(EpisodeSpec("sim", spec.combo_id, spec=spec))
    return items


def run(
    s2: str = "live",
    epochs: int = 3,
    seed: int = 17,
    out_dir: Path | None = None,
) -> dict:
    out = Path(out_dir or OUT_DIR)
    out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("TRACE_PATH", str(out / "traces.jsonl"))
    events_path = out / "events.jsonl"
    try:
        threshold = int(require_decision("correction_loop.graduation_threshold"))
    except Exception:  # noqa: BLE001 — the default matches the decided value
        threshold = 2
    learner = Learner(threshold=threshold, rng=random.Random(seed))
    completer = _completer_for(s2, out)
    pool = episodes()
    epoch_rows: list[dict] = []
    episode_rows: list[dict] = []
    with orchestrator.use_completer(completer):
        for epoch in range(1, epochs + 1):
            order = list(pool)
            random.Random(f"{seed}:{epoch}").shuffle(order)
            rows = []
            for seq, meta in enumerate(order):
                router.ledger.reset()
                rows.append(
                    _episode(meta, learner, epoch, seq, events_path)
                )
            episode_rows.extend(rows)
            epoch_rows.append(_epoch_summary(epoch, rows))
    save_overlay(learner.overlay, out / "overlay.json")
    training = _export(events_path, out)
    model = require_decision("system2.orchestrator_model")
    mubit = _mubit_trace_summary(s2, model)
    payload = {
        "schema": RUN_SCHEMA,
        "s2": s2,
        "model": model,
        "mubit": mubit,
        "seed": seed,
        "epochs": epoch_rows,
        "episodes": episode_rows,
        "events": learner.events,
        "bandit_log_tail": learner.bandit_log[-50:],
        "final_overlay": learner.overlay.to_dict(),
        "training": training,
        "notes": [
            "Live S2 calls go only through Mubit (llm.complete); no OpenRouter client.",
            "Replay cache misses score as System 2 fallbacks; they do not invent a host.",
            "P1 and complex patterns never graduate; they become recommendations.",
            "The shadow bandit never routes.",
            _finetune_note(),
        ],
    }
    (out / "run.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    (out / "rl.md").write_text(_markdown(payload), encoding="utf-8")
    return payload


def _episode(
    meta: EpisodeSpec,
    learner: Learner,
    epoch: int,
    seq: int,
    events_path: Path,
) -> dict:
    from gateway.route import handle

    if meta.kind == "theme":
        case = variant_case(meta.theme, meta.variant)
        truth = meta.theme.truth
        decision = handle(case, use_stubs=False, overlay=learner.overlay)
    elif meta.kind == "fixture":
        case = load_case(meta.fixture_id)
        truth = truth_from_expected(load_fixture(meta.fixture_id)["expected"])
        decision = handle(case, use_stubs=False, overlay=learner.overlay)
    else:
        case, decision, truth = _sim_episode(meta.spec, learner.overlay)
    ran = {outcome.system for outcome in decision.source_outcomes}
    s2 = next(
        (o for o in decision.source_outcomes if o.system.value == "system_2"), None
    )
    s2_fell_back = s2 is not None and "system2_unavailable" in s2.missing_evidence
    result = score(decision, truth, ran, s2_fell_back)
    learner.learn(
        EpisodeContext(case=case, decision=decision, truth=truth, score=result),
        epoch,
        seq,
    )
    _log_training(case, decision, truth, events_path)
    return {
        "epoch": epoch,
        "seq": seq,
        "id": meta.key,
        "kind": meta.kind,
        "systems": sorted(system.value for system in ran),
        "cascaded": len(decision.source_outcomes) > 1,
        "s2_fell_back": s2_fell_back,
        "priority": decision.final_priority.value,
        "route": decision.final_route.value,
        "truth_priority": truth.priority,
        "reward": round(result.reward, 3),
        "correct": result.correct,
        "under_triage": result.under_triage,
        "critical_under": result.critical_under,
        "missed_human": result.missed_human,
    }


def _sim_episode(spec, overlay: Overlay):
    from gateway.route import handle

    transcript: list[TranscriptTurn] = []
    case: CaseState | None = None
    decision: RouterDecision | None = None
    for index in range(N_TURNS):
        spoken = speak(spec, index, backend="scripted")
        transcript.append(
            TranscriptTurn(t_ms=index * 2000, speaker="caller", text=spoken.public_text)
        )
        case = CaseState(
            case_id=f"SIM-{spec.combo_id}",
            caller_id_hash=spec.persona.caller_id,
            transcript=list(transcript),
            fields=ExtractedFields(),
            received_at=RECEIVED_AT,
        )
        decision = handle(case, use_stubs=False, overlay=overlay)
        transcript.append(
            TranscriptTurn(
                t_ms=index * 2000 + 1000,
                speaker="operator",
                text=OPERATOR_LINES[index],
            )
        )
    return case, decision, truth_for_sim(spec)


def _log_training(
    case: CaseState,
    decision: RouterDecision,
    truth: Truth,
    events_path: Path,
) -> None:
    try:
        policy_version = current_policy_version()
    except Exception:  # noqa: BLE001 — a missing corpus must not stop the loop
        policy_version = "unversioned"
    s1 = next(
        (o for o in decision.source_outcomes if o.system.value == "system_1"), None
    )
    s2 = next(
        (o for o in decision.source_outcomes if o.system.value == "system_2"), None
    )
    ref = InputRef(case_id=case.case_id, lang="en")
    if s1 is not None and s1.needs:
        correct = s1_label(truth.needs, truth.priority)
        if correct:
            model_label = s1_label(s1.needs, s1.priority)
            append_event(
                TrainingEvent(
                    task="s1_triage",
                    group_id=case.case_id,
                    input_ref=ref,
                    output_model=S1Label(model_label) if model_label else None,
                    output_correct=S1Label(correct),
                    reason="RL loop scored System 1 triage.",
                    source="sim",
                    model_version="rl-loop@s1",
                    policy_version=policy_version,
                ),
                path=events_path,
            )
    if s2 is not None:
        gold = gold_outcome(truth)
        append_event(
            TrainingEvent(
                task="s2_action",
                group_id=case.case_id,
                input_ref=ref,
                output_model=S2Action(decision.next_action.value),
                output_correct=S2Action(_next_action(case, gold).value),
                reason="RL loop scored System 2 action.",
                source="sim",
                model_version="rl-loop@s2",
                policy_version=policy_version,
            ),
            path=events_path,
        )


def _export(events_path: Path, out: Path) -> dict:
    try:
        manifests = export_datasets(
            events_path, out / "training", allow_missing=True
        )
    except Exception as exc:  # noqa: BLE001 — report, do not crash the loop
        return {"status": "error", "error": str(exc)}
    return {
        "status": "exported",
        "counts": {name: body["event_count"] for name, body in manifests.items()},
        "finetune": _finetune_status(),
    }


def _epoch_summary(epoch: int, rows: list[dict]) -> dict:
    count = len(rows) or 1
    return {
        "epoch": epoch,
        "episodes": len(rows),
        "mean_reward": round(sum(r["reward"] for r in rows) / count, 3),
        "correct": sum(1 for r in rows if r["correct"]),
        "under_triage": sum(1 for r in rows if r["under_triage"]),
        "critical_under": sum(1 for r in rows if r["critical_under"]),
        "missed_human": sum(1 for r in rows if r["missed_human"]),
        "share_s1_only": round(
            sum(1 for r in rows if r["systems"] == ["system_1"]) / count, 3
        ),
        "share_cascade": round(sum(1 for r in rows if r["cascaded"]) / count, 3),
        "share_s2_only": round(
            sum(1 for r in rows if r["systems"] == ["system_2"]) / count, 3
        ),
        "s2_fallbacks": sum(1 for r in rows if r["s2_fell_back"]),
    }


def _completer_for(mode: str, out: Path) -> Callable:
    if mode == "fake":
        return _fake_completer()
    cache_path = out / CACHE_NAME
    if mode == "replay":
        cache = _read_cache(cache_path)

        def replay(messages, model=None, **kwargs):
            key = _cache_key(model, messages)
            case_id = _case_id_from(kwargs, messages)
            if key not in cache:
                # Miss → ValueError → orchestrator system2_unavailable fallback.
                # Do not invent a non-Mubit hop or open a socket.
                raise ValueError("s2 cache miss")
            _emit_rl_cache_hit(case_id=case_id, model=model)
            return cache[key]

        return replay
    if mode != "live":
        raise ValueError(f"unknown s2 mode {mode!r}")
    cache = _read_cache(cache_path)
    from llm.client import complete

    last_call = {"at": 0.0}
    live_calls = {"count": 0}

    def live(messages, model=None, **kwargs):
        key = _cache_key(model, messages)
        case_id = _case_id_from(kwargs, messages)
        if key in cache:
            _emit_rl_cache_hit(case_id=case_id, model=model)
            return cache[key]
        # Free-tier pacing: at least 4 s between real calls, then 5/15/30 s
        # 429 backoff. A 429 answer is never written to the cache.
        wait = 4.0 - (time.monotonic() - last_call["at"])
        if wait > 0:
            time.sleep(wait)
        delay = 0.0
        last: Exception | None = None
        call_kwargs = {**kwargs, "case_id": case_id}
        for attempt in range(3):
            if delay:
                time.sleep(delay)
            last_call["at"] = time.monotonic()
            live_calls["count"] += 1
            try:
                # Only Mubit: complete() emits mubit_chat (status=ok|http_*).
                reply = complete(messages, model=model, **call_kwargs)
            except Exception as exc:  # noqa: BLE001 — retry only rate limits
                if "429" not in str(exc):
                    raise
                last = exc
                delay = (5.0, 15.0, 30.0)[attempt]
                continue
            cache[key] = reply
            with cache_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps({"key": key, "reply": reply}) + "\n")
            return reply
        # The orchestrator turns an HTTP error into the safe fallback outcome.
        raise last

    live.calls = live_calls
    return live


def _case_id_from(kwargs: dict, messages) -> str:
    raw = kwargs.get("case_id")
    if raw:
        return str(raw)
    try:
        payload = json.loads(messages[1]["content"])
        case_id = payload.get("case_id")
        if case_id:
            return str(case_id)
    except Exception:  # noqa: BLE001 — missing payload is fine
        pass
    return "rl"


def _emit_rl_cache_hit(*, case_id: str, model: str | None) -> None:
    """Trace a cache hit without opening a Mubit socket. Never logs a key."""
    from llm.client import emit_mubit_chat_trace

    emit_mubit_chat_trace(
        case_id=case_id or "rl",
        model=model,
        latency_ms=0,
        status="cache_hit",
        host="rl_s2_cache",
    )


def _mubit_trace_summary(s2: str, model: str) -> dict:
    """Summarize mubit_chat rows written during this run for run.json / UI."""
    from trace import read_traces

    events = [e for e in read_traces() if e.stage == "mubit_chat"]
    live_ok = 0
    cache_hits = 0
    errors = 0
    latencies: list[int] = []
    for event in events:
        notes = event.notes or ""
        latencies.append(event.latency_ms)
        if "status=cache_hit" in notes:
            cache_hits += 1
        elif "status=ok" in notes:
            live_ok += 1
        else:
            errors += 1
    if s2 == "live":
        via = "api.mubit.ai"
    elif s2 == "replay":
        via = "rl_s2_cache"
    else:
        via = "fake"
    avg = round(sum(latencies) / len(latencies), 1) if latencies else None
    return {
        "via": via,
        "model": model,
        "mubit_chat_count": len(events),
        "live_ok": live_ok,
        "cache_hits": cache_hits,
        "errors": errors,
        "avg_latency_ms": avg,
    }


def _finetune_status() -> str:
    """Reflect config/decisions.yaml instead of a hardcoded block message."""
    missing = unset_decisions(["modal.finetune_base_model", "modal.finetune_gpu"])
    if missing:
        return "blocked on " + ", ".join(missing)
    return "ready: make modal-finetune (datasets under eval/out/rl/training)"


def _finetune_note() -> str:
    status = _finetune_status()
    if status.startswith("blocked"):
        return f"Fine-tune is {status}."
    return "Fine-tune decisions are set; make modal-finetune consumes the exported datasets."


def _cache_key(model: str | None, messages) -> str:
    raw = json.dumps({"model": model, "messages": messages}, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _read_cache(path: Path) -> dict:
    cache: dict = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                cache[row["key"]] = row["reply"]
    return cache


def _fake_completer() -> Callable:
    truths = lookup_by_text()

    def fake(messages, model=None, **_kwargs):
        payload = json.loads(messages[1]["content"])
        text = " ".join(
            turn["text"].lower()
            for turn in payload["transcript"]
            if turn["speaker"] == "caller"
        )
        normalized = " ".join(text.split())
        truth = truths.get(normalized)
        if truth is None and payload.get("case_id"):
            try:
                expected = load_fixture(payload["case_id"])["expected"]
                truth = truth_from_expected(expected)
            except Exception:  # noqa: BLE001 — a non-fixture id is fine
                truth = None
        if truth is None:
            data = {
                "priority": "P2",
                "route": "supervisor_escalation",
                "needs": [],
                "requires_human": True,
                "missing_evidence": [],
                "next_question": None,
                "confidence": 0.4,
                "rationale": "Cautious generic handoff from the fake System 2.",
                "plan": [],
            }
        else:
            data = {
                "priority": truth.priority,
                "route": truth.routes[0],
                "needs": list(truth.needs),
                "requires_human": truth.requires_human,
                "missing_evidence": [],
                "next_question": None,
                "confidence": 0.9,
                "rationale": "Fake System 2 replays the authored truth.",
                "plan": [],
            }
        return {
            "choices": [{"message": {"content": json.dumps(data)}}]
        }

    return fake


def _markdown(payload: dict) -> str:
    lines = ["# RL loop run", ""]
    mubit = payload.get("mubit") or {}
    lines.append(
        f"s2={payload['s2']} model={payload.get('model')} "
        f"via={mubit.get('via')} seed={payload['seed']} "
        f"episodes/epoch={payload['epochs'][-1]['episodes'] if payload['epochs'] else 0}"
    )
    if mubit:
        lines.append(
            f"mubit_chat: live_ok={mubit.get('live_ok')} "
            f"cache_hits={mubit.get('cache_hits')} errors={mubit.get('errors')} "
            f"avg_latency_ms={mubit.get('avg_latency_ms')}"
        )
    lines.append("")
    for epoch in payload["epochs"]:
        lines.append(
            f"- epoch {epoch['epoch']}: mean_reward={epoch['mean_reward']} "
            f"correct={epoch['correct']}/{epoch['episodes']} "
            f"under={epoch['under_triage']} critical_under={epoch['critical_under']} "
            f"s1={epoch['share_s1_only']} cascade={epoch['share_cascade']} "
            f"s2={epoch['share_s2_only']} fallbacks={epoch['s2_fallbacks']}"
        )
    lines.append("")
    lines.append("## Events")
    for event in payload["events"]:
        lines.append(
            f"- {event['kind']} epoch={event['epoch']} case={event['case_id']} "
            f"sig={event['signature'][:60]}"
        )
    if not payload["events"]:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)
