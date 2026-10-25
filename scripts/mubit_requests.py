"""List the last N Mubit chat hops that carry a request id. `make mubit-requests`.

Reads the `TRACE_PATH` JSONL (default `traces.jsonl`), keeps `mubit_chat`
rows whose notes carry `request_id=mreq_<32 hex>`, and prints them newest
first: time, case_id, request_id, host, status, latency_ms, outcome.

`outcome` is the deciding system's outcome for that case from the same
trace file. The `router` TraceEvent that `gateway/route.py` emits carries
no `next_action` (its notes are `router.merge ran on the selected
outcome(s)` and `outcome` is None), so the column shows the `system_2`
stage outcome (`<route> <priority>`), falling back to `system_1`, and marks
whether a router event exists for the case (`routed`). A cache replay is
shown with status `cache_hit` and `(recorded)` after the request id.

Only parsed fields are printed, never a raw note, a header, or anything
that looks like a key.

    make mubit-requests N=20
    python scripts/mubit_requests.py --n 20 --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trace import read_traces, trace_path  # noqa: E402

REQUEST_ID = re.compile(r"request_id=(mreq_[0-9a-f]{32})( \(recorded\))?")
HOST = re.compile(r"host=([A-Za-z0-9._/\-]+)")
STATUS = re.compile(r"status=([A-Za-z0-9_]+)")
COLUMNS = ("time", "case_id", "request_id", "host", "status", "latency_ms", "routed", "outcome")


def _first(pattern: re.Pattern, text: str) -> str | None:
    match = pattern.search(text)
    return match.group(1) if match else None


def hops(events: list, limit: int) -> list[dict]:
    """Newest-first `mubit_chat` rows with a Mubit request id, at most `limit`."""

    outcomes: dict[str, dict] = {}
    routed: set[str] = set()
    for event in events:
        if event.stage == "router":
            routed.add(event.case_id)
        elif event.stage in ("system_2", "system_1") and event.outcome is not None:
            previous = outcomes.get(event.case_id)
            # System 2 is the deciding system on a cascade; keep it over System 1.
            if previous is None or event.stage == "system_2" or previous["system"] == "system_1":
                outcomes[event.case_id] = {
                    "system": event.stage,
                    "route": event.outcome.route.value,
                    "priority": event.outcome.priority.value,
                    "outcome": event.outcome.outcome,
                }
    rows: list[dict] = []
    for event in events:
        if event.stage != "mubit_chat":
            continue
        note = event.notes or ""
        match = REQUEST_ID.search(note)
        if not match:
            continue
        decided = outcomes.get(event.case_id)
        rows.append(
            {
                "time": event.started_at.isoformat(),
                "case_id": event.case_id,
                "request_id": match.group(1),
                "recorded": bool(match.group(2)),
                "host": _first(HOST, note) or "?",
                "status": _first(STATUS, note) or "?",
                "latency_ms": int(event.latency_ms),
                "model": event.model,
                "routed": event.case_id in routed,
                "outcome_system": decided["system"] if decided else None,
                "outcome": f"{decided['route']} {decided['priority']}" if decided else None,
            }
        )
    rows.sort(key=lambda row: row["time"], reverse=True)
    return rows[: max(0, limit)]


def render(rows: list[dict]) -> str:
    if not rows:
        return "no mubit_chat rows with a request_id"
    cells = []
    for row in rows:
        cells.append(
            (
                row["time"][:19].replace("T", " "),
                row["case_id"],
                row["request_id"] + (" (recorded)" if row["recorded"] else ""),
                row["host"],
                row["status"],
                str(row["latency_ms"]),
                "yes" if row["routed"] else "no",
                (row["outcome"] or "—") + (f" ({row['outcome_system']})" if row["outcome_system"] == "system_1" else ""),
            )
        )
    widths = [max(len(COLUMNS[i]), *(len(c[i]) for c in cells)) for i in range(len(COLUMNS))]
    line = lambda parts: "  ".join(part.ljust(widths[i]) for i, part in enumerate(parts)).rstrip()  # noqa: E731
    out = [line(COLUMNS), line(tuple("-" * w for w in widths))]
    out.extend(line(c) for c in cells)
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--n", type=int, default=20, help="how many hops, newest first (default 20)")
    parser.add_argument("--path", default=None, help="trace file (default TRACE_PATH / traces.jsonl)")
    parser.add_argument("--json", dest="as_json", action="store_true", help="print JSON instead of a table")
    args = parser.parse_args(argv)
    path = Path(args.path) if args.path else trace_path()
    if not path.is_file():
        print(f"no trace file at {path.name} (set TRACE_PATH)", file=sys.stderr)
        return 0
    try:
        events = read_traces(path=path)
    except Exception as exc:  # noqa: BLE001 - a bad line is reported by type only
        print(f"could not read {path.name}: {type(exc).__name__}", file=sys.stderr)
        return 1
    rows = hops(events, args.n)
    if args.as_json:
        print(json.dumps({"trace_path": path.name, "count": len(rows), "hops": rows}, indent=2))
    else:
        print(render(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
