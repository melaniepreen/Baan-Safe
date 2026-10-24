"""Laya JSONL for ``laya-train`` 0.4.14.

Each row is ``{state, questions, expected}``. ``state`` is ``{"body": text}``
because the question instructions name the field ``body`` (the preset
convention). ``priority`` is one ``choice`` over the five NIEMS colours.
Each other System 1 label is a ``noul`` question with a boolean gold answer.
The same questions are asked on every row so train and held-out match.

``laya-train --data <train> --eval <held> --base convaiinnovations/laya-multilingual --out <ckpt>``
reads this file with no column flags. CSV ``--text-column body`` is a
different path and is not what this export writes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fixtures.synthetic_gold import COLOUR_TO_LABEL, NOUL_LABELS
from training.synthetic_export import call_text, split_calls

COLOUR_CRITERIA = {
    "red": "Life-threatening emergency that must be handled immediately.",
    "yellow": "Urgent emergency, handled after a life-threatening case.",
    "green": "Emergency that is not severe, handled after urgent cases.",
    "white": "General patient who can go elsewhere or after the emergency cases.",
    "black": "No patient. Another public-health request for another time or place.",
}

NOUL_INSTRUCTIONS = {
    "niems_not_conscious_or_breathing": "Is someone in `body` not conscious or not breathing normally?",
    "sphere_water_short": "Does `body` say the household is short of drinking water?",
    "sphere_food_short": "Does `body` say the household is short of food?",
    "sphere_shelter_crowded": "Does `body` say the shelter is crowded or short of living space?",
    "safeguarding_child": "Does `body` involve a child who needs a person to decide?",
    "safeguarding_older_person": "Does `body` involve an older person who needs an individual assessment?",
    "safeguarding_disability": "Does `body` involve a person with a disability who needs an individual assessment?",
    "safeguarding_serious_health": "Does `body` describe a serious health condition a person must decide?",
    "safeguarding_protection_referral": "Does `body` need a protection referral to a person?",
    "flood_water_depth": "Does `body` describe how deep the flood water is?",
    "flood_trapped": "Does `body` say someone is trapped by flood water and cannot leave?",
}


def questions() -> dict:
    block = {
        "priority": {
            "type": "choice",
            "instructions": "Which NIEMS colour fits the flood call in `body`?",
            "criteria": dict(COLOUR_CRITERIA),
        }
    }
    for label in NOUL_LABELS:
        block[label] = {"type": "noul", "instructions": NOUL_INSTRUCTIONS[label]}
    return block


def laya_row(call: dict, asked: dict | None = None) -> dict:
    positive = set(call["labels"])
    colour = call["colour"]
    if COLOUR_TO_LABEL[colour] not in positive:
        raise ValueError(f"{call['id']} colour {colour} is not a positive label")
    expected = {"priority": colour}
    for label in NOUL_LABELS:
        expected[label] = label in positive
    return {
        "state": {"body": call_text(call)},
        "questions": asked if asked is not None else questions(),
        "expected": expected,
        "language": call["lang"],
        "tags": [f"group:{call['group_id']}", call["primary_label"]],
    }


def write_laya(out_dir: Path) -> dict:
    train, held = split_calls()
    asked = questions()
    out_dir.mkdir(parents=True, exist_ok=True)
    train_rows = [laya_row(call, asked) for call in train]
    held_rows = [laya_row(call, asked) for call in held]
    _write(out_dir / "train.jsonl", train_rows)
    _write(out_dir / "held.jsonl", held_rows)
    return {
        "train": len(train_rows),
        "held_out": len(held_rows),
        "questions": 1 + len(NOUL_LABELS),
        "train_positives": _positives(train_rows),
        "held_out_positives": _positives(held_rows),
    }


def _positives(rows: list[dict]) -> dict[str, int]:
    counts = {colour: 0 for colour in COLOUR_CRITERIA}
    for label in NOUL_LABELS:
        counts[label] = 0
    for row in rows:
        expected = row["expected"]
        counts[expected["priority"]] += 1
        for label in NOUL_LABELS:
            if expected[label] is True:
                counts[label] += 1
    return counts


def _write(path: Path, rows: list[dict]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export Laya train and held-out JSONL.")
    parser.add_argument("--out", default="training/out/laya")
    args = parser.parse_args(argv)
    counts = write_laya(Path(args.out))
    print(
        f"laya train {counts['train']} held_out {counts['held_out']} "
        f"questions {counts['questions']}"
    )
    print("train positives " + json.dumps(counts["train_positives"], sort_keys=True))
    print("held positives " + json.dumps(counts["held_out_positives"], sort_keys=True))


if __name__ == "__main__":
    main()
