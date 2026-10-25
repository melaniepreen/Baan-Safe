"""Eval gate: fail when training quality regressed. `make eval-gate`.

Two checks, one line each (`PASS` / `FAIL` / `SKIP` with the numbers):

- `s1_heldout`: the newest fine-tune version for task `s1_triage` must have a
  held-out accuracy of at least `EVAL_GATE_S1_ACC` (default 0.85). The
  registry is read through `api.routes.training.finetune_section`
  (`TRAINING_REGISTRY_PATH`, else `/vol/registry.json`, else
  `var/versions/registry.json`). No registry, no `s1_triage` version, or no
  `heldout` block -> SKIP.
- `rl_critical_under`: the current `eval/out/rl/run.json` (`RL_RUN_PATH`)
  last-epoch `critical_under` must not exceed the baseline snapshot's
  last-epoch `critical_under`. Baseline is `EVAL_GATE_BASELINE` (snapshot name,
  directory, or `run.json`), default `eval/snapshots/rl/20261025T0600Z-memory-local`.
  No current run -> SKIP.

Exit 1 when any check fails, else 0. Reads files only; no network, no model.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.routes.training import display_path, finetune_section, rl_run_path  # noqa: E402
from eval.rl import compare as rl_compare  # noqa: E402

DEFAULT_S1_ACC = 0.85
DEFAULT_BASELINE = rl_compare.DEFAULT_B
S1_TASK = "s1_triage"


def s1_threshold() -> float:
    raw = os.environ.get("EVAL_GATE_S1_ACC", "").strip()
    return float(raw) if raw else DEFAULT_S1_ACC


def baseline_ref() -> str:
    return os.environ.get("EVAL_GATE_BASELINE", "").strip() or DEFAULT_BASELINE


def check_s1(threshold: float) -> tuple[str, str]:
    """(`PASS`|`FAIL`|`SKIP`, message) for the newest `s1_triage` version."""

    section = finetune_section()
    registry = section["registry_path"]
    if not section["versions"]:
        return "SKIP", f"s1_heldout: no fine-tune registry or no versions at {registry}"
    newest = next((v for v in section["versions"] if v.get("task") == S1_TASK), None)
    if newest is None:
        return "SKIP", f"s1_heldout: no {S1_TASK} version in {registry}"
    accuracy = newest.get("heldout_accuracy")
    if accuracy is None:
        return "SKIP", f"s1_heldout: {newest['version_id']} has no heldout block (no held-out file at train time)"
    rows = ((newest.get("metrics") or {}).get("heldout") or {}).get("rows")
    detail = f"{newest['version_id']} heldout accuracy {accuracy:.3f} on {rows if rows is not None else '?'} rows, threshold {threshold:.2f}"
    if float(accuracy) < threshold:
        return "FAIL", f"s1_heldout: {detail}"
    return "PASS", f"s1_heldout: {detail}"


def _last_critical_under(run: dict) -> tuple[int | None, int | None]:
    epochs = [row for row in run.get("epochs") or [] if isinstance(row, dict)]
    if not epochs:
        return None, None
    last = max(epochs, key=lambda row: row.get("epoch") or 0)
    value = last.get("critical_under")
    return (last.get("epoch"), int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None)


def check_rl(baseline: str) -> tuple[str, str]:
    """(`PASS`|`FAIL`|`SKIP`, message) for current vs baseline last-epoch critical_under."""

    current_path = rl_run_path()
    if not current_path.is_file():
        return "SKIP", f"rl_critical_under: no current run at {display_path(current_path)} (make rl-loop-replay)"
    baseline_path = rl_compare.resolve(baseline)
    if not baseline_path.is_file():
        return "SKIP", f"rl_critical_under: baseline {display_path(baseline_path)} not found"
    try:
        current = rl_compare.load_run(current_path)
        base = rl_compare.load_run(baseline_path)
    except (OSError, ValueError) as exc:
        return "SKIP", f"rl_critical_under: unreadable run ({type(exc).__name__})"
    cur_epoch, cur_value = _last_critical_under(current)
    base_epoch, base_value = _last_critical_under(base)
    if cur_value is None or base_value is None:
        return "SKIP", "rl_critical_under: a run has no epochs or no critical_under"
    detail = (
        f"current {cur_value} (epoch {cur_epoch}, {display_path(current_path)}) vs baseline "
        f"{base_value} (epoch {base_epoch}, {rl_compare.label_for(baseline_path)})"
    )
    if cur_value > base_value:
        return "FAIL", f"rl_critical_under: {detail}"
    return "PASS", f"rl_critical_under: {detail}"


def run_gate(threshold: float, baseline: str) -> list[tuple[str, str]]:
    return [check_s1(threshold), check_rl(baseline)]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--s1-acc", type=float, default=None, help=f"override EVAL_GATE_S1_ACC (default {DEFAULT_S1_ACC})")
    parser.add_argument("--baseline", default=None, help="override EVAL_GATE_BASELINE (snapshot name, dir, or run.json)")
    args = parser.parse_args(argv)
    threshold = args.s1_acc if args.s1_acc is not None else s1_threshold()
    baseline = args.baseline or baseline_ref()
    results = run_gate(threshold, baseline)
    for status, message in results:
        print(f"{status} {message}")
    failed = [status for status, _ in results if status == "FAIL"]
    print(f"eval-gate: {len(failed)} failed, {sum(1 for s, _ in results if s == 'PASS')} passed, {sum(1 for s, _ in results if s == 'SKIP')} skipped")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
