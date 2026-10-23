"""Play a fixture transcript. Speech-to-text provider is TODO_HUMAN.

Run: python -m ui.transcript_player F01 --pace 0
"""

from __future__ import annotations

import argparse
import time

from fixtures.load import load_fixture


def play(fixture_id: str, pace: float = 1.0, emit=print) -> None:
    payload = load_fixture(fixture_id)
    previous = 0
    for turn in payload["transcript_stream"]:
        delta_ms = turn["t_ms"] - previous
        previous = turn["t_ms"]
        if pace and delta_ms > 0:
            time.sleep(delta_ms / 1000 * pace)
        emit(f"[{turn['t_ms']:>6} ms] {turn['speaker']}: {turn['text']}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Play a synthetic fixture transcript")
    parser.add_argument("fixture_id")
    parser.add_argument("--pace", type=float, default=1.0, help="1 is real time, 0 emits immediately")
    args = parser.parse_args()
    play(args.fixture_id, pace=args.pace)


if __name__ == "__main__":
    main()
