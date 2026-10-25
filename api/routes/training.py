"""`GET /training`: what we can measure about training, in one JSON document.

Four blocks. `finetune` is the correction-loop fine-tune registry on the
`baansafe-versions` volume (`registry.json` plus each version's
`metrics.json`, so loss curves are inline). `rl` summarises the last RL loop
report. `mubit_traffic` counts the `mubit_chat` trace rows: Mubit trains
per-task adapters from those calls on their side and exposes no training
API, so requests, distinct sessions, ok/error, latency, and tokens are the
measurable part. `events` counts the TrainingEvent log and lists export
manifests. Every file is optional; a missing one is named in `missing`.
No secret and no path outside the repo or a Modal volume is returned.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter

from config.settings import DecisionRequired, require_decision
from paths import ROOT
from trace import read_traces
from training.log import events_path

router = APIRouter()

# Same string as infra.modal.runtime.VERSIONS_PATH; that module imports modal,
# which the API image does not ship, so the path is repeated here on purpose.
VOLUME_REGISTRY_PATH = "/vol/registry.json"
LOCAL_REGISTRY_PATH = ROOT / "var" / "versions" / "registry.json"
DEFAULT_RL_RUN_PATH = ROOT / "eval" / "out" / "rl" / "run.json"
RL_TRAINING_OUT = ROOT / "eval" / "out" / "rl" / "training"
SNAPSHOT_ROOT = ROOT / "eval" / "snapshots" / "rl"
MANIFEST_DIRS = (ROOT / "training" / "out", RL_TRAINING_OUT)
KEPT_EXAMPLE_THRESHOLD = 25
MUBIT_NOTE = (
    "Mubit groups these into one task; kept-example count and adapter status "
    "are read in the Mubit console (Tasks / Adapters)."
)
VOLUME_ROOTS = ("/vol", "/data")


def registry_path() -> Path:
    """`TRAINING_REGISTRY_PATH`, else the volume file when `/vol` exists, else `var/`."""

    raw = os.environ.get("TRAINING_REGISTRY_PATH", "").strip()
    if raw:
        return Path(raw)
    volume = Path(VOLUME_REGISTRY_PATH)
    if volume.parent.is_dir():
        return volume
    return LOCAL_REGISTRY_PATH


def manifest_dirs() -> list[Path]:
    """`MANIFEST_DIRS`; a missing `eval/out/rl/training` falls back to the newest
    committed snapshot's `training/` (hosted images do not ship `eval/out`)."""
    dirs: list[Path] = []
    for directory in MANIFEST_DIRS:
        if directory == RL_TRAINING_OUT and not directory.is_dir() and SNAPSHOT_ROOT.is_dir():
            snapshots = sorted(
                path / "training" for path in SNAPSHOT_ROOT.iterdir() if (path / "training").is_dir()
            )
            if snapshots:
                directory = snapshots[-1]
        dirs.append(directory)
    return dirs


def rl_run_path() -> Path:
    raw = os.environ.get("RL_RUN_PATH", "").strip()
    if raw:
        return Path(raw)
    return DEFAULT_RL_RUN_PATH


def display_path(path: Path) -> str:
    """Repo-relative, a volume path as is, otherwise just the file name."""

    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        pass
    text = path.as_posix()
    if any(text == root or text.startswith(root + "/") for root in VOLUME_ROOTS):
        return text
    return path.name


def _read_json(path: Path, missing: list[str]) -> dict | list | None:
    if not path.is_file():
        missing.append(display_path(path))
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        missing.append(display_path(path))
        return None


def _decided(key: str) -> str:
    try:
        value = require_decision(key)
    except DecisionRequired:
        return "TODO_HUMAN"
    except Exception:  # noqa: BLE001 - a broken YAML must not take the page down
        return "TODO_HUMAN"
    return str(value)


def finetune_section() -> dict:
    missing: list[str] = []
    path = registry_path()
    registry = _read_json(path, missing)
    versions_raw = registry.get("versions") if isinstance(registry, dict) else None
    jobs_raw = registry.get("jobs") if isinstance(registry, dict) else None
    jobs = {
        job.get("job_id"): job
        for job in (jobs_raw or [])
        if isinstance(job, dict) and job.get("job_id")
    }
    versions: list[dict] = []
    for raw in versions_raw or []:
        if not isinstance(raw, dict) or not raw.get("version_id"):
            continue
        version_id = str(raw["version_id"])
        job = jobs.get(raw.get("training_job_id")) or {}
        metrics_path = path.parent / "versions" / version_id / "metrics.json"
        metrics = _read_json(metrics_path, missing) if metrics_path.is_file() else None
        versions.append(_version_row(raw, job, metrics if isinstance(metrics, dict) else None))
    # The registry appends; newest last. The page wants newest first.
    versions.reverse()
    return {
        "registry_path": display_path(path),
        "version_count": len(versions),
        "versions": versions,
        "decided": {
            "base_model": _decided("modal.finetune_base_model"),
            "gpu": _decided("modal.finetune_gpu"),
        },
        "missing": missing,
    }


