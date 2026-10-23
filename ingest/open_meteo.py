"""Open-Meteo daily observations for flood-affected district centroids.

Capped at 50 districts. See config/ingest.yaml for the robots.txt exception.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from config.settings import load_yaml
from ingest.common import OffHostError, PoliteClient, RobotsDisallowed
from ingest.db import connect, set_status

FORECAST_HOST = "api.open-meteo.com"
ARCHIVE_HOST = "archive-api.open-meteo.com"
DAILY = "precipitation_sum,temperature_2m_mean,wind_speed_10m_max"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _bangkok_today():
    return datetime.now(ZoneInfo("Asia/Bangkok")).date()


def ingest(refresh: bool) -> str:
    cfg = load_yaml("ingest.yaml")
    allowed = bool(cfg.get("open_meteo_documented_api_despite_robots_disallow"))
    if not allowed:
        detail = (
            "BLOCKED: config/ingest.yaml sets "
            "open_meteo_documented_api_despite_robots_disallow to false, and "
            "api.open-meteo.com robots.txt is Disallow: /."
        )
        set_status("open_meteo", fetched_at=_now(), row_count=0, status="blocked", detail=detail)
        return detail

    with connect() as conn:
        districts = conn.execute(
            "SELECT location_id, name_en, lat, lon FROM districts ORDER BY location_id"
        ).fetchall()
    districts = list(districts)[:50]
    if not districts:
        detail = "SKIPPED: no district centroids to query. GISTDA polygons or the admin lookup produced none."
        set_status("open_meteo", fetched_at=_now(), row_count=0, status="skipped", detail=detail)
        return detail

    client = PoliteClient("open-meteo", refresh=refresh, timeout=40)
    today = _bangkok_today()
    archive_end = today - timedelta(days=1)
    archive_start = archive_end - timedelta(days=29)
    stored = 0
    errors: list[str] = []
    for district in districts:
        stored += _one(
            client,
            location_id=district["location_id"],
            lat=district["lat"],
            lon=district["lon"],
            start=archive_start.isoformat(),
            end=archive_end.isoformat(),
            kind="archive",
            errors=errors,
        )
        stored += _one(
            client,
            location_id=district["location_id"],
            lat=district["lat"],
            lon=district["lon"],
            start=None,
            end=None,
            kind="forecast",
            errors=errors,
        )
    detail = (
        f"Daily rows={stored} for {len(districts)} locations. "
        f"Archive {archive_start.isoformat()} to {archive_end.isoformat()}, "
        "forecast 7 days. Granularity is daily (config/ingest.yaml). "
        "robots.txt on the API hosts is Disallow: /; calls were made because "
        "open_meteo_documented_api_despite_robots_disallow is true."
    )
    if errors:
        detail += " Errors: " + "; ".join(errors[:8])
    set_status(
        "open_meteo",
        fetched_at=_now(),
        row_count=stored,
        status="ok" if stored else "empty",
        detail=detail,
    )
    return detail


def _one(
    client: PoliteClient,
    *,
    location_id: str,
    lat: float,
    lon: float,
    start: str | None,
    end: str | None,
    kind: str,
    errors: list[str],
) -> int:
    if kind == "archive":
        url = "https://archive-api.open-meteo.com/v1/archive"
        host = ARCHIVE_HOST
        params = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start,
            "end_date": end,
            "daily": DAILY,
            "timezone": "Asia/Bangkok",
            "wind_speed_unit": "kmh",
        }
        source = "open-meteo-archive"
    else:
        url = "https://api.open-meteo.com/v1/forecast"
        host = FORECAST_HOST
        params = {
            "latitude": lat,
            "longitude": lon,
            "daily": DAILY,
            "forecast_days": 7,
            "timezone": "Asia/Bangkok",
            "wind_speed_unit": "kmh",
        }
        source = "open-meteo-forecast"
    try:
        result = client.get_json(
            url,
            allowed_hosts={host},
            params=params,
            ignore_robots=True,
        )
    except (RobotsDisallowed, OffHostError) as exc:
        errors.append(f"{location_id} {kind}: {exc}")
        return 0
    if result.status_code != 200:
        errors.append(f"{location_id} {kind}: HTTP {result.status_code}")
        return 0
    payload = json.loads(result.body)
    daily = payload.get("daily") or {}
    days = daily.get("time") or []
    rain = daily.get("precipitation_sum") or []
    temp = daily.get("temperature_2m_mean") or []
    wind = daily.get("wind_speed_10m_max") or []
    rows = 0
    with connect() as conn:
        for index, day in enumerate(days):
            conn.execute(
                """
                INSERT INTO weather_observation
                    (location_id, timestamp, rainfall_mm, temperature_c, wind_speed_kph, source)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    location_id,
                    day,
                    _at(rain, index),
                    _at(temp, index),
                    _at(wind, index),
                    source,
                ),
            )
            rows += 1
    return rows


def _at(values: list, index: int):
    if index >= len(values):
        return None
    return values[index]
