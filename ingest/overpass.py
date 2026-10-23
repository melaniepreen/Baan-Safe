"""OpenStreetMap Overpass queries limited to the flood-polygon bbox.

overpass-api.de robots.txt disallows /api/, so the interpreter host comes from
config/ingest.yaml (a host with no robots.txt).
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from config.settings import load_yaml
from ingest.common import OffHostError, PoliteClient, RobotsDisallowed
from ingest.db import connect, set_status
from ingest.geo import bounds_of, centroid_latlon, haversine_km, loads

AMENITY_RE = "hospital|clinic|pharmacy|school|place_of_worship|community_centre"
FACILITY_TYPES = {
    "hospital",
    "clinic",
    "pharmacy",
    "school",
    "place_of_worship",
    "community_centre",
    "bridge",
    "waterway",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _interpreter() -> tuple[str, str]:
    cfg = load_yaml("ingest.yaml")
    url = cfg["overpass"]["interpreter"]
    host = urlparse(url).hostname or ""
    if host == "overpass-api.de":
        raise OffHostError("overpass-api.de is disallowed by its robots.txt")
    return url, host


def _flood_geoms():
    with connect() as conn:
        rows = conn.execute("SELECT geometry, duration_window FROM flood_extent").fetchall()
    geoms = []
    for row in rows:
        geoms.append((row["duration_window"], loads(row["geometry"])))
    return geoms


def ingest_admin(refresh: bool) -> str:
    geoms = _flood_geoms()
    if not geoms:
        detail = "SKIPPED: no flood polygons, so no district bbox."
        set_status("overpass_admin", fetched_at=_now(), row_count=0, status="skipped", detail=detail)
        return detail
    shapes = [geom for _, geom in geoms]
    min_lat, min_lon, max_lat, max_lon = bounds_of(shapes)
    if (max_lat - min_lat) > 4 or (max_lon - min_lon) > 4:
        detail = (
            "BLOCKED: flood bbox is wider than 4 degrees, so the admin query would "
            "be too close to a country-wide pull. Human should narrow demo_event."
        )
        set_status("overpass_admin", fetched_at=_now(), row_count=0, status="blocked", detail=detail)
        return detail
    pad = 0.05
    south, west, north, east = min_lat - pad, min_lon - pad, max_lat + pad, max_lon + pad
    query = (
        f"[out:json][timeout:80];"
        f'relation["boundary"="administrative"]["admin_level"="6"]'
        f"({south},{west},{north},{east});"
        f"out tags center;"
    )
    try:
        url, host = _interpreter()
        client = PoliteClient("overpass", refresh=refresh, timeout=100)
        result = client.post(
            url,
            allowed_hosts={host},
            data={"data": query},
        )
    except (RobotsDisallowed, OffHostError) as exc:
        set_status("overpass_admin", fetched_at=_now(), row_count=0, status="blocked", detail=str(exc))
        return str(exc)
    if result.status_code != 200:
        detail = f"BLOCKED: Overpass admin HTTP {result.status_code}."
        set_status("overpass_admin", fetched_at=result.fetched_at, row_count=0, status="blocked", detail=detail)
        return detail
    payload = json.loads(result.body)
    cfg = load_yaml("ingest.yaml")
    max_km = float(cfg.get("district_match_km", 25))
    centroids = [centroid_latlon(geom) for geom in shapes]
    chosen: dict[str, dict] = {}
    for element in payload.get("elements") or []:
        center = element.get("center") or {}
        lat, lon = center.get("lat"), center.get("lon")
        if lat is None or lon is None:
            continue
        tags = element.get("tags") or {}
        name_en = tags.get("name:en") or tags.get("name") or ""
        name_th = tags.get("name") or ""
        if not name_en:
            continue
        nearest = min(haversine_km(lat, lon, clat, clon) for clat, clon in centroids)
        if nearest > max_km:
            continue
        location_id = _slug(name_en)
        province = tags.get("addr:province") or _province_hint(name_en)
        current = chosen.get(location_id)
        if current is None or nearest < current["km"]:
            chosen[location_id] = {
                "location_id": location_id,
                "name_en": name_en,
                "name_th": name_th,
                "lat": lat,
                "lon": lon,
                "province": province,
                "km": nearest,
            }
    # Cap 50, closest first.
    ordered = sorted(chosen.values(), key=lambda row: row["km"])[:50]
    with connect() as conn:
        conn.execute("DELETE FROM districts")
        for row in ordered:
            conn.execute(
                """
                INSERT INTO districts (location_id, name_en, name_th, lat, lon, province, source)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["location_id"],
                    row["name_en"],
                    row["name_th"],
                    row["lat"],
                    row["lon"],
                    row["province"],
                    "overpass-admin-level-6-nearest-centre",
                ),
            )
    if not ordered:
        _fallback_grid(centroids)
        detail = (
            "Overpass returned no admin centre within the match distance. "
            "Stored DISTRICT_TBD grid centroids from flood polygons instead."
        )
        with connect() as conn:
            count = conn.execute("SELECT COUNT(*) AS n FROM districts").fetchone()["n"]
        set_status("overpass_admin", fetched_at=result.fetched_at, row_count=count, status="fallback", detail=detail)
        return detail
    detail = (
        f"Stored {len(ordered)} districts whose centres are within {max_km} km of a "
        "flood polygon centroid. Assignment is nearest centre, not a boundary intersection."
    )
    set_status(
        "overpass_admin",
        fetched_at=result.fetched_at,
        row_count=len(ordered),
        status="ok",
        detail=detail,
    )
    return detail


