"""`python -m eval.rl.compare [--a NAME] [--b NAME]`: two RL snapshots side by side.

Reads `eval/snapshots/rl/<name>/run.json` for each side, pairs the epochs by
number, and takes the last epoch of each as the headline (critical
under-triage, mean reward, correct, under-triage, missed human). The
committed snapshots are the memory-off (`memory-empty`) and memory-on
(`memory-local`) runs, so with no arguments this is the "memory off vs on"
number. Pure functions; `main` writes `eval/out/rl_compare.md` and
`rl_compare.json`. `GET /training/compare` returns the same dict.

Snapshot names are checked against the folder listing before any read, so a
name from a query string can never point outside `eval/snapshots/rl/`.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from paths import ROOT

SNAPSHOT_ROOT = ROOT / "eval" / "snapshots" / "rl"
DEFAULT_OUT_DIR = ROOT / "eval" / "out"
SCHEMA = "baansafe.rl_compare.v1"
HEADLINE_METRICS = ("critical_under", "mean_reward", "correct", "under_triage", "missed_human")
EPOCH_FIELDS = (
    "episodes",
    "mean_reward",
    "correct",
    "under_triage",
    "critical_under",
    "missed_human",
    "share_s1_only",
    "share_cascade",
    "share_s2_only",
    "s2_fallbacks",
)
OVERLAY_FIELDS = ("graduated", "recommendations", "demoted")
MUBIT_FIELDS = ("live_ok", "cache_hits", "errors", "mubit_chat_count", "avg_latency_ms", "model", "via")


def list_snapshots(root: Path | None = None) -> list[str]:
    """Sorted folder names under the snapshot root that hold a `run.json`."""

    base = root or SNAPSHOT_ROOT
    if not base.is_dir():
        return []
    return sorted(path.name for path in base.iterdir() if path.is_dir() and (path / "run.json").is_file())


def load_snapshot(name: str, root: Path | None = None) -> dict:
    """`run.json` of one snapshot. `ValueError` for anything not a listed bare folder name."""

    if not isinstance(name, str) or not name or "/" in name or "\\" in name or ".." in name:
        raise ValueError("snapshot name must be a bare folder name")
    base = root or SNAPSHOT_ROOT
    if name not in list_snapshots(base):
        raise ValueError(f"unknown snapshot {name!r}")
    payload = json.loads((base / name / "run.json").read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"snapshot {name!r} run.json is not an object")
    return payload


def compare(a: dict, b: dict, a_name: str, b_name: str) -> dict:
    """Side A vs side B: per-side summary, last-epoch headline, epochs paired by number."""

    side_a = _side(a, a_name)
    side_b = _side(b, b_name)
    last_a = side_a["epochs"][-1] if side_a["epochs"] else {}
    last_b = side_b["epochs"][-1] if side_b["epochs"] else {}
    headline = {metric: _pair(last_a.get(metric), last_b.get(metric)) for metric in HEADLINE_METRICS}
    by_epoch_a = {row["epoch"]: row for row in side_a["epochs"] if row["epoch"] is not None}
    by_epoch_b = {row["epoch"]: row for row in side_b["epochs"] if row["epoch"] is not None}
    per_epoch = []
    for number in sorted(set(by_epoch_a) | set(by_epoch_b), key=_epoch_key):
        row_a = by_epoch_a.get(number)
        row_b = by_epoch_b.get(number)
        per_epoch.append(
            {
                "epoch": number,
                "a": row_a,
                "b": row_b,
                "delta": {
                    metric: _delta((row_a or {}).get(metric), (row_b or {}).get(metric))
                    for metric in HEADLINE_METRICS
                },
            }
        )
    return {"schema": SCHEMA, "a": side_a, "b": side_b, "headline": headline, "per_epoch": per_epoch}


def _side(run: dict, name: str) -> dict:
    epochs = [_epoch_row(epoch) for epoch in run.get("epochs") or [] if isinstance(epoch, dict)]
    overlay = run.get("final_overlay") if isinstance(run.get("final_overlay"), dict) else {}
    mubit = run.get("mubit") if isinstance(run.get("mubit"), dict) else {}
    return {
        "name": name,
        "model": run.get("model"),
        "seed": run.get("seed"),
        "s2": run.get("s2"),
        "epochs": epochs,
        "mubit": {field: mubit.get(field) for field in MUBIT_FIELDS},
        "overlay": {field: _count(overlay.get(field)) for field in OVERLAY_FIELDS},
    }


# Same shape as api.routes.training._epoch_row / _count. That module imports
# FastAPI, which this CLI does not need, so the two small helpers live here too.
def _epoch_row(epoch: dict) -> dict:
    return {"epoch": epoch.get("epoch"), **{field: epoch.get(field) for field in EPOCH_FIELDS}}


def _count(value) -> int:
    if isinstance(value, (list, dict)):
        return len(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def _epoch_key(value) -> tuple:
    return (0, value) if _is_number(value) else (1, str(value))


def _is_number(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _delta(a, b):
    if not _is_number(a) or not _is_number(b):
        return None
    if isinstance(a, int) and isinstance(b, int):
        return b - a
    return round(b - a, 3)


def _pair(a, b) -> dict:
    return {"a": a, "b": b, "delta": _delta(a, b)}


# ---- rendering -------------------------------------------------------------


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        if value.is_integer():
            return str(int(value))
        return f"{value:.3f}".rstrip("0").rstrip(".")
    return str(value)


def _fmt_delta(value) -> str:
    if value is None:
        return "—"
    text = _fmt(value)
    return text if text.startswith("-") or text == "0" else "+" + text


def headline_line(result: dict) -> str:
    """One line: `A vs B: critical_under 9 -> 2 (-7) · mean_reward ...`."""

    headline = result["headline"]
    parts = []
    for metric in ("critical_under", "mean_reward", "correct"):
        cell = headline[metric]
        parts.append(f"{metric} {_fmt(cell['a'])} -> {_fmt(cell['b'])} ({_fmt_delta(cell['delta'])})")
    return f"{result['a']['name']} vs {result['b']['name']}: " + " · ".join(parts)


def render_markdown(result: dict) -> str:
    side_a = result["a"]
    side_b = result["b"]
    lines = [
        "# RL snapshot comparison",
        "",
        f"A = `{side_a['name']}` · B = `{side_b['name']}`. Delta is B − A; the headline is the last epoch of each run.",
        "",
    ]
    for label, side in (("A", side_a), ("B", side_b)):
        lines.append(
            f"- {label} `{side['name']}`: s2={_fmt(side['s2'])} model={_fmt(side['model'])} "
            f"seed={_fmt(side['seed'])} epochs={len(side['epochs'])}"
        )
    lines += ["", "## Headline (last epoch)", "", "| Metric | A | B | Delta |", "|---|---:|---:|---:|"]
    for metric in HEADLINE_METRICS:
        cell = result["headline"][metric]
        lines.append(f"| {metric} | {_fmt(cell['a'])} | {_fmt(cell['b'])} | {_fmt_delta(cell['delta'])} |")
    per_epoch_metrics = ("correct", "under_triage", "critical_under", "mean_reward")
    header = ["Epoch"]
    for metric in per_epoch_metrics:
        header += [f"{metric} A", f"{metric} B", "Δ"]
    lines += [
        "",
        "## Per epoch",
        "",
        "| " + " | ".join(header) + " |",
        "|---|" + "---:|" * (len(header) - 1),
    ]
    for row in result["per_epoch"]:
        cells = [_fmt(row["epoch"])]
        for metric in per_epoch_metrics:
            cells += [
                _fmt((row["a"] or {}).get(metric)),
                _fmt((row["b"] or {}).get(metric)),
                _fmt_delta(row["delta"].get(metric)),
            ]
        lines.append("| " + " | ".join(cells) + " |")
    if not result["per_epoch"]:
        lines.append("| — |" + " — |" * (len(header) - 1))
    lines += ["", "## Mubit", "", "| | A | B |", "|---|---:|---:|"]
    for field in MUBIT_FIELDS:
        lines.append(f"| {field} | {_fmt(side_a['mubit'].get(field))} | {_fmt(side_b['mubit'].get(field))} |")
    lines += ["", "## Overlay", "", "| | A | B |", "|---|---:|---:|"]
    for field in OVERLAY_FIELDS:
        lines.append(f"| {field} | {_fmt(side_a['overlay'].get(field))} | {_fmt(side_b['overlay'].get(field))} |")
    lines.append("")
    return "\n".join(lines)


# ---- CLI -------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Compare two RL loop snapshots (A vs B).")
    parser.add_argument("--a", help="snapshot folder name for side A (default: first listed)")
    parser.add_argument("--b", help="snapshot folder name for side B (default: last listed)")
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR), help="where rl_compare.md/.json go")
    args = parser.parse_args(argv)
    snapshots = list_snapshots()
    if not snapshots:
        print(f"no snapshot under {_display(SNAPSHOT_ROOT)}; run make rl-snapshot", file=sys.stderr)
        return 2
    a_name = args.a or snapshots[0]
    b_name = args.b or snapshots[-1]
    try:
        result = compare(load_snapshot(a_name), load_snapshot(b_name), a_name, b_name)
    except ValueError as exc:
        print(f"{exc}; available: {', '.join(snapshots)}", file=sys.stderr)
        return 2
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "rl_compare.md").write_text(render_markdown(result), encoding="utf-8")
    (out_dir / "rl_compare.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(headline_line(result))
    print(f"wrote {_display(out_dir / 'rl_compare.md')} and {_display(out_dir / 'rl_compare.json')}")
    return 0


def _display(path: Path) -> str:
    """Repo-relative when inside the repo, else as given."""

    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())
