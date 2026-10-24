"""CSD-style coach. Notes only.

Compares the hidden persona and the private traces with the stub operator
lines. Writes JSONL tagged source=coach. Rows are not human corrections and
are not promoted.

The paper's token-level coached self-distillation is future work and is not
implemented here.
"""

from __future__ import annotations

import json
from pathlib import Path

from sim.env import Episode

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


def write_jsonl(episodes: list[Episode] | tuple[Episode, ...], path: Path) -> int:
    """Write coach rows. Does not write a Correction and does not promote."""
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8") as handle:
        for episode in episodes:
            for row in rows_for(episode):
                if row["source"] != SOURCE or row["promoted"] is not False:
                    raise RuntimeError("coach rows stay source=coach and promoted false")
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                count += 1
    return count
