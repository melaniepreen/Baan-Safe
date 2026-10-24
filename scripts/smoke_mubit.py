"""One Mubit OpenAI-SDK call. Prints status and latency only, never the key.

Skipped unless both MUBIT_API_KEY and MUBIT_BASE_URL are set.
Uses the registered app client in llm/openai_client.py.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    # Load .env when present so local runs match make sync.
    try:
        from config.envfile import load_env_file

        load_env_file()
    except Exception:
        pass

    key = os.environ.get("MUBIT_API_KEY", "").strip()
    base = os.environ.get("MUBIT_BASE_URL", "").strip()
    if not key or not base:
        print("skipped: MUBIT_API_KEY or MUBIT_BASE_URL unset")
        return 0

    from llm.openai_client import make_client, registered_base_url

    started = time.perf_counter()
    try:
        client = make_client()
        models = client.models.list()
        count = len(list(models))
    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        print(f"status=error latency_ms={latency_ms} kind={type(exc).__name__}")
        return 1
    latency_ms = int((time.perf_counter() - started) * 1000)
    print(
        f"status=ok latency_ms={latency_ms} base={registered_base_url()} models={count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
