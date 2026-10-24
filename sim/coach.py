"""CSD-style coach. Notes only.

Compares the hidden persona and the private traces with the stub operator
lines. Writes JSONL tagged source=coach, and appends TrainingEvent rows
through training/log.py. Coach rows use source=coach. The simulator outcome
uses source=sim. Neither is a human correction, and neither is promoted.

The paper's token-level coached self-distillation is future work and is not
implemented here. Event types come from contracts.training and are not
redefined here.
"""

from __future__ import annotations

import json
from pathlib import Path

from contracts.training import InputRef, S1Label, S2Action, TrainingEvent, current_policy_version
from sim.callers.persona import CallerSpec
from sim.env import Episode
from training.log import AppendResult, append_event

SOURCE = "coach"


def notes_for(episode: Episode) -> list[dict]:
    """Short notes. The note text does not repeat the hidden district."""
    operator = [turn.operator_text for turn in episode.turns]
    blob = " ".join(operator).lower()
    ask_at = next((index for index, text in enumerate(operator) if "district" in text.lower()), None)
    found: list[dict] = []
    if ask_at is None:
        found.append({"note": "never asked for location", "turn_index": None})
    elif ask_at >= 2:
        found.append({"note": "asked for location too late", "turn_index": ask_at})
    hidden_people = episode.spec.persona.vulnerable
    if hidden_people and not any(tag.lower() in blob for tag in hidden_people):
        found.append({"note": "missed a vulnerable household member", "turn_index": None})
    withheld = any("saying it is milder" in turn.caller.private_trace for turn in episode.turns)
    if withheld and "how urgent" not in blob and "unable to leave" not in blob:
        found.append({"note": "accepted an under-reported severity", "turn_index": None})
    return found


def rows_for(episode: Episode) -> list[dict]:
    traits = list(episode.spec.traits)
    return [
        {
            "source": SOURCE,
            "promoted": False,
            "case_id": episode.spec.combo_id,
            "note": item["note"],
            "traits": traits,
            "turn_index": item["turn_index"],
        }
        for item in notes_for(episode)
    ]


def _lang(spec: CallerSpec) -> str:
    if "code_switches" in spec.traits:
        return "mixed"
    return "en"


def hidden_label(spec: CallerSpec) -> S1Label:
    """Closed s1 label for the hidden need. Priorities are not labels."""
    needs = spec.persona.true_needs
    if "rescue" in needs:
        return S1Label.flood_trapped
    if "water" in needs:
        return S1Label.sphere_water_short
    if "shelter" in needs:
        return S1Label.sphere_shelter_crowded
    if "food" in needs:
        return S1Label.sphere_food_short
    return S1Label.niems_white_general


def _ref(spec: CallerSpec, turn_ids: list[str]) -> InputRef:
    return InputRef(
        case_id=f"SIM-{spec.combo_id}",
        turn_ids=turn_ids,
        lang=_lang(spec),
        policy_ids=[],
        memory_ref=None,
    )


def _safeguarding(tag: str) -> S1Label:
    if tag == "infant":
        return S1Label.safeguarding_child
    if "older" in tag:
        return S1Label.safeguarding_older_person
    return S1Label.safeguarding_protection_referral


def events_for(episode: Episode, policy_version: str) -> list[TrainingEvent]:
    """One sim outcome, plus one coach event per note.

    input_ref differs per event so the content hash does not drop a note.
    corrected_by stays unset. These sources are not human.
    """
    spec = episode.spec
    group_id = spec.combo_id
    events = [
        TrainingEvent(
            task="s1_triage",
            group_id=group_id,
            input_ref=_ref(spec, [str(turn.index) for turn in episode.turns]),
            output_model=None,
            output_correct=hidden_label(spec),
            reason=f"Scripted caller outcome. Traits: {', '.join(spec.traits)}.",
            source="sim",
            model_version="s1@stub-sim",
            policy_version=policy_version,
        )
    ]
    for item in notes_for(episode):
        note = item["note"]
        turn = item["turn_index"]
        if note in ("asked for location too late", "never asked for location"):
            events.append(
                TrainingEvent(
                    task="s2_action",
                    group_id=group_id,
                    input_ref=_ref(spec, [f"location:{turn if turn is not None else 'none'}"]),
                    output_model=None,
                    output_correct=S2Action.ask_next_question,
                    reason=note,
                    source="coach",
                    model_version="s2@stub-sim",
                    policy_version=policy_version,
                )
            )
            continue
        if note == "missed a vulnerable household member":
            for tag in spec.persona.vulnerable:
                events.append(
                    TrainingEvent(
                        task="s1_triage",
                        group_id=group_id,
                        input_ref=_ref(spec, [f"vulnerable:{tag}"]),
                        output_model=None,
                        output_correct=_safeguarding(tag),
                        reason=note,
                        source="coach",
                        model_version="s1@stub-sim",
                        policy_version=policy_version,
                    )
                )
            continue
        if note == "accepted an under-reported severity":
            events.append(
                TrainingEvent(
                    task="s1_triage",
                    group_id=group_id,
                    input_ref=_ref(spec, ["severity"]),
                    output_model=None,
                    output_correct=hidden_label(spec),
                    reason=note,
                    source="coach",
                    model_version="s1@stub-sim",
                    policy_version=policy_version,
                )
            )
            continue
        events.append(
            TrainingEvent(
                task="s2_action",
                group_id=group_id,
                input_ref=_ref(spec, [f"note:{note}"]),
                output_model=None,
                output_correct=S2Action.request_more_evidence,
                reason=note,
                source="coach",
                model_version="s2@stub-sim",
                policy_version=policy_version,
            )
        )
    return events


def log_training(episodes: list[Episode] | tuple[Episode, ...]) -> list[AppendResult]:
    """Append coach and sim events. A repeated content_hash is not written again."""
    policy_version = current_policy_version()
    results: list[AppendResult] = []
    for episode in episodes:
        for event in events_for(episode, policy_version):
            if event.source == "human" or event.corrected_by is not None:
                raise RuntimeError("coach and sim events are not human corrections")
            results.append(append_event(event))
    return results


def write_jsonl(episodes: list[Episode] | tuple[Episode, ...], path: Path) -> int:
    """Write coach JSONL, then the training log. Does not promote."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for episode in episodes:
            for row in rows_for(episode):
                if row["source"] != SOURCE or row["promoted"] is not False:
                    raise RuntimeError("coach rows stay source=coach and promoted false")
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                count += 1
    log_training(episodes)
    return count
