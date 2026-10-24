"""Markdown for the learning report's external latte-bench section."""

from __future__ import annotations

from pathlib import Path

from config.settings import UNSET
from eval.latte.pin import PIN, STUDY_PATH
from eval.latte.read import Study, load_reference, load_study
from paths import ROOT


def _num(value: float | None) -> str:
    if value is None:
        return "n/a"
    return f"{value:.1f}"


def _delta(notes: float | None, plain: float | None) -> str:
    if notes is None or plain is None:
        return "n/a"
    return f"{notes - plain:+.1f}"


def _reference_lines(payload: dict | None, path: Path) -> list[str]:
    if payload is None:
        return [
            "No local calibrated-reference result.",
            "`make latte-bench` replays the passing default-milk witness with no API call",
            "when bun and the submodule are both present.",
        ]
    if payload.get("unreadable"):
        return [f"`{path.name}` was present and could not be read."]
    passed = payload.get("passed")
    score = payload.get("score")
    calls = payload.get("api_calls")
    task = payload.get("task", "heart")
    seed = payload.get("seed", 42)
    score_text = _num(score) if isinstance(score, (int, float)) else "n/a"
    state = "pass" if passed is True else "fail" if passed is False else "n/a"
    calls_text = str(calls) if isinstance(calls, int) else "n/a"
    return [
        f"Task `{task}`, seed {seed}: {state}, score {score_text}, API calls {calls_text}.",
        "This replay is the free calibrated reference. It is a witness for the scorer,",
        "and it is separate from the notes comparison below.",
    ]


def _study_lines(study: Study) -> list[str]:
    if not study.present:
        return [
            "The submodule is not checked out, so there is no published notes comparison to read.",
            "`git submodule update --init third_party/latte-bench` fetches the pinned commit.",
        ]
    if study.note:
        return [study.note]
    lines = [
        "Read from `docs/model-study/summary.json` in the pinned checkout.",
        "Notes means that run kept a feedback summary for the next attempt.",
        "The benchmark's own write-up says these figures do not establish learning or transfer.",
        "The last-attempt value is the mean best score across the seeds recorded in that file.",
    ]
    if study.tag or study.commit:
        lines.append(
            "Published file: "
            + (f"`{study.tag}` " if study.tag else "")
            + (f"at `{study.commit}`." if study.commit else ".")
        )
    if not study.rows:
        lines.append("The file had no complete notes / no-notes pair.")
        return lines
    lines.extend(
        [
            "",
            "| Model | No notes | Notes | Notes − no notes | Passes |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in study.rows:
        passes = f"{row.no_notes_passes} → {row.notes_passes}"
        lines.append(
            f"| {row.model} | {_num(row.no_notes_mean)} | {_num(row.notes_mean)} | "
            f"{_delta(row.notes_mean, row.no_notes_mean)} | {passes} |"
        )
    if study.incomplete:
        lines.append("")
        lines.append(f"Incomplete model rows left out of the table: {study.incomplete}.")
    return lines


def external_section(out_dir: Path | None = None) -> str:
    """Section appended to the BaanSafe learning report. It does not score the arms."""
    reference_path = None
    if out_dir is not None:
        candidate = out_dir / "latte-reference.json"
        if candidate.is_file():
            reference_path = candidate
    if reference_path is None:
        fallback = ROOT / "eval" / "out" / "latte-reference.json"
        reference_path = fallback if fallback.is_file() else (out_dir or ROOT / "eval" / "out") / "latte-reference.json"
    payload = load_reference(reference_path)
    study = load_study(STUDY_PATH)
    lines = [
        "## External sanity check: does the model learn from feedback",
        "",
        "MubitLabs/latte-bench is a third-party benchmark and publishes no license.",
        "BaanSafe checks it out at `third_party/latte-bench` and does not vendor its source.",
        f"`latte_bench.license_confirmation`: {UNSET}. Confirm the terms with Mubit",
        "before any use beyond this reference.",
        "",
        f"Pinned commit: `{PIN}`.",
        "",
        "Promotion stays on the BaanSafe held-out scores above.",
        "",
        "### Calibrated reference",
        "",
        *_reference_lines(payload, reference_path),
        "",
        "### Published notes comparison",
        "",
        *_study_lines(study),
    ]
    return "\n".join(lines).rstrip() + "\n"
