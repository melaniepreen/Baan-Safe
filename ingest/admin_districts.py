"""Full admin_level=6 district gazetteer for the configured provinces.

`districts` stays the flood-match table (enrichment, weather, and facilities
are keyed to it). `admin_districts` is the wider gazetteer the keyword
extractor reads: every district of every `gistda.province_codes` province.
Licence: OpenStreetMap, ODbL.

The Overpass mirror carries no `area` objects for these relations, so each
province takes two small calls: the province boundary `out geom` (a bounding
box for the district query and the polygon for attribution), then the
admin_level=6 relations inside that box. A district belongs to the province
when its centre falls inside the province polygon — bbox edges overlap the
neighbouring provinces.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from config.settings import load_yaml
from ingest.common import OffHostError, PoliteClient, RobotsDisallowed
from ingest.db import connect, set_status
from ingest.overpass import _interpreter

PROVINCE_NAMES = {
    50: "Chiang Mai",
    51: "Lamphun",
    52: "Lampang",
    54: "Phrae",
    55: "Nan",
    56: "Phayao",
    57: "Chiang Rai",
    90: "Songkhla",
}

SOURCE = "overpass-admin-level-6-province"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(name: str) -> str:
    return "".join(ch if ch.isalnum() else "-" for ch in name.lower()).strip("-")


def _province_query(code: int) -> str:
    return (
        "[out:json][timeout:80];"
        f'rel["boundary"="administrative"]["ISO3166-2"="TH-{code}"];'
        "out geom;"
    )


def _districts_query(south: float, west: float, north: float, east: float) -> str:
    return (
        "[out:json][timeout:80];"
        'rel["boundary"="administrative"]["admin_level"="6"]'
        f"({south},{west},{north},{east});"
        "out tags center;"
    )


def _outer_rings(relation: dict) -> list[list[tuple[float, float]]]:
    """Assemble outer boundary ways into closed rings of (lat, lon)."""
    ways = []
    for member in relation.get("members") or []:
        if member.get("type") == "way" and member.get("role") in ("outer", ""):
            geometry = member.get("geometry") or []
            points = [(p["lat"], p["lon"]) for p in geometry if "lat" in p and "lon" in p]
            if len(points) >= 2:
                ways.append(points)
    rings: list[list[tuple[float, float]]] = []
    while ways:
        ring = ways.pop()
        while ring[0] != ring[-1]:
            for i, way in enumerate(ways):
                if way[0] == ring[-1]:
                    ring += way[1:]
                elif way[-1] == ring[-1]:
                    ring += way[-2::-1]
                elif way[0] == ring[0]:
                    ring = way[-2::-1] + ring
                elif way[-1] == ring[0]:
                    ring = way[:-1] + ring
                else:
                    continue
                ways.pop(i)
                break
            else:
                break  # unclosed chain: keep what we have
        if len(ring) >= 4:
            rings.append(ring)
    return rings


def _inside(point: tuple[float, float], ring: list[tuple[float, float]]) -> bool:
    """Ray casting. point is (lat, lon); the ring is closed (lat, lon)."""
    lat, lon = point
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        yi, xi = ring[i]
        yj, xj = ring[j]
        if (xi > lon) != (xj > lon):
            cross = (yj - yi) * (lon - xi) / (xj - xi) + yi
            if lat < cross:
                inside = not inside
        j = i
    return inside


def _in_province(lat: float, lon: float, rings: list[list[tuple[float, float]]]) -> bool:
    return any(_inside((lat, lon), ring) for ring in rings)


def ingest(refresh: bool = False) -> str:
    codes = [int(code) for code in load_yaml("ingest.yaml")["gistda"]["province_codes"]]
    url, host = _interpreter()
    client = PoliteClient("overpass_gazetteer", refresh=refresh, timeout=100)
    rows: list[dict] = []
    notes: list[str] = []
    for code in codes:
        try:
            result = client.post(
                url, allowed_hosts={host}, data={"data": _province_query(code)}
            )
            if result.status_code != 200:
                notes.append(f"TH-{code}: province HTTP {result.status_code}")
                continue
            elements = (json.loads(result.body) or {}).get("elements") or []
            relation = next(
                (e for e in elements if (e.get("tags") or {}).get("ISO3166-2")),
                None,
            )
            if relation is None:
                notes.append(f"TH-{code}: no province relation")
                continue
            tags = relation.get("tags") or {}
            province = tags.get("name:en") or PROVINCE_NAMES.get(code, f"TH-{code}")
            rings = _outer_rings(relation)
            if not rings:
                notes.append(f"TH-{code} {province}: no outer boundary")
                continue
            lats = [p[0] for ring in rings for p in ring]
            lons = [p[1] for ring in rings for p in ring]
            south, north = min(lats) - 0.02, max(lats) + 0.02
            west, east = min(lons) - 0.02, max(lons) + 0.02
            result = client.post(
                url,
                allowed_hosts={host},
                data={"data": _districts_query(south, west, north, east)},
            )
            if result.status_code != 200:
                notes.append(f"TH-{code}: districts HTTP {result.status_code}")
                continue
            found = 0
            for element in (json.loads(result.body) or {}).get("elements") or []:
                dtags = element.get("tags") or {}
                name_en = dtags.get("name:en")
                name_th = dtags.get("name:th") or dtags.get("name") or ""
                center = element.get("center") or {}
                lat, lon = center.get("lat"), center.get("lon")
                if not name_en or lat is None or lon is None:
                    continue
                if not _in_province(lat, lon, rings):
                    continue
                rows.append(
                    {
                        "location_id": _slug(name_en) + "-" + str(code),
                        "name_en": name_en,
                        "name_th": name_th,
                        "province": province,
                        "province_code": str(code),
                        "lat": lat,
                        "lon": lon,
                        "source": SOURCE,
                    }
                )
                found += 1
            notes.append(f"TH-{code} {province}: {found} districts")
        except (RobotsDisallowed, OffHostError, RuntimeError) as exc:
            notes.append(f"TH-{code}: {exc}")
    with connect() as conn:
        conn.execute("DELETE FROM admin_districts")
        for row in rows:
            conn.execute(
                """
                INSERT OR REPLACE INTO admin_districts
                    (location_id, name_en, name_th, province, province_code, lat, lon, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["location_id"],
                    row["name_en"],
                    row["name_th"],
                    row["province"],
                    row["province_code"],
                    row["lat"],
                    row["lon"],
                    row["source"],
                ),
            )
    status = "ok" if rows and all("districts HTTP" not in n and "no province" not in n and "no outer" not in n for n in notes) else "partial"
    detail = (
        f"Stored {len(rows)} admin_level=6 districts across {len(codes)} provinces "
        "(OpenStreetMap, ODbL). " + " ".join(notes)
    )
    set_status("overpass_gazetteer", fetched_at=_now(), row_count=len(rows), status=status, detail=detail)
    return detail
