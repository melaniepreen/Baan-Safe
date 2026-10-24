"""Export per-task training files from the append-only event log.

The schema lives in contracts.training. This module imports it and does not
redefine it. Rows are deduplicated on content_hash. The earliest event wins.
Output order is the content hash, so the files do not depend on log order.

s1 is {text, label, group_id, weight}. s2 is chat: policy text and the
rendered call in, the action and a short reason out. sapling is
{policy, evidence, claim, verdict}. prefs is {prompt, chosen, rejected}
where output_model differs from output_correct. Each file has a manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path

from contracts.training import SCHEMA_VERSION, InputRef, TrainingEvent
from fixtures.load import load_fixture
from policies.service import PolicyError, get_service
from training.log import events_path

EXPORT_NAMES = ("s1", "s2", "sapling", "prefs")

_TASK_FOR_EXPORT = {
    "s1": "s1_triage",
    "s2": "s2_action",
    "sapling": "sapling_verdict",
}


class ExportError(ValueError):
    """The log could not be rendered into a training file."""


def default_source() -> Path:
    """The log file when TRAINING_EVENTS_PATH is set, otherwise the events directory."""

    raw = os.environ.get("TRAINING_EVENTS_PATH", "").strip()
    if raw:
        return Path(raw)
    return events_path().parent


def export_datasets(
    source: Path,
    out_dir: Path,
    *,
    allow_missing: bool = False,
) -> dict[str, dict]:
    """Write the four JSONL files and their manifests. Return the manifests."""

    events = _load_events(source, allow_missing=allow_missing)
    kept = _dedupe(events)
    out_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, dict] = {}
    for name in EXPORT_NAMES:
        paired = _rows_for(name, kept)
        paired.sort(key=lambda item: item[0].content_hash)
        body = "".join(_dumps(row) for _, row in paired)
        jsonl_path = out_dir / f"{name}.jsonl"
        jsonl_path.write_text(body, encoding="utf-8")
        manifest = _manifest([event for event, _row in paired], body)
        manifest_path = out_dir / f"{name}.manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        written[name] = manifest
    return written


def _load_events(source: Path, *, allow_missing: bool) -> list[TrainingEvent]:
    if not source.exists():
        if allow_missing:
            return []
        raise ExportError(f"{source} does not exist")
    files = _event_files(source)
    events: list[TrainingEvent] = []
    for path in files:
        events.extend(_read_file(path))
    return events


def _event_files(source: Path) -> list[Path]:
    if source.is_file():
        return [source]
    return sorted(path for path in source.glob("*.jsonl") if path.is_file())


def _read_file(path: Path) -> list[TrainingEvent]:
    events: list[TrainingEvent] = []
    text = path.read_text(encoding="utf-8")
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(TrainingEvent.model_validate_json(line))
        except Exception as exc:  # noqa: BLE001 — the log line is the context
            raise ExportError(f"{path}:{line_number}: {exc}") from exc
    return events


def _dedupe(events: list[TrainingEvent]) -> list[TrainingEvent]:
    """Keep the earliest event for each content_hash."""

    ordered = sorted(events, key=lambda event: (event.created_at, event.event_id))
    kept: dict[str, TrainingEvent] = {}
    for event in ordered:
        if event.content_hash not in kept:
            kept[event.content_hash] = event
    return list(kept.values())


def _rows_for(name: str, events: list[TrainingEvent]) -> list[tuple[TrainingEvent, dict]]:
    task = _TASK_FOR_EXPORT.get(name)
    pool = events if task is None else [event for event in events if event.task == task]
    rows: list[tuple[TrainingEvent, dict]] = []
    for event in pool:
        row = _ROW_FOR[name](event)
        if row is not None:
            rows.append((event, row))
    return rows


def _manifest(events: list[TrainingEvent], body: str) -> dict:
    versions = sorted({event.policy_version for event in events})
    if len(versions) == 1:
        policy_version: str | None = versions[0]
    elif not versions:
        policy_version = None
    else:
        policy_version = ",".join(versions)
    return {
        "schema_version": SCHEMA_VERSION,
        "event_count": len(events),
        "policy_version": policy_version,
        "hash": hashlib.sha256(body.encode("utf-8")).hexdigest(),
    }


def _dumps(row: dict) -> str:
    return json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"


def s1_row(event: TrainingEvent) -> dict:
    return {
        "text": render_call(event.input_ref),
        "label": event.output_correct.value,
        "group_id": event.group_id,
        "weight": event.weight,
    }


def s2_row(event: TrainingEvent) -> dict:
    action = event.output_correct.value
    return {
        "messages": [
            {"role": "system", "content": policy_text(event) or _NO_POLICY},
            {"role": "user", "content": render_call(event.input_ref)},
            {"role": "assistant", "content": f"{action}\n{event.reason.strip()}"},
        ]
    }


def sapling_row(event: TrainingEvent) -> dict:
    """policy, evidence, and claim. The log has no separate claim, so claim is the reason."""

    return {
        "policy": policy_text(event) or _NO_POLICY,
        "evidence": render_call(event.input_ref),
        "claim": event.reason.strip(),
        "verdict": event.output_correct.value,
    }


def prefs_row(event: TrainingEvent) -> dict | None:
    """A pair only when the model label and the correct label differ."""

    if event.output_model is None:
        return None
    chosen = event.output_correct.value
    rejected = event.output_model.value
    if chosen == rejected:
        return None
    return {
        "prompt": prompt_text(event),
        "chosen": chosen,
        "rejected": rejected,
    }


_ROW_FOR = {
    "s1": s1_row,
    "s2": s2_row,
    "sapling": sapling_row,
    "prefs": prefs_row,
}

_NO_POLICY = "No policy ids were named on this event."


def prompt_text(event: TrainingEvent) -> str:
    call = render_call(event.input_ref)
    policy = policy_text(event)
    if policy:
        return f"{policy}\n\n{call}"
    return call


def render_call(ref: InputRef) -> str:
    """Transcript lines for a fixture case. Otherwise a stable rendering of the ref."""

    turns = _fixture_turns(ref.case_id)
    if turns is not None:
        selected = _select_turns(turns, ref.turn_ids)
        if selected:
            return "\n".join(f"{turn['speaker']}: {turn['text']}" for turn in selected)
    return _fallback_call(ref)


def _fixture_turns(case_id: str) -> list[dict] | None:
    try:
        payload = load_fixture(case_id)
    except KeyError:
        return None
    stream = payload.get("transcript_stream")
    if isinstance(stream, list) and stream:
        return stream
    transcript = (payload.get("case_state") or {}).get("transcript")
    if isinstance(transcript, list):
        return transcript
    return None


def _select_turns(turns: list[dict], turn_ids: list[str]) -> list[dict]:
    if not turn_ids:
        return list(turns)
    chosen: list[dict] = []
    seen: set[int] = set()
    for token in turn_ids:
        match = _match_turn(turns, token)
        if match is None or match in seen:
            continue
        seen.add(match)
        chosen.append(turns[match])
    return chosen


def _match_turn(turns: list[dict], token: str) -> int | None:
    if token.isdigit():
        index = int(token)
        if 0 <= index < len(turns):
            return index
    for index, turn in enumerate(turns):
        if str(turn.get("t_ms")) == token:
            return index
    return None


def _fallback_call(ref: InputRef) -> str:
    lines = [f"case_id: {ref.case_id}", f"lang: {ref.lang}"]
    if ref.turn_ids:
        lines.append("turn_ids: " + ",".join(ref.turn_ids))
    if ref.memory_ref:
        lines.append(f"memory_ref: {ref.memory_ref}")
    return "\n".join(lines)


def policy_text(event: TrainingEvent) -> str:
    """Corpus text for the event's policy ids at its policy_version.

    A missing pin or an unknown id is named. The text is not invented.
    """

    ids: list[str] = []
    seen: set[str] = set()
    for rule_id in event.input_ref.policy_ids:
        if rule_id and rule_id not in seen:
            seen.add(rule_id)
            ids.append(rule_id)
    if not ids:
        return ""
    service = get_service()
    blocks: list[str] = []
    for rule_id in ids:
        try:
            rule = service.require_rule(rule_id, version=event.policy_version)
        except PolicyError:
            blocks.append(
                f"[{rule_id}]\n"
                f"Policy text is not available for corpus version {event.policy_version}."
            )
            continue
        blocks.append(_rule_block(rule, event.input_ref.lang))
    return "\n\n".join(blocks)


def _rule_block(rule, lang: str) -> str:
    english = rule.languages["en"].text.strip()
    thai = rule.languages["th"].text.strip()
    if lang == "th":
        body = thai or english
    elif lang == "mixed":
        body = "\n".join(part for part in (english, thai) if part)
    else:
        body = english or thai
    if not body:
        body = "This rule has no text in the corpus."
    return f"[{rule.rule_id}]\n{body}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export training datasets from the event log.")
    parser.add_argument(
        "--events",
        default="",
        help="JSONL file or directory. Default is the event log.",
    )
    parser.add_argument("--out", default="training/out")
    args = parser.parse_args(argv)
    if args.events:
        source = Path(args.events)
        allow_missing = False
    else:
        source = default_source()
        allow_missing = True
    try:
        written = export_datasets(source, Path(args.out), allow_missing=allow_missing)
    except ExportError as exc:
        raise SystemExit(str(exc)) from None
    for name in EXPORT_NAMES:
        manifest = written[name]
        print(f"{name} {manifest['event_count']} {manifest['hash']}")


if __name__ == "__main__":
    main()
