"""SetFit rows from fixtures/synthetic. The event log export is unchanged.

One row per call: ``{text, label, group_id, weight}``. ``label`` is the
primary label. The held-out file uses the same group_id split as Laya.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from fixtures.load import iter_synthetic, synthetic_split


def call_text(call: dict) -> str:
    return "\n".join(
        f"{turn['speaker']}: {turn['text']}" for turn in call["transcript_stream"]
    )


def setfit_row(call: dict) -> dict:
    return {
        "text": call_text(call),
        "label": call["primary_label"],
        "group_id": call["group_id"],
        "weight": 1.0,
    }


def split_calls(calls: list[dict] | None = None) -> tuple[list[dict], list[dict]]:
    rows = calls if calls is not None else iter_synthetic()
    held_ids = set(synthetic_split()["held_out_groups"])
    train = [call for call in rows if call["group_id"] not in held_ids]
    held = [call for call in rows if call["group_id"] in held_ids]
    train.sort(key=lambda call: call["id"])
    held.sort(key=lambda call: call["id"])
    return train, held


def write_setfit(out_dir: Path, calls: list[dict] | None = None) -> dict[str, int]:
    train, held = split_calls(calls)
    out_dir.mkdir(parents=True, exist_ok=True)
    _write(out_dir / "s1_synthetic.jsonl", [setfit_row(call) for call in train])
    _write(out_dir / "s1_synthetic_heldout.jsonl", [setfit_row(call) for call in held])
    return {"train": len(train), "held_out": len(held)}


def _write(path: Path, rows: list[dict]) -> None:
    body = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows
    )
    path.write_text(body, encoding="utf-8")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Export synthetic SetFit rows.")
    parser.add_argument("--out", default="training/out")
    args = parser.parse_args(argv)
    counts = write_setfit(Path(args.out))
    print(f"s1_synthetic train {counts['train']} held_out {counts['held_out']}")


if __name__ == "__main__":
    main()
