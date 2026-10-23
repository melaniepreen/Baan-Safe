"""Hit every API endpoint once. The server must already be running on :8000."""

from __future__ import annotations

import json
import sys

import httpx

from fixtures.load import load_case


def main() -> int:
    base = "http://127.0.0.1:8000"
    client = httpx.Client(base_url=base, timeout=30.0)
    checks = []

    def check(name: str, response: httpx.Response) -> None:
        ok = response.status_code < 400
        checks.append((name, response.status_code, ok))
        print(f"{name}: {response.status_code}")

    check("health", client.get("/health"))
    check("fixtures", client.get("/fixtures"))
    check("fixture", client.get("/fixtures/F01"))
    check("stream", client.get("/fixtures/F01/stream", params={"pace": 0}))
    check("create", client.post("/cases", json={"fixture_id": "F06"}))
    check(
        "turn",
        client.post(
            "/cases/F06/turns",
            json={"t_ms": 90000, "speaker": "operator", "text": "Noted. Five people, shelter this afternoon."},
        ),
    )
    check("case", client.get("/cases/F06"))
    case = json.loads(load_case("F01").model_dump_json())
    check("triage", client.post("/triage", json=case))
    check("create-a", client.post("/cases", json={"fixture_id": "C01-a"}))
    check(
        "correction",
        client.post(
            "/cases/C01-a/corrections",
            json={
                "corrected_by": "supervisor",
                "field": "priority",
                "old_value": "P3",
                "new_value": "P1",
                "reason": "smoke correction for the paired case",
            },
        ),
    )
    check("trace", client.get("/cases/C01-a/trace"))
    check("create-b", client.post("/cases", json={"fixture_id": "C01-b"}))
    paired = client.get("/cases/C01-b")
    check("paired", paired)
    summaries = " ".join(item["summary"] for item in paired.json()["case"]["memory_context"])
    if "smoke correction" not in summaries:
        print("paired memory did not show the new correction")
        return 1
    check("context-district", client.get("/context", params={"district": "Mae Mo District"}))
    check("context-point", client.get("/context", params={"lat": 18.4, "lon": 99.8}))
    check("resources", client.get("/resources"))
    check("flood", client.get("/map/flood"))
    check("facilities", client.get("/map/facilities"))
    check("replay", client.post("/replay", json={"fixture_ids": ["F01", "F10"]}))
    check("metrics", client.get("/metrics"))
    check("docs", client.get("/docs"))
    check("openapi", client.get("/openapi.json"))
    check("player", client.get("/ui/player.html"))
    failed = [name for name, _status, ok in checks if not ok]
    if failed:
        print("failed:", ", ".join(failed))
        return 1
    print(f"smoke ok: {len(checks)} endpoints")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
