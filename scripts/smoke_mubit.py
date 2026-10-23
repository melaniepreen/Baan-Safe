"""One trivial Mubit request. Prints status and latency only, never the key.

Skipped unless both MUBIT_API_KEY and MUBIT_BASE_URL are set.
"""

from __future__ import annotations

import os
import time

import httpx


def main() -> int:
    key = os.environ.get("MUBIT_API_KEY", "").strip()
    base = os.environ.get("MUBIT_BASE_URL", "").strip()
    if not key or not base:
        print("skipped: MUBIT_API_KEY or MUBIT_BASE_URL unset")
        return 0
    started = time.perf_counter()
    try:
        response = httpx.get(
            base,
            headers={"Authorization": f"Bearer {key}", "Accept": "application/json"},
            timeout=15.0,
            follow_redirects=False,
        )
    except httpx.HTTPError:
        latency_ms = int((time.perf_counter() - started) * 1000)
        print(f"status=error latency_ms={latency_ms}")
        return 1
    latency_ms = int((time.perf_counter() - started) * 1000)
    print(f"status={response.status_code} latency_ms={latency_ms}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