def _version_row(version: dict, job: dict, metrics: dict | None) -> dict:
    notes = str(version.get("notes") or "")
    task = _task_from_notes(notes, metrics)
    row = {
        "version_id": version.get("version_id"),
        "task": task,
        "role": version.get("role"),
        "base_model": (metrics or {}).get("base_model") or version.get("model_name"),
        "gpu": (metrics or {}).get("gpu") or job.get("gpu"),
        "parent_version_id": version.get("parent_version_id"),
        "status": job.get("status") or ("completed" if metrics else "unknown"),
        "created_at": version.get("created_at") or created_at_from_id(str(version["version_id"])),
        "notes": notes,
        "trainer": (metrics or {}).get("trainer"),
        "steps": (metrics or {}).get("steps"),
        "rows": (metrics or {}).get("rows"),
        "first_loss": (metrics or {}).get("first_loss"),
        "last_loss": (metrics or {}).get("last_loss"),
        "min_loss": (metrics or {}).get("min_loss"),
        "mean_loss": (metrics or {}).get("mean_loss"),
        "wall_seconds": (metrics or {}).get("wall_seconds"),
        "heldout_accuracy": ((metrics or {}).get("heldout") or {}).get("accuracy"),
        "loss_curve": (metrics or {}).get("loss_curve") or [],
        "metrics": metrics,
    }
    return row


