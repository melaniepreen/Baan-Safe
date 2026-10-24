"""Pure data lookup: district or coordinate → flood, rain, and nearby facilities."""

from __future__ import annotations

from shapely.geometry import Point

from ingest.db import DB_PATH, connect, db_exists
from ingest.geo import haversine_km, loads

EXTENT_1D = {"1d", "1", "1-day", "1day"}
EXTENT_3D = {"3d", "3", "3-day", "3day"}
EXTENT_7D = {"7d", "7", "7-day", "7day"}
EXTENT_30D = {"30d", "30", "30-day", "30day"}
HOSPITAL_TYPES = {"hospital", "clinic"}
SHELTER_TYPES = {"school", "place_of_worship", "community_centre"}


def location_context(
    district: str | None,
    lat: float | None = None,
    lon: float | None = None,
) -> dict:
    """Return flood, rain, and facility context. Missing data becomes null or false."""
    result = {
        "in_flood_extent_1d": False,
        "in_flood_extent_7d": False,
        "in_flood_extent_30d": False,
        "repeat_flood_area": False,
        "rainfall_last_24h_mm": None,
        "rainfall_forecast_24h_mm": None,
        "nearest_hospitals": [],
        "candidate_shelters": [],
        "data_freshness": {},
        "in_flood_risk_layer": False,
        "in_observed_event_extent": False,
        "matched_district": None,
        "point": None,
    }
    if not db_exists():
        return result
    with connect() as conn:
        result["data_freshness"] = {
            row["source"]: row["fetched_at"]
            for row in conn.execute("SELECT source, fetched_at FROM source_status")
        }
        matched = _match_district(conn, district)
        if lat is None or lon is None:
            if matched is not None:
                lat = matched["lat"]
                lon = matched["lon"]
        if matched is not None:
            result["matched_district"] = matched["name_en"]
        if lat is None or lon is None:
            return result
        result["point"] = {"lat": lat, "lon": lon}
        windows, observed = _windows_containing(conn, lat, lon)
        result["in_observed_event_extent"] = observed
        result["in_flood_extent_1d"] = bool(windows & EXTENT_1D)
        result["in_flood_extent_7d"] = bool(windows & (EXTENT_1D | EXTENT_3D | EXTENT_7D))
        result["in_flood_extent_30d"] = bool(
            windows & (EXTENT_1D | EXTENT_3D | EXTENT_7D | EXTENT_30D)
        )
        result["in_flood_risk_layer"] = "flood_risk_layer" in windows
        result["repeat_flood_area"] = _repeat_contains(conn, lat, lon)
        location_id = matched["location_id"] if matched is not None else None
        if location_id:
            # A ThaiWater gauge is a measured 24-hour total. The Open-Meteo
            # archive is the fallback when no gauge was matched to this district.
            gauge = _latest_rain(conn, location_id, "thaiwater-rain-24h")
            result["rainfall_last_24h_mm"] = (
                gauge
                if gauge is not None
                else _latest_rain(conn, location_id, "open-meteo-archive")
            )
            result["rainfall_forecast_24h_mm"] = _latest_rain(
                conn, location_id, "open-meteo-forecast", newest=False
            )
        result["nearest_hospitals"] = _nearest(conn, lat, lon, HOSPITAL_TYPES, 3)
        result["candidate_shelters"] = _nearest(conn, lat, lon, SHELTER_TYPES, 3)
    return result


def _match_district(conn, text: str | None):
    rows = conn.execute(
        "SELECT location_id, name_en, name_th, lat, lon FROM districts"
    ).fetchall()
    if not text:
        return None
    low = text.lower()
    matches = []
    for row in rows:
        name = (row["name_en"] or "").lower()
        thai = (row["name_th"] or "").lower()
        if name and (name in low or low in name):
            matches.append(row)
        elif thai and (thai in low or low in thai):
            matches.append(row)
    if not matches:
        return None
    return max(matches, key=lambda row: len(row["name_en"] or ""))


def _windows_containing(conn, lat: float, lon: float) -> tuple[set[str], bool]:
    point = Point(lon, lat)
    found: set[str] = set()
    observed = False
    live = EXTENT_1D | EXTENT_3D | EXTENT_7D | EXTENT_30D
    for row in conn.execute("SELECT duration_window, geometry FROM flood_extent"):
        window = str(row["duration_window"] or "")
        try:
            geom = loads(row["geometry"])
        except Exception:
            continue
        if not geom.contains(point):
            continue
        if window == "flood_risk_layer" or window.lower() in live:
            found.add(window)
        else:
            observed = True
    return found, observed


def _repeat_contains(conn, lat: float, lon: float) -> bool:
    point = Point(lon, lat)
    for row in conn.execute("SELECT geometry FROM repeat_flood"):
        if loads(row["geometry"]).contains(point):
            return True
    return False


def _latest_rain(conn, location_id: str, source: str, newest: bool = True) -> float | None:
    order = "DESC" if newest else "ASC"
    row = conn.execute(
        f"""
        SELECT rainfall_mm FROM weather_observation
        WHERE location_id = ? AND source = ? AND rainfall_mm IS NOT NULL
        ORDER BY timestamp {order}
        LIMIT 1
        """,
        (location_id, source),
    ).fetchone()
    if row is None:
        return None
    return row["rainfall_mm"]


def _nearest(conn, lat: float, lon: float, types: set[str], limit: int) -> list[dict]:
    placeholders = ",".join("?" for _ in types)
    rows = conn.execute(
        f"""
        SELECT osm_id, type, name, accessibility_flag, lat, lon
        FROM infrastructure
        WHERE type IN ({placeholders}) AND lat IS NOT NULL AND lon IS NOT NULL
        """,
        tuple(types),
    ).fetchall()
    ranked = []
    for row in rows:
        distance = haversine_km(lat, lon, row["lat"], row["lon"])
        ranked.append(
            {
                "osm_id": row["osm_id"],
                "name": row["name"],
                "type": row["type"],
                "accessibility_flag": row["accessibility_flag"],
                "distance_km": round(distance, 3),
            }
        )
    ranked.sort(key=lambda item: item["distance_km"])
    return ranked[:limit]


def sample_districts(limit: int = 3) -> list[str]:
    if not DB_PATH.exists():
        return []
    with connect() as conn:
        rows = conn.execute(
            "SELECT name_en FROM districts ORDER BY name_en LIMIT ?",
            (limit,),
        ).fetchall()
    return [row["name_en"] for row in rows]
