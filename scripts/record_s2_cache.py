"""Record `fixtures/s2_cache/demo.jsonl` for `S2_IMPL=cache`.

Runs every fixture case (and the synthetic set) through the gateway with
System 2 in cache mode and a record path, so each turn that reaches Nemotron
is answered once by Mubit and stored under its exact key. Re-running only
fills misses. Needs `.env` (MUBIT_API_KEY, MUBIT_BASE_URL).

    S1_IMPL=real S2_IMPL=cache MEMORY_IMPL=mock \
      S2_CACHE_RECORD_PATH=fixtures/s2_cache/demo.jsonl \
      python scripts/record_s2_cache.py [--synthetic] [--ids F10,F12]

The hosted gateway records its own misses on the volume
(`S2_CACHE_RECORD_PATH=/data/s2_cache.jsonl`); run the demo script once there
before the live demo so every scripted turn is a hit.
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from config.envfile import load_env_file  # noqa: E402

load_env_file()

from contracts.models import CaseState  # noqa: E402
from fixtures.load import all_ids, load_case, load_synthetic, synthetic_ids  # noqa: E402


def _case(case_id: str) -> CaseState:
    try:
        return load_case(case_id)
    except KeyError:
        return CaseState.model_validate(load_synthetic(case_id)["case_state"])


def _require() -> None:
    missing = [k for k in ("MUBIT_API_KEY", "MUBIT_BASE_URL") if not os.environ.get(k)]
    if missing:
        raise SystemExit("record_s2_cache needs " + ", ".join(missing) + " (load .env).")
    if os.environ.get("S2_IMPL", "").lower() != "cache":
        raise SystemExit("set S2_IMPL=cache")
    if not os.environ.get("S2_CACHE_RECORD_PATH", "").strip():
        raise SystemExit("set S2_CACHE_RECORD_PATH (e.g. fixtures/s2_cache/demo.jsonl)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--synthetic", action="store_true", help="include fixtures/synthetic")
    parser.add_argument("--ids", default="", help="comma-separated case ids only")
    args = parser.parse_args(argv)
    _require()

    from gateway.route import handle
    from system2 import cache

    if args.ids:
        ids = [i.strip() for i in args.ids.split(",") if i.strip()]
    else:
        ids = list(all_ids()) + (list(synthetic_ids()) if args.synthetic else [])
    before = cache.size()
    actions: collections.Counter[str] = collections.Counter()
    errors: collections.Counter[str] = collections.Counter()
    for case_id in ids:
        try:
            decision = handle(_case(case_id), use_stubs=False)
            actions[str(decision.next_action.value)] += 1
        except Exception as exc:  # noqa: BLE001 — report the class, keep going
            errors[type(exc).__name__] += 1
    cache._loaded.clear()
    print(
        json.dumps(
            {
                "cases": len(ids),
                "cache_before": before,
                "cache_after": cache.size(),
                "record_path": str(cache.record_path()),
                "next_action": dict(actions),
                "errors": dict(errors),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