def created_at_from_id(version_id: str) -> str | None:
    """`ft-20261025T043300Z-1a2b3c4d` carries its UTC stamp. Else None."""

    parts = version_id.split("-")
    if len(parts) < 2:
        return None
    try:
        stamp = datetime.strptime(parts[1], "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    return stamp.isoformat()


def _task_from_notes(notes: str, metrics: dict | None) -> str | None:
    marker = "Task "
    if marker in notes:
        tail = notes.split(marker, 1)[1].strip().rstrip(".")
        if tail:
            return tail.split()[0]
    if metrics and metrics.get("trainer") == "setfit":
        return "s1_triage"
    if notes:
        return "sft"
    return None


def rl_section() -> dict:
    missing: list[str] = []
    path = rl_run_path()
    run = _read_json(path, missing)
    if not isinstance(run, dict):
        return {
            "run_path": display_path(path),
            "schema": None,
            "s2": None,
            "model": None,
            "epochs": [],
            "mubit": {},
            "overlay": {},
            "training": {},
            "finetune": None,
            "missing": missing,
        }
    epochs = [_epoch_row(epoch) for epoch in run.get("epochs") or [] if isinstance(epoch, dict)]
    overlay = run.get("final_overlay") if isinstance(run.get("final_overlay"), dict) else {}
    training = run.get("training") if isinstance(run.get("training"), dict) else {}
    finetune = training.get("finetune") if isinstance(training, dict) else None
    if finetune is None and isinstance(run.get("finetune"), str):
        finetune = run["finetune"]
    return {
        "run_path": display_path(path),
        "schema": run.get("schema"),
        "s2": run.get("s2"),
        "model": run.get("model"),
        "seed": run.get("seed"),
        "epochs": epochs,
        "mubit": run.get("mubit") if isinstance(run.get("mubit"), dict) else {},
        "overlay": {
            "graduation_threshold": overlay.get("graduation_threshold"),
            "graduated": _count(overlay.get("graduated")),
            "recommendations": _count(overlay.get("recommendations")),
            "demoted": _count(overlay.get("demoted")),
        },
        "training": {
            "status": training.get("status"),
            "counts": training.get("counts") if isinstance(training.get("counts"), dict) else {},
        },
        "finetune": finetune,
        "event_count": _count(run.get("events")),
        "episode_count": _count(run.get("episodes")),
        "missing": missing,
    }


def _epoch_row(epoch: dict) -> dict:
    return {
        "epoch": epoch.get("epoch"),
        "episodes": epoch.get("episodes"),
        "mean_reward": epoch.get("mean_reward"),
        "correct": epoch.get("correct"),
        "under_triage": epoch.get("under_triage"),
        "critical_under": epoch.get("critical_under"),
        "missed_human": epoch.get("missed_human"),
        "share_s1_only": epoch.get("share_s1_only"),
        "share_cascade": epoch.get("share_cascade"),
        "share_s2_only": epoch.get("share_s2_only"),
        "s2_fallbacks": epoch.get("s2_fallbacks"),
    }


def _count(value) -> int:
    if isinstance(value, (list, dict)):
        return len(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def mubit_traffic_section() -> dict:
    from trace import trace_path

    missing: list[str] = []
    path = trace_path()
    if not path.exists():
        missing.append(display_path(path))
    try:
        events = [event for event in read_traces(path=path) if event.stage == "mubit_chat"]
    except Exception:  # noqa: BLE001 - a bad trace line must not take the page down
        events = []
        missing.append(display_path(path))
    return {**summarize_mubit_chat(events), "trace_path": display_path(path), "missing": missing}


def summarize_mubit_chat(events: list) -> dict:
    """Counts over `mubit_chat` TraceEvents. Pure, so the RL run can reuse it."""

    ok = errors = cache_hits = 0
    latencies: list[int] = []
    tokens_in = tokens_out = 0
    sessions: set[str] = set()
    models: dict[str, int] = {}
    first: datetime | None = None
    last: datetime | None = None
    for event in events:
        note = event.notes or ""
        if "status=ok" in note:
            ok += 1
        elif "status=cache_hit" in note:
            cache_hits += 1
        else:
            errors += 1
        if "status=cache_hit" not in note:
            latencies.append(int(event.latency_ms))
        tokens_in += int(event.tokens_in or 0)
        tokens_out += int(event.tokens_out or 0)
        sessions.add(event.case_id)
        if event.model:
            models[event.model] = models.get(event.model, 0) + 1
        stamp = event.started_at
        if first is None or stamp < first:
            first = stamp
        if last is None or stamp > last:
            last = stamp
    ordered = sorted(latencies)
    return {
        "call_count": len(events),
        "ok_count": ok,
        "error_count": errors,
        "cache_hit_count": cache_hits,
        "distinct_sessions": len(sessions),
        "avg_latency_ms": (sum(ordered) / len(ordered)) if ordered else None,
        "p50_latency_ms": _percentile(ordered, 0.5),
        "p95_latency_ms": _percentile(ordered, 0.95),
        "tokens_in_total": tokens_in,
        "tokens_out_total": tokens_out,
        "models": models,
        "first_call_at": first.isoformat() if first else None,
        "last_call_at": last.isoformat() if last else None,
        "kept_example_threshold": KEPT_EXAMPLE_THRESHOLD,
        "via": "api.mubit.ai",
        "note": MUBIT_NOTE,
    }


def _percentile(ordered: list[int], share: float) -> float | None:
    if not ordered:
        return None
    index = min(len(ordered) - 1, max(0, round(share * (len(ordered) - 1))))
    return float(ordered[index])


def events_section() -> dict:
    missing: list[str] = []
    source = events_path()
    files = _event_files(source)
    if not files:
        missing.append(display_path(source))
    by_task: dict[str, int] = {}
    by_source: dict[str, int] = {}
    total = 0
    skipped = 0
    for file in files:
        for line in file.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                skipped += 1
                continue
            if not isinstance(row, dict):
                skipped += 1
                continue
            total += 1
            task = str(row.get("task") or "unknown")
            origin = str(row.get("source") or "unknown")
            by_task[task] = by_task.get(task, 0) + 1
            by_source[origin] = by_source.get(origin, 0) + 1
    manifests: list[dict] = []
    for directory in manifest_dirs():
        if not directory.is_dir():
            missing.append(display_path(directory))
            continue
        for file in sorted(directory.glob("*.manifest.json")):
            payload = _read_json(file, missing)
            if isinstance(payload, dict):
                manifests.append({"path": display_path(file), **payload})
    return {
        "events_path": display_path(source),
        "total": total,
        "skipped_lines": skipped,
        "by_task": by_task,
        "by_source": by_source,
        "manifests": manifests,
        "missing": missing,
    }


def _event_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    if source.is_dir():
        return sorted(path for path in source.glob("*.jsonl") if path.is_file())
    return []


def training_report() -> dict:
    finetune = finetune_section()
    rl = rl_section()
    mubit = mubit_traffic_section()
    events = events_section()
    missing = [*finetune["missing"], *rl["missing"], *mubit["missing"], *events["missing"]]
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "finetune": finetune,
        "rl": rl,
        "mubit_traffic": mubit,
        "events": events,
        "missing": missing,
        "note": (
            "Mubit trains per-task adapters from the recorded System 2 calls on their side; "
            "there is no API to read that state. This page shows what BaanSafe can measure."
        ),
    }


@router.get("/training")
def training() -> dict:
    return training_report()
