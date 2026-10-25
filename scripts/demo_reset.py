"""Reset demo state so the frozen 3-minute script starts from the same point.

`make demo-reset` is a dry run. Add `RESET_ARGS=--yes` (or run the script
with `--yes`) to change anything.

Local mode (default, `--local`) uses the same env-derived paths the API uses:

    TRACE_PATH              traces.jsonl (default <repo>/traces.jsonl)   -> truncated
    MEMORY_LOCAL_PATH       memory.jsonl (default var/memory.jsonl)      -> `baansafe-case`
                            and `baansafe-correction` rows dropped, `baansafe-policy`
                            rows kept; the 10 policy lessons are re-seeded through
                            scripts/seed_memory.py when none are left
    S2_CACHE_RECORD_PATH    recorded Nemotron replies (only when set)    -> removed
    MOCK_CORRECTIONS_PATH   operator correction log                      -> truncated
    TRAINING_EVENTS_PATH    training event log                           -> left alone
                            unless `--events`

Hosted mode (`--hosted`) does the same against the Modal volume
`baansafe-demo` (mounted at /data by infra/modal/gateway_app.py):
`modal volume get` memory.jsonl, filter it, `modal volume put --force`;
`modal volume rm` traces.jsonl, s2_cache.jsonl, corrections.jsonl (and
events.jsonl with `--events`). The gateway recreates the files on its next
write. A container that is already running keeps its own view of the volume
until it scales down (scaledown_window is 120 s), so run this between demos,
not during one.

Both modes print a before/after summary: memory rows per lane, line counts
of the other files. The committed replay fixture
`fixtures/s2_cache/demo.jsonl` (S2_CACHE_PATH) is never touched. Nothing
here prints an environment value other than file paths; no key is read.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory.content import LANE_CASE, LANE_CORRECTION, LANE_POLICY  # noqa: E402

DEMO_VOLUME = "baansafe-demo"
DROP_LANES = frozenset({LANE_CASE, LANE_CORRECTION})
# Remote file names on the volume (infra/modal/gateway_app.py STUB_ENV).
HOSTED_FILES = {
    "traces": "traces.jsonl",
    "memory": "memory.jsonl",
    "s2_cache": "s2_cache.jsonl",
    "corrections": "corrections.jsonl",
    "events": "events.jsonl",
}

Runner = Callable[[list[str]], subprocess.CompletedProcess]


@dataclass
class Plan:
    """What a reset will do. Built before anything changes."""

    mode: str
    paths: dict[str, str]
    before: dict[str, Any]
    after: dict[str, Any]
    kept_rows: list[dict[str, Any]] = field(default_factory=list)
    reseed: bool = False
    include_events: bool = False
    notes: list[str] = field(default_factory=list)
    # Hosted mode: which remote files exist, so `rm` is not sent for a missing one.
    present: dict[str, bool] = field(default_factory=dict)


# --- pure helpers -----------------------------------------------------------


def lane_counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counter: Counter[str] = Counter(str(row.get("lane") or "(none)") for row in rows)
    return dict(sorted(counter.items()))


def parse_rows(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def filter_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Drop case and correction rows. Everything else (policy, unknown) stays."""
    return [row for row in rows if str(row.get("lane") or "") not in DROP_LANES]


def policy_lessons() -> list[dict[str, Any]]:
    """The 10 corpus-derived items, in the shape memory.local.ingest accepts."""
    from scripts.seed_memory import build_lessons

    return build_lessons()


def line_count(path: Path | None) -> int:
    if path is None or not path.exists():
        return 0
    with path.open("r", encoding="utf-8") as handle:
        return sum(1 for line in handle if line.strip())