def _fallback_grid(centroids: list[tuple[float, float]]) -> None:
    cells: dict[tuple[int, int], tuple[float, float]] = {}
    for lat, lon in centroids:
        key = (round(lat * 10), round(lon * 10))
        cells.setdefault(key, (lat, lon))
    with connect() as conn:
        for index, ((_, _), (lat, lon)) in enumerate(list(cells.items())[:50], start=1):
            conn.execute(
                """
                INSERT OR REPLACE INTO districts
                    (location_id, name_en, name_th, lat, lon, province, source)
                VALUES (?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    f"DISTRICT_TBD_{index}",
                    f"DISTRICT_TBD_{index}",
                    "",
                    lat,
                    lon,
                    "flood-polygon-centroid-grid",
                ),
            )


def ingest_facilities(refresh: bool) -> str:
    geoms = _flood_geoms()
    if not geoms:
        detail = "SKIPPED: no flood polygons, so no facility bbox."
        set_status("overpass_facilities", fetched_at=_now(), row_count=0, status="skipped", detail=detail)
        return detail
    shapes = [geom for _, geom in geoms]
    min_lat, min_lon, max_lat, max_lon = bounds_of(shapes)
    if (max_lat - min_lat) > 4 or (max_lon - min_lon) > 4:
        detail = "BLOCKED: facility bbox would be wider than 4 degrees."
        set_status(
            "overpass_facilities",
            fetched_at=_now(),
            row_count=0,
            status="blocked",
            detail=detail,
        )
        return detail
    pad = 0.02
    south, west, north, east = min_lat - pad, min_lon - pad, max_lat + pad, max_lon + pad
    bbox = f"({south},{west},{north},{east})"
    query = (
        "[out:json][timeout:90];("
        f'node["amenity"~"{AMENITY_RE}"]{bbox};'
        f'way["amenity"~"{AMENITY_RE}"]{bbox};'
        f'node["man_made"="bridge"]{bbox};'
        f'way["man_made"="bridge"]{bbox};'
        f'way["waterway"~"river|canal"]{bbox};'
        ");out center tags 1200;"
    )
    try:
        url, host = _interpreter()
        client = PoliteClient("overpass", refresh=refresh, timeout=120)
        result = client.post(url, allowed_hosts={host}, data={"data": query})
    except (RobotsDisallowed, OffHostError) as exc:
        set_status(
            "overpass_facilities",
            fetched_at=_now(),
            row_count=0,
            status="blocked",
            detail=str(exc),
        )
        return str(exc)
    if result.status_code != 200:
        detail = f"BLOCKED: Overpass facilities HTTP {result.status_code}."
        set_status(
            "overpass_facilities",
            fetched_at=result.fetched_at,
            row_count=0,
            status="blocked",
            detail=detail,
        )
        return detail
    payload = json.loads(result.body)
    elements = list(payload.get("elements") or [])
    # OSM tags bridges as bridge=yes on the highway way. man_made=bridge is rare.
    bridge_query = (
        "[out:json][timeout:60];("
        f'way["bridge"="yes"]{bbox};'
        f'node["man_made"="bridge"]{bbox};'
        ");out center tags 150;"
    )
    try:
        bridge_result = client.post(url, allowed_hosts={host}, data={"data": bridge_query})
        if bridge_result.status_code == 200:
            bridge_payload = json.loads(bridge_result.body)
            seen = {(el.get("type"), el.get("id")) for el in elements}
            for el in bridge_payload.get("elements") or []:
                key = (el.get("type"), el.get("id"))
                if key not in seen:
                    elements.append(el)
                    seen.add(key)
    except (RobotsDisallowed, OffHostError):
        pass
    extent_shapes = [geom for window, geom in geoms if _is_extent_window(window)]
    buffer_m = float(load_yaml("escalation.yaml")["enrichment_flags"]["near_flood_buffer_m"])
    stored = 0
    with connect() as conn:
        conn.execute("DELETE FROM infrastructure")
        for element in elements:
            lat, lon = _element_latlon(element)
            if lat is None or lon is None:
                continue
            kind = _element_type(element)
            if kind not in FACILITY_TYPES:
                continue
            tags = element.get("tags") or {}
            name = tags.get("name:en") or tags.get("name") or "unnamed"
            flag = _accessibility(lat, lon, extent_shapes, buffer_m)
            osm_id = f"{element.get('type')}/{element.get('id')}"
            point = json.dumps({"type": "Point", "coordinates": [lon, lat]})
            conn.execute(
                """
                INSERT INTO infrastructure
                    (osm_id, type, geometry, name, accessibility_flag, lat, lon)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (osm_id, kind, point, name, flag, lat, lon),
            )
            stored += 1
    detail = (
        f"Stored {stored} facilities inside the flood-polygon bbox "
        f"({south:.3f},{west:.3f},{north:.3f},{east:.3f}). "
        "accessibility_flag uses flood-extent windows only, not the flood-risk layer. "
        "Waterways are centre points, not full lines, to keep the pull bounded."
    )
    set_status(
        "overpass_facilities",
        fetched_at=result.fetched_at,
        row_count=stored,
        status="ok" if stored else "empty",
        detail=detail,
    )
    return detail


