"""Send distinct System 2 calls through Mubit so its task keeps learning.

Mubit groups every System 2 call into one task (static system prompt) and
trains a per-task adapter once it holds enough *kept examples*. Repeating a
prompt does not add an example, so this driver builds new synthetic callers
by varying the location, household size, names, water depth and floor of the
existing synthetic transcripts, then runs each through ``gateway.route.handle``
with the real System 1 and System 2. Only calls that reach System 2 open a
Mubit hop; each hop carries ``metadata.session_id=<case_id>``.

Synthetic people only. Names come from a short invented list. No phone
numbers, ids or bank details are ever generated. Refuses to run without the
Mubit credentials and prints no secret.

    MEMORY_IMPL=mock S1_IMPL=real S2_IMPL=real \
      python scripts/mubit_traffic.py --count 200 --seed 3

``--dry-run`` writes the variants to stdout and opens no socket.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import random
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from fixtures.load import iter_synthetic  # noqa: E402

# Invented callers. Not real people.
NAMES = [
    "Malee Phueng", "Somchai Rattana", "Niran Boonmee", "Kanya Srisuk",
    "Prasert Wongsa", "Anong Chaiyo", "Wichai Thongdee", "Pim Saelim",
    "Dao Kittisak", "Nok Pramote", "Arthit Saengthong", "Ratree Inthanon",
]
LOCATIONS = [
    "Soi Sukhumvit 39, Watthana", "Soi Sukhumvit 49, Watthana",
    "Soi Sukhumvit 55, Watthana", "Soi Sukhumvit 40, Watthana",
    "Soi Sukhumvit 63, Watthana", "Thanon Sukhumvit near Soi 49, Watthana",
    "Thanon Phetchaburi Tat Mai, Watthana", "Thanon At Narong, Khlong Toei",
    "behind Khlong Saen Saep, Watthana", "Soi Thong Lo, Watthana",
    "Soi Ekkamai, Watthana", "Phrom Phong, Khlong Tan",
]
DEPTHS = ["ankle deep", "knee deep", "waist deep", "up to the table", "chest high"]
FLOORS = ["the ground floor", "the first floor", "the second floor", "the roof"]
COUNT_WORDS = {
    1: "There is just me.", 2: "There are two of us.", 3: "There are three of us.",
    4: "There are four of us.", 5: "There are five of us.", 6: "There are six of us.",
    7: "Seven people, two of them children.", 8: "Eight of us, including a baby.",
}

_LOC_RE = re.compile(r"We are in [^.]*\.")
_DISTRICT_RE = re.compile(r"[A-Z][A-Za-z]+(?: [A-Z][A-Za-z]+)* District, [A-Z][a-z]+(?:, near Placeholder Soi \d+)?")
_PLACEHOLDER_RE = re.compile(r"Placeholder Soi \d+")
_NAME_RE = re.compile(r"^[A-Z][a-z]+ [A-Z][a-z]+\.")
_COUNT_RE = re.compile(r"^(There (?:is|are) [^.]*\.|[A-Z][a-z]+ people[^.]*\.|[A-Z][a-z]+ of us[^.]*\.)$")
_DEPTH_RE = re.compile(r"(ankle|knee|waist|chest)[- ]?(deep|high)")
_FLOOR_RE = re.compile(r"the (ground|first|second|third) floor|the roof")


def _vary(text: str, rng: random.Random, name: str, loc: str, count: int) -> str:
    out = _NAME_RE.sub(f"{name}.", text, count=1)
    out = _LOC_RE.sub(f"We are in {loc}, near the flooded lane.", out, count=1)
    out = _DISTRICT_RE.sub(loc, out, count=1)
    out = _PLACEHOLDER_RE.sub(f"Soi {rng.randint(2, 71)}", out, count=1)
    if _COUNT_RE.match(out.strip()):
        out = COUNT_WORDS[count]
    out = _DEPTH_RE.sub(rng.choice(DEPTHS), out, count=1)
    out = _FLOOR_RE.sub(rng.choice(FLOORS), out, count=1)
    return out


def build_variants(count: int, seed: int, *, langs: tuple[str, ...] = ("en", "mixed")) -> list[dict]:
    rng = random.Random(seed)
    sources = [c for c in iter_synthetic() if c.get("lang") in langs]
    if not sources:
        raise SystemExit("no synthetic sources for the requested languages")
    variants: list[dict] = []
    for i in range(count):
        src = sources[i % len(sources)]
        name = rng.choice(NAMES)
        loc = rng.choice(LOCATIONS)
        people = rng.choice(list(COUNT_WORDS))
        turns = [
            {
                "t_ms": t["t_ms"],
                "speaker": t["speaker"],
                "text": _vary(t["text"], rng, name, loc, people) if t["speaker"] == "caller" else t["text"],
            }
            for t in src["transcript_stream"]
        ]
        variants.append(
            {
                "case_id": f"traffic-{seed}-{i:04d}",
                "source": src["id"],
                "primary_label": src.get("primary_label"),
                "transcript": turns,
            }
        )
    return variants


def _require_live() -> None:
    missing = [k for k in ("MUBIT_API_KEY", "MUBIT_BASE_URL") if not os.environ.get(k)]
    if missing:
        raise SystemExit(
            "mubit_traffic needs " + ", ".join(missing) + " (load .env). "
            "Use --dry-run to print variants without a socket."
        )
    if os.environ.get("S2_IMPL", "").lower() != "real":
        raise SystemExit("set S2_IMPL=real so System 2 opens a Mubit hop (S1_IMPL=real too).")


def _run_one(variant: dict) -> tuple[str, str | None, str | None]:
    from contracts.models import CaseState, ExtractedFields, TranscriptTurn
    from gateway.route import handle

    case = CaseState(
        case_id=variant["case_id"],
        caller_id_hash=f"synthetic:{variant['case_id']}",
        transcript=[TranscriptTurn(**t) for t in variant["transcript"]],
        fields=ExtractedFields(),
        memory_context=[],
        policy_flags=[],
        resources={},
        received_at=datetime.now(timezone.utc),
    )
    try:
        decision = handle(case, use_stubs=False)
        return variant["case_id"], str(decision.next_action.value), None
    except Exception as exc:  # noqa: BLE001 — report class only, keep going
        return variant["case_id"], None, type(exc).__name__


def _mubit_summary(trace_path: Path, prefix: str) -> dict:
    stats: collections.Counter[str] = collections.Counter()
    sessions: set[str] = set()
    if not trace_path.is_file():
        return {"mubit_chat": 0}
    for line in trace_path.read_text(encoding="utf-8").splitlines():
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("stage") != "mubit_chat" or not str(event.get("case_id", "")).startswith(prefix):
            continue
        stats["mubit_chat"] += 1
        sessions.add(str(event.get("case_id")))
        for tok in str(event.get("notes") or "").split():
            if tok.startswith("status="):
                stats[tok] += 1
    return {**stats, "distinct_sessions": len(sessions)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--langs", default="en,mixed")
    args = parser.parse_args(argv)

    variants = build_variants(args.count, args.seed, langs=tuple(args.langs.split(",")))
    if args.dry_run:
        for v in variants:
            print(json.dumps(v, ensure_ascii=False))
        print(f"dry-run: {len(variants)} variants, no socket", file=sys.stderr)
        return 0

    _require_live()
    started = time.time()
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        results = list(pool.map(_run_one, variants))
    actions = collections.Counter(r[1] for r in results if r[1])
    errors = collections.Counter(r[2] for r in results if r[2])
    trace_path = Path(os.environ.get("TRACE_PATH", "traces.jsonl"))
    summary = {
        "sent": len(results),
        "seconds": round(time.time() - started),
        "next_action": dict(actions),
        "errors": dict(errors),
        "mubit": _mubit_summary(trace_path, f"traffic-{args.seed}-"),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