def write_rows(path: Path, rows: list[dict[str, Any]]) -> None:
    """Rewrite the memory file atomically (tmp + rename)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
    os.replace(tmp, path)


# --- local mode ---------------------------------------------------------------


def local_paths() -> dict[str, Path | None]:
    from memory.local import store_path
    from mocks.loader import corrections_path
    from system2.cache import record_path
    from trace import trace_path
    from training.log import events_path

    return {
        "traces": trace_path(),
        "memory": store_path(),
        "s2_cache": record_path(),
        "corrections": corrections_path(),
        "events": events_path(),
    }


def plan_local(*, include_events: bool) -> Plan:
    paths = local_paths()
    memory_path = paths["memory"]
    assert memory_path is not None
    rows = parse_rows(memory_path.read_text(encoding="utf-8")) if memory_path.exists() else []
    kept = filter_rows(rows)
    reseed = not any(str(row.get("lane") or "") == LANE_POLICY for row in kept)
    before = {
        "memory_rows": lane_counts(rows),
        "traces_lines": line_count(paths["traces"]),
        "s2_cache_lines": line_count(paths["s2_cache"]),
        "corrections_lines": line_count(paths["corrections"]),
        "events_lines": line_count(paths["events"]),
    }
    after_rows = lane_counts(kept)
    if reseed:
        after_rows[LANE_POLICY] = after_rows.get(LANE_POLICY, 0) + len(policy_lessons())
    after = {
        "memory_rows": after_rows,
        "traces_lines": 0,
        "s2_cache_lines": 0,
        "corrections_lines": 0,
        "events_lines": 0 if include_events else before["events_lines"],
    }
    notes = []
    if paths["s2_cache"] is None:
        notes.append("S2_CACHE_RECORD_PATH is unset; no recorded-reply file to remove.")
    if reseed:
        notes.append("no baansafe-policy rows left; the policy lessons will be re-seeded.")
    return Plan(
        mode="local",
        paths={key: str(value) if value is not None else "" for key, value in paths.items()},
        before=before,
        after=after,
        kept_rows=kept,
        reseed=reseed,
        include_events=include_events,
        notes=notes,
    )


def apply_local(plan: Plan) -> None:
    from memory.local import ingest

    paths = {key: Path(value) if value else None for key, value in plan.paths.items()}
    traces = paths["traces"]
    if traces is not None:
        traces.parent.mkdir(parents=True, exist_ok=True)
        traces.write_text("", encoding="utf-8")
    s2_cache = paths["s2_cache"]
    if s2_cache is not None and s2_cache.exists():
        s2_cache.unlink()
    corrections = paths["corrections"]
    if corrections is not None and corrections.exists():
        corrections.write_text("", encoding="utf-8")
    events = paths["events"]
    if plan.include_events and events is not None and events.exists():
        events.write_text("", encoding="utf-8")
    memory = paths["memory"]
    assert memory is not None
    write_rows(memory, plan.kept_rows)
    if plan.reseed:
        ingest(policy_lessons(), path=memory)


# --- hosted mode --------------------------------------------------------------


def default_runner(args: list[str]) -> subprocess.CompletedProcess:
    """`python -m modal volume ...` with the interpreter running this script."""
    return subprocess.run(
        [sys.executable, "-m", "modal", "volume", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def _fetch(runner: Runner, remote: str, workdir: Path) -> Path | None:
    """Download one volume file. None when the file is not on the volume."""
    local = workdir / remote
    result = runner(["get", DEMO_VOLUME, remote, str(local), "--force"])
    if result.returncode != 0 or not local.exists():
        return None
    return local


def plan_hosted(*, include_events: bool, runner: Runner, workdir: Path) -> Plan:
    fetched = {key: _fetch(runner, name, workdir) for key, name in HOSTED_FILES.items()}
    memory_file = fetched["memory"]
    rows = parse_rows(memory_file.read_text(encoding="utf-8")) if memory_file else []
    kept = filter_rows(rows)
    reseed = not any(str(row.get("lane") or "") == LANE_POLICY for row in kept)
    before = {
        "memory_rows": lane_counts(rows),
        "traces_lines": line_count(fetched["traces"]),
        "s2_cache_lines": line_count(fetched["s2_cache"]),
        "corrections_lines": line_count(fetched["corrections"]),
        "events_lines": line_count(fetched["events"]),
    }
    after_rows = lane_counts(kept)
    if reseed:
        after_rows[LANE_POLICY] = after_rows.get(LANE_POLICY, 0) + len(policy_lessons())
    after = {
        "memory_rows": after_rows,
        "traces_lines": 0,
        "s2_cache_lines": 0,
        "corrections_lines": 0,
        "events_lines": 0 if include_events else before["events_lines"],
    }
    notes = [
        f"{DEMO_VOLUME}:{name} is not on the volume"
        for key, name in HOSTED_FILES.items()
        if fetched[key] is None
    ]
    if reseed:
        notes.append("no baansafe-policy rows on the volume; the policy lessons will be re-seeded.")
    notes.append("a running gateway container sees the new files after it scales down.")
    return Plan(
        mode="hosted",
        paths={key: f"{DEMO_VOLUME}:{name}" for key, name in HOSTED_FILES.items()},
        before=before,
        after=after,
        kept_rows=kept,
        reseed=reseed,
        include_events=include_events,
        notes=notes,
        present={key: value is not None for key, value in fetched.items()},
    )


def apply_hosted(plan: Plan, *, runner: Runner, workdir: Path) -> list[str]:
    """Push the filtered memory file and delete the others. Returns failures."""
    from memory.local import ingest

    failures: list[str] = []
    staged = workdir / "memory.reset.jsonl"
    write_rows(staged, plan.kept_rows)
    if plan.reseed:
        ingest(policy_lessons(), path=staged)
    result = runner(["put", DEMO_VOLUME, str(staged), HOSTED_FILES["memory"], "--force"])
    if result.returncode != 0:
        failures.append(f"put {HOSTED_FILES['memory']}: exit {result.returncode}")
    targets = ["traces", "s2_cache", "corrections"]
    if plan.include_events:
        targets.append("events")
    for key in targets:
        if not plan.present.get(key, True):
            continue
        result = runner(["rm", DEMO_VOLUME, HOSTED_FILES[key]])
        if result.returncode != 0:
            failures.append(f"rm {HOSTED_FILES[key]}: exit {result.returncode}")
    return failures


# --- CLI ----------------------------------------------------------------------


def summary(plan: Plan, *, applied: bool) -> str:
    label = "applied" if applied else "dry-run"
    lines = [f"demo-reset {plan.mode} ({label})"]
    for key in ("traces", "memory", "s2_cache", "corrections", "events"):
        lines.append(f"  {key:12} {plan.paths.get(key) or '(unset)'}")
    lines.append("  before:")
    lines.append(f"    memory rows per lane: {plan.before['memory_rows'] or '{}'}")
    for key in ("traces_lines", "s2_cache_lines", "corrections_lines", "events_lines"):
        lines.append(f"    {key}: {plan.before[key]}")
    lines.append("  after:")
    lines.append(f"    memory rows per lane: {plan.after['memory_rows'] or '{}'}")
    for key in ("traces_lines", "s2_cache_lines", "corrections_lines", "events_lines"):
        lines.append(f"    {key}: {plan.after[key]}")
    for note in plan.notes:
        lines.append(f"  note: {note}")
    if not applied:
        lines.append("  nothing changed. Pass --yes to apply.")
    return "\n".join(lines)


def run(argv: list[str] | None = None, *, runner: Runner | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--local", action="store_true", help="env-derived local paths (default)")
    mode.add_argument("--hosted", action="store_true", help=f"the Modal volume {DEMO_VOLUME}")
    parser.add_argument("--yes", action="store_true", help="apply; without it this is a dry run")
    parser.add_argument("--events", action="store_true", help="also truncate the training event log")
    parser.add_argument("--json", action="store_true", help="JSON summary on stdout")
    args = parser.parse_args(argv)

    if args.hosted:
        run_modal = runner or default_runner
        workdir = Path(tempfile.mkdtemp(prefix="baansafe-demo-reset-"))
        try:
            plan = plan_hosted(include_events=args.events, runner=run_modal, workdir=workdir)
            failures: list[str] = []
            if args.yes:
                failures = apply_hosted(plan, runner=run_modal, workdir=workdir)
        finally:
            shutil.rmtree(workdir, ignore_errors=True)
    else:
        plan = plan_local(include_events=args.events)
        failures = []
        if args.yes:
            apply_local(plan)

    if args.json:
        print(
            json.dumps(
                {
                    "mode": plan.mode,
                    "applied": bool(args.yes),
                    "paths": plan.paths,
                    "before": plan.before,
                    "after": plan.after,
                    "reseed": plan.reseed,
                    "notes": plan.notes,
                    "failures": failures,
                },
                indent=2,
                default=str,
            )
        )
    else:
        print(summary(plan, applied=bool(args.yes)))
        for failure in failures:
            print(f"  failed: {failure}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(run())