def _is_extent_window(window: str | None) -> bool:
    if not window:
        return False
    return window.lower() in {
        "1d",
        "3d",
        "7d",
        "30d",
        "1",
        "3",
        "7",
        "30",
        "1-day",
        "3-day",
        "7-day",
        "30-day",
    }


def _accessibility(lat: float, lon: float, extents, buffer_m: float) -> str:
    from shapely.geometry import Point

    point = Point(lon, lat)
    nearest_m = None
    for geom in extents:
        if geom.contains(point):
            return "inside_flood_extent"
        # Degree distance, scaled at this latitude. Good enough for a 500 m flag.
        metres = geom.distance(point) * 111_320
        nearest_m = metres if nearest_m is None else min(nearest_m, metres)
    if nearest_m is not None and nearest_m <= buffer_m:
        return "near_flood_extent"
    return "clear"


def _element_latlon(element: dict) -> tuple[float | None, float | None]:
    if "lat" in element and "lon" in element:
        return float(element["lat"]), float(element["lon"])
    center = element.get("center") or {}
    if "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None, None


def _element_type(element: dict) -> str:
    tags = element.get("tags") or {}
    if tags.get("man_made") == "bridge" or tags.get("bridge") == "yes":
        return "bridge"
    if tags.get("waterway"):
        return "waterway"
    amenity = tags.get("amenity") or ""
    if amenity in FACILITY_TYPES:
        return amenity
    return amenity


def _slug(name: str) -> str:
    slug = name.lower().strip()
    slug = re.sub(r"[^a-z0-9]+", "-", slug).strip("-")
    return slug or "district"


def _province_hint(name_en: str) -> str | None:
    # The English OSM name is the district. Province is not invented here.
    return None
