"""`make eval-gate`: two thresholds over eval output that already exists.

SetFit: the newest `s1_triage` version in the fine-tune registry (read through
`api.routes.training.finetune_section`, so the volume / `var/` / env lookup is
the same as `GET /training`) must have held-out accuracy at or above
`--min-accuracy` (default 0.85, or `EVAL_GATE_MIN_ACCURACY`).

RL: the current run (`RL_RUN_PATH`, else `eval/out/rl/run.json`) must not have
a last-epoch `critical_under` above the last committed snapshot under
`eval/snapshots/rl/` (lexically last folder name with a `run.json`; names
start with a UTC stamp).

A missing input is a skip, not a failure: local machines do not mount the
Modal volume and a fresh clone has no `eval/out/`. `--strict` turns skips into
failures for a machine that is expected to have both. Nothing here calls
Mubit, and paths are printed through `display_path`, so no absolute path and
no secret reaches stdout.
"""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from api.routes.training import display_path, finetune_section, registry_path, rl_run_path
from paths import ROOT

DEFAULT_MIN_ACCURACY = 0.85
MIN_ACCURACY_ENV = "EVAL_GATE_MIN_ACCURACY"
DEFAULT_SNAPSHOT_ROOT = ROOT / "eval" / "snapshots" / "rl"
SETFIT_TASK = "s1_triage"
SETFIT_CHECK = "setfit_heldout_accuracy"
RL_CHECK = "rl_critical_under"

Status = Literal["pass", "fail", "skip"]


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    detail: str


def _number(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def check_setfit(min_accuracy: float) -> Check:
    """Newest `s1_triage` version with a held-out accuracy, against `min_accuracy`."""

    for row in finetune_section()["versions"]:  # newest first
        if row.get("task") != SETFIT_TASK:
            continue
        accuracy = _number(row.get("heldout_accuracy"))
        if accuracy is None:
            continue
        version_id = row.get("version_id")
        if accuracy >= min_accuracy:
            return Check(
                SETFIT_CHECK,
                "pass",
                f"{version_id} held-out accuracy {accuracy:.3f} >= {min_accuracy:.3f}",
            )
        return Check(
            SETFIT_CHECK,
            "fail",
            f"{version_id} held-out accuracy {accuracy:.3f} < {min_accuracy:.3f}",
        )
    return Check(
        SETFIT_CHECK,
        "skip",
        f"no SetFit held-out metrics at {display_path(registry_path())}",
    )


def last_snapshot_run(snapshot_root: Path) -> Path | None:
    """`<snapshot_root>/<lexically last folder>/run.json`, or None."""

    if not snapshot_root.is_dir():
        return None
    folders = sorted(
        (child for child in snapshot_root.iterdir() if child.is_dir() and (child / "run.json").is_file()),
        key=lambda child: child.name,
    )
    if not folders:
        return None
    return folders[-1] / "run.json"


def last_epoch_critical_under(run_path: Path) -> float | None:
    """`critical_under` of the last epoch in an RL `run.json`, or None when absent."""

    if not run_path.is_file():
        return None
    try:
        run = json.loads(run_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(run, dict):
        return None
    epochs = [epoch for epoch in run.get("epochs") or [] if isinstance(epoch, dict)]
    if not epochs:
        return None
    return _number(epochs[-1].get("critical_under"))


def check_rl(current_path: Path, snapshot_root: Path) -> Check:
    """Last-epoch `critical_under` of the current run against the last snapshot."""

    current = last_epoch_critical_under(current_path)
    if current is None:
        return Check(
            RL_CHECK,
            "skip",
            f"no current RL run with a last-epoch critical_under at {display_path(current_path)}",
        )
    snapshot = last_snapshot_run(snapshot_root)
    if snapshot is None:
        return Check(RL_CHECK, "skip", f"no RL snapshot with run.json under {display_path(snapshot_root)}")
    label = snapshot.parent.name
    baseline = last_epoch_critical_under(snapshot)
    if baseline is None:
        return Check(RL_CHECK, "skip", f"snapshot {label} has no last-epoch critical_under")
    current_text = _format(current)
    baseline_text = _format(baseline)
    if current > baseline:
        return Check(
            RL_CHECK,
            "fail",
            f"critical_under {current_text} > {baseline_text} in snapshot {label}",
        )
    return Check(
        RL_CHECK,
        "pass",
        f"critical_under {current_text} <= {baseline_text} in snapshot {label}",
    )


def _format(value: float) -> str:
    return str(int(value)) if value == int(value) else f"{value:.3f}"


def _min_accuracy_default() -> float:
    raw = os.environ.get(MIN_ACCURACY_ENV, "").strip()
    if not raw:
        return DEFAULT_MIN_ACCURACY
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{MIN_ACCURACY_ENV} must be a number, got {raw!r}") from exc


def run_checks(min_accuracy: float, rl_run: Path, snapshot_root: Path) -> list[Check]:
    return [check_setfit(min_accuracy), check_rl(rl_run, snapshot_root)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m eval.gate",
        description="Fail when SetFit held-out accuracy or RL critical under-triage crosses a threshold.",
    )
    try:
        min_accuracy_default = _min_accuracy_default()
    except ValueError as exc:
        parser.error(str(exc))
    parser.add_argument(
        "--min-accuracy",
        type=float,
        default=min_accuracy_default,
        help=f"SetFit held-out accuracy floor (default {MIN_ACCURACY_ENV} or {DEFAULT_MIN_ACCURACY}).",
    )
    parser.add_argument(
        "--rl-run",
        type=Path,
        default=None,
        help="Current RL run.json (default RL_RUN_PATH or eval/out/rl/run.json).",
    )
    parser.add_argument(
        "--snapshots",
        type=Path,
        default=DEFAULT_SNAPSHOT_ROOT,
        help="Folder of committed RL snapshots (default eval/snapshots/rl).",
    )
    parser.add_argument("--strict", action="store_true", help="Treat a skipped check as a failure.")
    args = parser.parse_args(argv)
    rl_run = args.rl_run if args.rl_run is not None else rl_run_path()

    failed = 0
    for check in run_checks(args.min_accuracy, rl_run, args.snapshots):
        print(f"[{check.status.upper()}] {check.name}: {check.detail}")
        if check.status == "fail" or (args.strict and check.status == "skip"):
            failed += 1
    if failed:
        print(f"eval-gate: FAILED ({failed})")
        return 1
    print("eval-gate: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
