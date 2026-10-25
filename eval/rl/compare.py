"""Compare two RL runs (`run.json`) side by side.

    python -m eval.rl.compare --a <dir-or-name> --b <dir-or-name> \
        --out eval/out/rl_compare.md --json eval/out/rl_compare.json

`--a` / `--b` take a folder name under `eval/snapshots/rl/`, a directory that
holds a `run.json`, or a path to a `run.json`. The defaults are the two
committed 25 Oct snapshots: memory empty (A) vs memory local (B).

Pure functions here are reused by `GET /training` (`compare` section):
`resolve`, `load_run`, `compare`, `markdown`. No network, no model call.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from paths import ROOT

SCHEMA = "baansafe.rl_compare.v1"
SNAPSHOTS = ROOT / "eval" / "snapshots" / "rl"
DEFAULT_A = "20261025T0407Z-memory-empty"
DEFAULT_B = "20261025T0600Z-memory-local"
EPOCH_METRICS = (
    "correct",
    "under_triage",
    "critical_under",
    "missed_human",
    "mean_reward",
    "s2_fallbacks",
)
MUBIT_METRICS = ("live_ok", "cache_hits", "errors")
OVERLAY_METRICS = ("graduated", "recommendations", "demoted")
FLIP_FLAGS = ("critical_under", "under_triage", "missed_human")


def resolve(ref: str | Path) -> Path:
    """A snapshot name, a directory, or a `run.json` path -> the `run.json` path.

    Anything without a `.json` suffix is treated as a directory. Does not
    check that the file exists; callers decide how to report that.
    """

    text = str(ref).strip()
    candidate = Path(text)
    if not candidate.is_absolute() and "/" not in text and "\\" not in text:
        snapshot = SNAPSHOTS / text
        if snapshot.is_dir() or not candidate.exists():
            candidate = snapshot
    if candidate.is_dir() or candidate.suffix.lower() != ".json":
        candidate = candidate / "run.json"
    return candidate


def label_for(path: Path) -> str:
    """`eval/snapshots/rl/<stamp>/run.json` -> `<stamp>`; else the parent name."""

    return path.parent.name if path.name == "run.json" else path.stem


def load_run(ref: str | Path) -> dict:
    path = resolve(ref)
    if not path.is_file():
        raise FileNotFoundError(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path} is not a JSON object")
    return payload


def _num(value):
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    return None


def _delta(a, b):
    a_num, b_num = _num(a), _num(b)
    if a_num is None or b_num is None:
        return None
    delta = b_num - a_num
    return round(delta, 4) if isinstance(delta, float) else delta


def _cell(a, b) -> dict:
    return {"a": a, "b": b, "delta": _delta(a, b)}


def _epochs(run: dict) -> list[dict]:
    rows = [row for row in run.get("epochs") or [] if isinstance(row, dict)]
    return sorted(rows, key=lambda row: _num(row.get("epoch")) or 0)


def _last_epoch_number(run: dict) -> int | None:
    rows = _epochs(run)
    if not rows:
        return None
    value = _num(rows[-1].get("epoch"))
    return int(value) if value is not None else None


def _overlay_counts(run: dict) -> dict:
    overlay = run.get("final_overlay") if isinstance(run.get("final_overlay"), dict) else {}
    counts = {}
    for key in OVERLAY_METRICS:
        value = overlay.get(key)
        counts[key] = len(value) if isinstance(value, (list, dict)) else (_num(value) or 0)
    return counts


def flagged_ids(run: dict, flag: str, epoch: int | None = None) -> set[str]:
    """Episode ids with `flag` true in `epoch` (default: the run's last epoch)."""

    target = epoch if epoch is not None else _last_epoch_number(run)
    out: set[str] = set()
    for row in run.get("episodes") or []:
        if not isinstance(row, dict) or row.get("epoch") != target:
            continue
        if row.get(flag) is True and row.get("id"):
            out.add(str(row["id"]))
    return out


def _run_head(run: dict, label: str, path: Path | None) -> dict:
    epochs = _epochs(run)
    return {
        "label": label,
        "run_path": _display(path) if path else None,
        "s2": run.get("s2"),
        "model": run.get("model"),
        "seed": run.get("seed"),
        "epoch_count": len(epochs),
        "last_epoch": _last_epoch_number(run),
        "episode_count": len(run.get("episodes") or []),
    }


def _display(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def compare(
    run_a: dict,
    run_b: dict,
    *,
    label_a: str = "A",
    label_b: str = "B",
    path_a: Path | None = None,
    path_b: Path | None = None,
) -> dict:
    """Per-epoch, mubit, overlay and last-epoch per-case flips between two runs."""

    epochs_a = {int(_num(r.get("epoch")) or 0): r for r in _epochs(run_a)}
    epochs_b = {int(_num(r.get("epoch")) or 0): r for r in _epochs(run_b)}
    per_epoch = []
    for number in sorted(set(epochs_a) | set(epochs_b)):
        row_a = epochs_a.get(number) or {}
        row_b = epochs_b.get(number) or {}
        per_epoch.append(
            {
                "epoch": number,
                "metrics": {key: _cell(row_a.get(key), row_b.get(key)) for key in EPOCH_METRICS},
            }
        )
    last_a = _epochs(run_a)[-1] if _epochs(run_a) else {}
    last_b = _epochs(run_b)[-1] if _epochs(run_b) else {}
    last = {key: _cell(last_a.get(key), last_b.get(key)) for key in EPOCH_METRICS}
    mubit_a = run_a.get("mubit") if isinstance(run_a.get("mubit"), dict) else {}
    mubit_b = run_b.get("mubit") if isinstance(run_b.get("mubit"), dict) else {}
    mubit = {key: _cell(mubit_a.get(key), mubit_b.get(key)) for key in MUBIT_METRICS}
    overlay_a, overlay_b = _overlay_counts(run_a), _overlay_counts(run_b)
    overlay = {key: _cell(overlay_a.get(key), overlay_b.get(key)) for key in OVERLAY_METRICS}
    flips = {}
    for flag in FLIP_FLAGS:
        ids_a, ids_b = flagged_ids(run_a, flag), flagged_ids(run_b, flag)
        flips[flag] = {
            "fixed_in_b": sorted(ids_a - ids_b),
            "new_in_b": sorted(ids_b - ids_a),
            "both": sorted(ids_a & ids_b),
        }
    summary = (
        [{"group": "last_epoch", "metric": key, **last[key]} for key in EPOCH_METRICS]
        + [{"group": "mubit", "metric": key, **mubit[key]} for key in MUBIT_METRICS]
        + [{"group": "overlay", "metric": key, **overlay[key]} for key in OVERLAY_METRICS]
    )
    return {
        "schema": SCHEMA,
        "a": _run_head(run_a, label_a, path_a),
        "b": _run_head(run_b, label_b, path_b),
        "epochs": per_epoch,
        "last_epoch": {
            "epoch_a": _last_epoch_number(run_a),
            "epoch_b": _last_epoch_number(run_b),
            "metrics": last,
        },
        "mubit": mubit,
        "overlay": overlay,
        "flips": flips,
        "summary": summary,
    }


def compare_refs(ref_a: str | Path, ref_b: str | Path) -> dict:
    path_a, path_b = resolve(ref_a), resolve(ref_b)
    return compare(
        load_run(path_a),
        load_run(path_b),
        label_a=label_for(path_a),
        label_b=label_for(path_b),
        path_a=path_a,
        path_b=path_b,
    )


def _fmt(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def _fmt_delta(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:+.3f}"
    return f"{value:+d}"


def markdown(report: dict) -> str:
    a, b = report["a"], report["b"]
    lines = [
        "# RL compare",
        "",
        f"- A: `{a['label']}` ({a.get('run_path') or '?'}; s2={a.get('s2')}, epochs={a.get('epoch_count')})",
        f"- B: `{b['label']}` ({b.get('run_path') or '?'}; s2={b.get('s2')}, epochs={b.get('epoch_count')})",
        "- delta = B − A",
        "",
        f"## Last epoch (A epoch {report['last_epoch']['epoch_a']}, B epoch {report['last_epoch']['epoch_b']})",
        "",
        "| metric | A | B | delta |",
        "|---|---:|---:|---:|",
    ]
    for key in EPOCH_METRICS:
        cell = report["last_epoch"]["metrics"][key]
        lines.append(f"| {key} | {_fmt(cell['a'])} | {_fmt(cell['b'])} | {_fmt_delta(cell['delta'])} |")
    lines += ["", "## Per epoch", "", "| epoch | metric | A | B | delta |", "|---:|---|---:|---:|---:|"]
    for row in report["epochs"]:
        for key in EPOCH_METRICS:
            cell = row["metrics"][key]
            lines.append(
                f"| {row['epoch']} | {key} | {_fmt(cell['a'])} | {_fmt(cell['b'])} | {_fmt_delta(cell['delta'])} |"
            )
    lines += ["", "## Mubit", "", "| metric | A | B | delta |", "|---|---:|---:|---:|"]
    for key in MUBIT_METRICS:
        cell = report["mubit"][key]
        lines.append(f"| {key} | {_fmt(cell['a'])} | {_fmt(cell['b'])} | {_fmt_delta(cell['delta'])} |")
    lines += ["", "## Overlay", "", "| metric | A | B | delta |", "|---|---:|---:|---:|"]
    for key in OVERLAY_METRICS:
        cell = report["overlay"][key]
        lines.append(f"| {key} | {_fmt(cell['a'])} | {_fmt(cell['b'])} | {_fmt_delta(cell['delta'])} |")
    lines += ["", "## Per-case flips (last epoch)", ""]
    for flag in FLIP_FLAGS:
        flip = report["flips"][flag]
        lines.append(f"- `{flag}` fixed in B: {', '.join(flip['fixed_in_b']) or 'none'}")
        lines.append(f"- `{flag}` new in B: {', '.join(flip['new_in_b']) or 'none'}")
        lines.append(f"- `{flag}` in both: {', '.join(flip['both']) or 'none'}")
    return "\n".join(lines) + "\n"


def headline(report: dict) -> str:
    last = report["last_epoch"]["metrics"]
    parts = [f"{key} {_fmt(last[key]['a'])}→{_fmt(last[key]['b'])}" for key in EPOCH_METRICS]
    return f"rl-compare {report['a']['label']} vs {report['b']['label']}: " + ", ".join(parts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--a", default=DEFAULT_A, help="snapshot name, directory, or run.json")
    parser.add_argument("--b", default=DEFAULT_B, help="snapshot name, directory, or run.json")
    parser.add_argument("--out", default="eval/out/rl_compare.md", help="markdown output")
    parser.add_argument("--json", dest="json_out", default="eval/out/rl_compare.json", help="JSON output")
    args = parser.parse_args(argv)
    try:
        report = compare_refs(args.a, args.b)
    except FileNotFoundError as exc:
        print(f"rl-compare: run.json not found: {_display(Path(str(exc)))}", file=sys.stderr)
        return 2
    for target, text in ((Path(args.out), markdown(report)), (Path(args.json_out), json.dumps(report, indent=2) + "\n")):
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    print(headline(report))
    print(f"wrote {args.out} and {args.json_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
