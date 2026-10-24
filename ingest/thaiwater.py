"""One public ThaiWater snapshot of river level and 24-hour rain.

api-v3.thaiwater.net/robots.txt is HTTP 404, which this client treats as no
crawl restriction. The paths are the portal's public JSON. They are not the
authenticated exchange API at standard.thaiwater.net. One snapshot is stored
as counts plus, where a gauge is near an ingested district, one rain row.
Station names are not written into SQLite.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from config.settings import load_yaml
from ingest.common import OffHostError, PoliteClient, RobotsDisallowed
from ingest.db import connect, set_status
from ingest.geo import haversine_km

HOST = "api-v3.thaiwater.net"
LEVEL_URL = "https://api-v3.thaiwater.net/api/v1/thaiwater30/public/waterlevel_load"
RAIN_URL = "https://api-v3.thaiwater.net/api/v1/thaiwater30/public/rain_24h"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ingest(refresh: bool) -> str:
    client = PoliteClient("thaiwater", refresh=refresh, timeout=90, attempts=3)
    try:
        level = client.get_json(LEVEL_URL, allowed_hosts={HOST})
        rain = client.get_json(RAIN_URL, allowed_hosts={HOST})
    except (RobotsDisallowed, OffHostError, RuntimeError) as exc:
        detail = f"BLOCKED: {exc}"
        set_status("thaiwater", fetched_at=_now(), row_count=0, status="blocked", detail=detail)
        return detail
    if level.status_code != 200 or rain.status_code != 200:
        detail = (
            f"BLOCKED: waterlevel HTTP {level.status_code}, rain HTTP {rain.status_code}. "
            "No station table was written."
        )
        set_status("thaiwater", fetched_at=_now(), row_count=0, status="blocked", detail=detail)
        return detail
    level_payload = json.loads(level.body)
    rain_payload = json.loads(rain.body)
    counts, legend = _level_counts(level_payload)
    gauges = _rain_gauges(rain_payload)
    attached = _attach_rain(gauges)
    parts = [f"level {code} ({legend.get(code, 'unlabelled')})={count}" for code, count in sorted(counts.items())]
    detail = (
        "Public portal snapshot, not the keyed ThaiWater exchange API. "
        f"Water-level stations={sum(counts.values())}: " + "; ".join(parts) + ". "
        f"Rain gauges={len(gauges)}. District rows given a gauge within the match "
        f"radius={attached}. Gauge names are not stored. "
        "Level 5 in this feed's own scale is น้ำล้นตลิ่ง (over bank); "
        "level 1 is น้ำน้อยวิกฤติ (critically low), not a flood class."
    )
    set_status(
        "thaiwater",
        fetched_at=rain.fetched_at,
        row_count=attached,
        status="ok",
        detail=detail,
    )
    return detail


def _level_counts(payload: dict) -> tuple[dict[str, int], dict[str, str]]:
    rows = ((payload.get("waterlevel_data") or {}).get("data")) or []
    counts: dict[str, int] = {}
    for row in rows:
        code = str(row.get("situation_level"))
        counts[code] = counts.get(code, 0) + 1
    legend: dict[str, str] = {}
    scale_data = ((payload.get("scale") or {}).get("data") or {})
    scale = scale_data.get("scale") or []
    # rule_web is the feed's own map from a percent-of-bank band to a level.
    rules = scale_data.get("rule_web") or []
    for band in scale:
        if not isinstance(band, dict):
            continue
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            if str(band.get("operator")) == str(rule.get("operator")) and str(
                band.get("term")
            ) == str(rule.get("term")):
                legend[str(rule.get("level"))] = str(band.get("situation") or "")
    if not legend:
        legend = {
            "5": "น้ำล้นตลิ่ง",
            "4": "น้ำมาก",
            "3": "น้ำปกติ",
            "2": "น้ำน้อย",
            "1": "น้ำน้อยวิกฤติ",
        }
    return counts, legend


def _rain_gauges(payload: dict) -> list[dict]:
    gauges = []
    for row in payload.get("data") or []:
        station = row.get("station") or {}
        lat = station.get("tele_station_lat")
        lon = station.get("tele_station_long")
        if lat is None or lon is None or row.get("rain_24h") is None:
            continue
        gauges.append(
            {
                "lat": float(lat),
                "lon": float(lon),
                "rain": float(row["rain_24h"]),
                "timestamp": str(row.get("rainfall_datetime") or "")[:16],
            }
        )
    return gauges


def _attach_rain(gauges: list[dict]) -> int:
    cfg = load_yaml("ingest.yaml")
    radius = float(cfg.get("thaiwater_match_km", 25))
    with connect() as conn:
        districts = conn.execute(
            "SELECT location_id, lat, lon FROM districts"
        ).fetchall()
        conn.execute(
            "DELETE FROM weather_observation WHERE source = 'thaiwater-rain-24h'"
        )
        stored = 0
        for district in districts:
            if district["lat"] is None or district["lon"] is None or not gauges:
                continue
            nearest = min(
                gauges,
                key=lambda gauge: haversine_km(
                    district["lat"], district["lon"], gauge["lat"], gauge["lon"]
                ),
            )
            distance = haversine_km(
                district["lat"], district["lon"], nearest["lat"], nearest["lon"]
            )
            if distance > radius:
                continue
            conn.execute(
                """
                INSERT INTO weather_observation
                    (location_id, timestamp, rainfall_mm, temperature_c, wind_speed_kph, source)
                VALUES (?, ?, ?, NULL, NULL, 'thaiwater-rain-24h')
                """,
                (district["location_id"], nearest["timestamp"], nearest["rain"]),
            )
            stored += 1
    return stored
