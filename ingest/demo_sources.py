"""Live public data for the demo provinces, with a committed offline copy.

Provinces are the fixture set: Lampang, Phrae, Nan, and Phayao. Callers stay
synthetic. This module stores place names, district names, rain, and reservoir
totals. It does not store phones, national ids, or home addresses.

``--refresh`` talks to the network and rewrites ``data/snapshots/``. With no
flag, ``python -m ingest.demo_sources`` prints the committed status and does
not send a request. A failed live call keeps the previous snapshot.
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from config.envfile import load_env_file
from config.settings import load_yaml
from ingest.common import PoliteClient, scrub
from ingest.geo import haversine_km
from ingest.snapshots import read_snapshot, write_snapshot
from paths import ROOT

DEMO_PROVINCES = ("Lampang", "Phrae", "Nan", "Phayao")

# Public town centres used as Overpass search points. Not household locations.
TOWNS = (
    {"name": "Mueang Lampang District", "province": "Lampang", "lat": 18.2888, "lon": 99.4906},
    {"name": "Mueang Phrae District", "province": "Phrae", "lat": 18.1446, "lon": 100.1410},
    {"name": "Mueang Nan District", "province": "Nan", "lat": 18.7756, "lon": 100.7730},
    {"name": "Mueang Phayao District", "province": "Phayao", "lat": 19.1664, "lon": 99.8664},
)

FIXTURE_DISTRICTS = (
    ("Mae Mo District", "Lampang"),
    ("Mae Tha District", "Lampang"),
    ("Sop Prap District", "Lampang"),
    ("Mueang Lampang District", "Lampang"),
    ("Den Chai District", "Phrae"),
    ("Long District", "Phrae"),
    ("Wang Chin District", "Phrae"),
    ("Mueang Phrae District", "Phrae"),
    ("Song District", "Phrae"),
    ("Sung Men District", "Phrae"),
    ("Rong Kwang District", "Phrae"),
    ("Nong Muang Khai District", "Phrae"),
    ("Wiang Sa District", "Nan"),
    ("Ban Luang District", "Nan"),
    ("Mueang Nan District", "Nan"),
    ("Chiang Muan District", "Phayao"),
    ("Mueang Phayao District", "Phayao"),
)

GISTDA_FLOOD = "https://api-gateway.gistda.or.th/api/2.0/resources/features/flood/1day"
ARCGIS = "https://gistdaportal.gistda.or.th/arcgis/rest/services/app/GISTDA_flood/MapServer"
OVERPASS = "https://overpass.openstreetmap.fr/api/interpreter"
HDX_XLSX = (
    "https://data.humdata.org/dataset/d24bdc45-eb4c-4e3d-8b16-44db02667c27/"
    "resource/a925b917-01ae-48c4-9279-7efe680a6b11/download/tha_admin_boundaries.xlsx"
)
GEOBOUNDARIES = "https://www.geoboundaries.org/api/current/gbOpen/THA/ADM2/"
RID_DAMS = "https://app.rid.go.th/reservoir/api/dam/public"
OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"

PHONE = re.compile(r"(?:\+66|0)[\s-]?\d[\d\s-]{7,}")
NATIONAL_ID = re.compile(r"\b\d{13}\b")
BUILDING_ONLY = re.compile(r"^อาคาร\s*\d+$")

PLACE_FILTERS = (
    '["amenity"="hospital"]',
    '["amenity"="school"]',
    '["amenity"="place_of_worship"]',
    '["amenity"="fire_station"]',
    '["amenity"="boat_rental"]',
    '["amenity"="ferry_terminal"]',
    '["man_made"="pier"]',
)

LABEL_BUILDINGS = {
    "bldg-school": "school",
    "bldg-tower-white": "hospital",
    "bldg-tower-pink": "fire_station",
    "bldg-sala": "temple",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _public_text(value: str | None) -> str | None:
    if not value:
        return None
    text = " ".join(str(value).split())
    if not text or len(text) > 120:
        return None
    if PHONE.search(text) or NATIONAL_ID.search(text) or BUILDING_ONLY.match(text):
        return None
    if "@" in text:
        return None
    return text


def _round(value) -> float | None:
    try:
        return round(float(value), 5)
    except (TypeError, ValueError):
        return None


def load_gistda(refresh: bool = False) -> tuple[dict, str]:
    if not refresh:
        return read_snapshot("gistda") or {}, "snapshot"
    try:
        payload = _fetch_gistda()
    except Exception as exc:  # noqa: BLE001 — offline demo keeps the snapshot
        kept = read_snapshot("gistda") or {}
        return kept, "snapshot:" + scrub(str(exc))[:180]
    write_snapshot("gistda", payload)
    return payload, "live"


def _fetch_gistda() -> dict:
    load_env_file()
    key = os.environ.get("GISTDA_API_KEY", "").strip()
    client = PoliteClient("gistda_demo", refresh=True, timeout=40, attempts=2)
    open_api: dict = {
        "url": GISTDA_FLOOD,
        "catalogue": "https://opendata.gistda.or.th/dataset/flood-disaster-data",
    }
    if not key:
        result = client.get_json(
            GISTDA_FLOOD,
            allowed_hosts={"api-gateway.gistda.or.th"},
            params={"limit": 1, "offset": 0},
        )
        open_api["status"] = "blocked"
        open_api["http_status"] = result.status_code
        open_api["detail"] = (
            "GISTDA_API_KEY was not set. A request without a key was sent and "
            f"the server returned HTTP {result.status_code}. No key was written."
        )
    else:
        result = client.get_json(
            GISTDA_FLOOD,
            allowed_hosts={"api-gateway.gistda.or.th"},
            params={"limit": 1, "offset": 0, "api_key": key},
        )
        open_api["status"] = "ok" if result.status_code == 200 else "blocked"
        open_api["http_status"] = result.status_code
        open_api["detail"] = (
            "GISTDA_API_KEY was read from the environment and was not written "
            f"to this snapshot. HTTP {result.status_code}."
        )
        if result.status_code == 200:
            body = json.loads(result.body)
            open_api["number_matched"] = body.get("numberMatched")
    arcgis = {"url": ARCGIS, "status": "ok"}
    for layer, field in ((0, "layer0_flood_extent_count"), (1, "layer1_flood_risk_count")):
        counted = client.get_json(
            f"{ARCGIS}/{layer}/query",
            allowed_hosts={"gistdaportal.gistda.or.th"},
            params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
        )
        if counted.status_code != 200:
            arcgis["status"] = "blocked"
            arcgis[field] = None
            continue
        arcgis[field] = json.loads(counted.body).get("count")
    return {
        "checked_at": _now(),
        "open_api": open_api,
        "arcgis": arcgis,
        "licence": "GISTDA flood services. The keyed API needs a registered key. The ArcGIS MapServer counts are public.",
        "rate_limit": "One probe per window plus two count queries. No national polygon download.",
    }


def load_open_meteo(refresh: bool = False) -> tuple[dict, str]:
    if not refresh:
        return read_snapshot("open_meteo") or {}, "snapshot"
    try:
        payload = _fetch_open_meteo()
    except Exception as exc:  # noqa: BLE001
        return read_snapshot("open_meteo") or {}, "snapshot:" + scrub(str(exc))[:180]
    write_snapshot("open_meteo", payload)
    return payload, "live"


def _fetch_open_meteo() -> dict:
    allowed = bool(load_yaml("ingest.yaml").get("open_meteo_documented_api_despite_robots_disallow"))
    if not allowed:
        raise RuntimeError("open_meteo_documented_api_despite_robots_disallow is false")
    client = PoliteClient("open_meteo_demo", refresh=True, timeout=40, attempts=2)
    today = datetime.now(ZoneInfo("Asia/Bangkok")).date()
    archive_end = today - timedelta(days=1)
    archive_start = archive_end - timedelta(days=6)
    locations = []
    for town in TOWNS:
        forecast = _meteo(
            client,
            OPEN_METEO_FORECAST,
            "api.open-meteo.com",
            town,
            {"forecast_days": 3},
        )
        archive = _meteo(
            client,
            OPEN_METEO_ARCHIVE,
            "archive-api.open-meteo.com",
            town,
            {"start_date": archive_start.isoformat(), "end_date": archive_end.isoformat()},
        )
        locations.append(
            {
                "name_en": town["name"],
                "province": f"{town['province']} Province",
                "lat": town["lat"],
                "lon": town["lon"],
                "forecast": forecast,
                "archive": archive,
            }
        )
    return {
        "checked_at": _now(),
        "url": OPEN_METEO_FORECAST,
        "archive_url": OPEN_METEO_ARCHIVE,
        "licence": "CC BY 4.0 (Open-Meteo). Attribution required.",
        "rate_limit": "About 10,000 requests a day on the free API. This refresh sends 8 calls, slower than 1 per second.",
        "robots": "api.open-meteo.com robots.txt is Disallow: /. Calls are the documented forecast and archive APIs because config allows that.",
        "locations": locations,
    }


def _meteo(client: PoliteClient, url: str, host: str, town: dict, extra: dict) -> list[dict]:
    params = {
        "latitude": town["lat"],
        "longitude": town["lon"],
        "daily": "precipitation_sum",
        "timezone": "Asia/Bangkok",
        **extra,
    }
    result = client.get_json(url, allowed_hosts={host}, params=params, ignore_robots=True)
    if result.status_code != 200:
        raise RuntimeError(f"Open-Meteo HTTP {result.status_code}")
    daily = json.loads(result.body).get("daily") or {}
    rows = []
    for day, rain in zip(daily.get("time") or [], daily.get("precipitation_sum") or []):
        if rain is None:
            continue
        rows.append({"date": day, "precipitation_mm": rain})
    return rows


def load_gazetteer(refresh: bool = False) -> tuple[dict, str]:
    if not refresh:
        return read_snapshot("gazetteer") or {}, "snapshot"
    try:
        payload = _fetch_gazetteer()
    except Exception as exc:  # noqa: BLE001
        return read_snapshot("gazetteer") or {}, "snapshot:" + scrub(str(exc))[:180]
    write_snapshot("gazetteer", payload)
    return payload, "live"


def _fetch_gazetteer() -> dict:
    import httpx

    # HDX redirects the file to object storage. The redirect URL is not stored.
    with httpx.Client(timeout=120, follow_redirects=True, headers={"User-Agent": "BaanSafe-hackathon/0.1"}) as client:
        response = client.get(HDX_XLSX)
    if response.status_code != 200 or not response.content.startswith(b"PK"):
        raise RuntimeError(f"COD-AB spreadsheet HTTP {response.status_code}")
    raw_dir = ROOT / "data" / "raw" / "demo_sources"
    raw_dir.mkdir(parents=True, exist_ok=True)
    (raw_dir / "tha_admin_boundaries.xlsx").write_bytes(response.content)
    districts = _districts_from_xlsx(raw_dir / "tha_admin_boundaries.xlsx")
    return {
        "checked_at": _now(),
        "url": "https://data.humdata.org/dataset/cod-ab-tha",
        "download": HDX_XLSX,
        "licence": "Creative Commons Attribution for Intergovernmental Organisations (CC BY-IGO)",
        "rate_limit": "HDX CKAN. One spreadsheet download. Geometry zips are hundreds of megabytes and are not fetched.",
        "level": "ADM2 districts only. Tambon rows are not stored.",
        "districts": districts,
    }


def _districts_from_xlsx(path) -> list[dict]:
    import openpyxl

    book = openpyxl.load_workbook(path, read_only=True, data_only=True)
    sheet = book["tha_admin2"]
    rows = sheet.iter_rows(values_only=True)
    header = [str(cell) if cell is not None else "" for cell in next(rows)]
    index = {name: pos for pos, name in enumerate(header)}
    districts = []
    for row in rows:
        def cell(name: str):
            pos = index.get(name)
            if pos is None or pos >= len(row):
                return None
            return row[pos]

        name_en = _public_text(cell("adm2_name"))
        name_th = _public_text(cell("adm2_name1"))
        province_en = _public_text(cell("adm1_name"))
        province_th = _public_text(cell("adm1_name1"))
        if not name_en or not province_en:
            continue
        districts.append(
            {
                "name_en": name_en,
                "name_th": name_th,
                "province_en": province_en,
                "province_th": province_th,
                "pcode": _public_text(cell("adm2_pcode")),
                "lat": _round(cell("center_lat")),
                "lon": _round(cell("center_lon")),
            }
        )
    book.close()
    if len(districts) < 100:
        raise RuntimeError("COD-AB district sheet was too short to trust")
    return districts


def load_places(refresh: bool = False) -> tuple[dict, str]:
    if not refresh:
        return read_snapshot("places") or {}, "snapshot"
    try:
        payload = _fetch_places()
    except Exception as exc:  # noqa: BLE001
        return read_snapshot("places") or {}, "snapshot:" + scrub(str(exc))[:180]
    write_snapshot("places", payload)
    return payload, "live"


def _fetch_places() -> dict:
    client = PoliteClient("overpass_demo", refresh=True, timeout=70, attempts=2)
    elements: list[dict] = []
    notes = []
    for point in _search_points():
        query = _point_query(point["lat"], point["lon"], point["radius"])
        batch, note = _overpass(client, query)
        elements.extend(batch)
        notes.append(f"{point['name']}: {note}")
    boats, boat_note = _overpass(client, _boat_query())
    elements.extend(boats)
    notes.append("boats: " + boat_note)
    places = _normalise_places(elements)
    return {
        "checked_at": _now(),
        "url": OVERPASS,
        "licence": "OpenStreetMap, ODbL. Attribution and share-alike.",
        "rate_limit": "overpass.openstreetmap.fr has no robots.txt. One query per town or fixture district, at most one per second. overpass-api.de is not used.",
        "notes": notes,
        "places": places,
    }


def _search_points() -> list[dict]:
    points = []
    seen = set()

    def add(name: str, lat: float, lon: float, radius: int) -> None:
        key = (round(lat, 3), round(lon, 3))
        if key in seen:
            return
        seen.add(key)
        points.append({"name": name, "lat": lat, "lon": lon, "radius": radius})

    for town in TOWNS:
        add(town["name"], town["lat"], town["lon"], 7000)
    for name, province, lat, lon in _district_coords():
        if (name, province) in FIXTURE_DISTRICTS or (name, province.replace(" Province", "")) in FIXTURE_DISTRICTS:
            add(name, lat, lon, 10000)
        short = province.replace(" Province", "")
        pair = (name, short)
        if pair in FIXTURE_DISTRICTS:
            add(name, lat, lon, 10000)
    return points


def _district_coords() -> list[tuple[str, str, float, float]]:
    from ingest import store

    rows = [
        (row["name_en"], row["province"] or "", row["lat"], row["lon"])
        for row in store.rows("admin_districts")
        if row["lat"] is not None and row["lon"] is not None
    ]
    if rows:
        return rows
    payload = read_snapshot("gazetteer") or {}
    coords = []
    for row in payload.get("districts") or []:
        if row.get("lat") is None or row.get("lon") is None:
            continue
        coords.append((f"{row['name_en']} District", f"{row['province_en']} Province", row["lat"], row["lon"]))
    return coords


def _point_query(lat: float, lon: float, radius: int) -> str:
    lines = [f"nwr{filt}(around:{radius},{lat:.5f},{lon:.5f});" for filt in PLACE_FILTERS]
    return "[out:json][timeout:50];(\n" + "\n".join(lines) + "\n);out tags center;"


def _boat_query() -> str:
    return (
        "[out:json][timeout:40];("
        'nwr["man_made"="pier"](17.4,99.0,19.7,101.3);'
        'nwr["amenity"="ferry_terminal"](17.4,99.0,19.7,101.3);'
        'nwr["amenity"="boat_rental"](17.4,99.0,19.7,101.3);'
        ");out tags center 40;"
    )


def _overpass(client: PoliteClient, query: str) -> tuple[list[dict], str]:
    result = client.post(
        OVERPASS,
        allowed_hosts={"overpass.openstreetmap.fr"},
        data={"data": query},
    )
    if result.status_code != 200:
        return [], f"HTTP {result.status_code}"
    payload = json.loads(result.body)
    elements = payload.get("elements") or []
    return elements, f"{len(elements)} elements"


def _kind(tags: dict, name: str) -> str | None:
    amenity = tags.get("amenity") or ""
    if "คลินิก" in name:
        return None
    if amenity == "hospital":
        lowered = name.lower()
        if "โรงพยาบาล" in name or lowered.startswith("hospital") or " hospital" in lowered or name.startswith("รพ"):
            return "hospital"
        return None
    if amenity == "school":
        return "school"
    if amenity == "fire_station":
        return "fire_station"
    if amenity == "boat_rental":
        return "boat_rental"
    if amenity == "ferry_terminal":
        return "ferry_terminal"
    if tags.get("man_made") == "pier":
        return "pier"
    if amenity == "place_of_worship":
        if tags.get("religion") == "buddhist" or name.startswith("วัด"):
            return "temple"
        return "place_of_worship"
    return None


def _normalise_places(elements: list[dict]) -> list[dict]:
    centres = [
        {"name": name, "province": province, "lat": lat, "lon": lon}
        for name, province, lat, lon in _district_coords()
    ]
    chosen: dict[tuple, dict] = {}
    for element in elements:
        tags = element.get("tags") or {}
        name = _public_text(tags.get("name") or tags.get("name:th") or tags.get("name:en"))
        if not name or "ร้าง" in name or "poss closed" in name.lower():
            continue
        kind = _kind(tags, name)
        if kind is None:
            continue
        lat = _round(element.get("lat") or (element.get("center") or {}).get("lat"))
        lon = _round(element.get("lon") or (element.get("center") or {}).get("lon"))
        if lat is None or lon is None:
            continue
        district, province, km = _nearest_district(lat, lon, centres)
        if district is None or km > 30:
            continue
        short = (province or "").replace(" Province", "")
        if short not in DEMO_PROVINCES:
            continue
        place = {
            "osm_type": element.get("type"),
            "osm_id": element.get("id"),
            "kind": kind,
            "name": name,
            "name_th": _public_text(tags.get("name:th")),
            "name_en": _public_text(tags.get("name:en")),
            "lat": lat,
            "lon": lon,
            "district": district,
            "province": province,
            "km": round(km, 2),
        }
        key = (place["osm_type"], place["osm_id"], kind)
        current = chosen.get(key)
        if current is None or place["km"] < current["km"]:
            chosen[key] = place
    grouped: dict[tuple, list] = {}
    for place in chosen.values():
        grouped.setdefault((place["district"], place["kind"]), []).append(place)
    kept = []
    for rows in grouped.values():
        rows.sort(key=lambda row: row["km"])
        for row in rows[:3]:
            row.pop("km", None)
            kept.append(row)
    kept.sort(key=lambda row: (row["province"], row["district"], row["kind"], row["name"]))
    return kept


def _nearest_district(lat: float, lon: float, centres: list[dict]) -> tuple[str | None, str | None, float]:
    best = None
    best_km = 1e9
    for centre in centres:
        km = haversine_km(lat, lon, centre["lat"], centre["lon"])
        if km < best_km:
            best = centre
            best_km = km
    if best is None:
        return None, None, best_km
    return best["name"], best["province"], best_km


def load_rid(refresh: bool = False) -> tuple[dict, str]:
    if not refresh:
        return read_snapshot("rid") or {}, "snapshot"
    try:
        payload = _fetch_rid()
    except Exception as exc:  # noqa: BLE001
        return read_snapshot("rid") or {}, "snapshot:" + scrub(str(exc))[:180]
    write_snapshot("rid", payload)
    return payload, "live"


def _fetch_rid() -> dict:
    client = PoliteClient("rid_demo", refresh=True, timeout=40, attempts=2)
    result = client.get_json(RID_DAMS, allowed_hosts={"app.rid.go.th"})
    if result.status_code != 200:
        raise RuntimeError(f"RID HTTP {result.status_code}")
    body = json.loads(result.body)
    dams = []
    for block in body.get("data") or []:
        if block.get("region") != "ภาคเหนือ":
            continue
        for dam in block.get("dam") or []:
            name = _public_text(dam.get("name"))
            if not name:
                continue
            capacity = dam.get("capacity")
            storage = dam.get("storage")
            percent = None
            try:
                if capacity and storage is not None and float(capacity) > 0:
                    percent = round(float(storage) / float(capacity) * 100, 1)
            except (TypeError, ValueError):
                percent = None
            dams.append(
                {
                    "id": str(dam.get("id") or ""),
                    "name": name,
                    "capacity_mcm": capacity,
                    "storage_mcm": storage,
                    "percent_storage": percent,
                }
            )
    return {
        "checked_at": _now(),
        "url": RID_DAMS,
        "licence": "Royal Irrigation Department public dam JSON. No licence page is linked from the payload. Treat as a public operational feed and keep the attribution.",
        "rate_limit": "No published limit. One request per refresh. robots.txt on app.rid.go.th is HTTP 404.",
        "date": body.get("date"),
        "scope": "Northern region dams. The feed has no coordinates, so these rows are not joined to a district and do not change priority.",
        "dams": dams,
    }


def load_tmd(refresh: bool = False) -> tuple[dict, str]:
    """Record that no working public TMD JSON was usable.

    data.tmd.go.th robots.txt disallows ``/``, so that host is not called.
    """
    if not refresh:
        return read_snapshot("tmd") or {}, "snapshot"
    payload = {
        "checked_at": _now(),
        "status": "failed",
        "url": "https://www.tmd.go.th/",
        "data_host": "https://data.tmd.go.th/",
        "licence": "Not applicable. No dataset was stored.",
        "rate_limit": "data.tmd.go.th robots.txt is Disallow: /. That host was not called.",
        "detail": (
            "data.tmd.go.th robots.txt disallows every path, so the registered data API was not called. "
            "https://www.tmd.go.th/api/weather returned an HTML error page, not observations."
        ),
    }
    if refresh:
        try:
            client = PoliteClient("tmd_demo", refresh=True, timeout=25, attempts=1)
            result = client.get_json(
                "https://www.tmd.go.th/api/weather",
                allowed_hosts={"www.tmd.go.th"},
            )
            payload["http_status"] = result.status_code
            if result.status_code == 200 and result.body[:1] in (b"{", b"["):
                payload["status"] = "ok"
                payload["detail"] = "www.tmd.go.th returned JSON. It is not parsed into a district gauge."
        except Exception as exc:  # noqa: BLE001
            payload["detail"] += " Probe error: " + scrub(str(exc))[:160]
    write_snapshot("tmd", payload)
    return payload, "live"


def load_geoboundaries(refresh: bool = False) -> tuple[dict, str]:
    if not refresh:
        return read_snapshot("geoboundaries") or {}, "snapshot"
    try:
        payload = _fetch_geoboundaries()
    except Exception as exc:  # noqa: BLE001
        return read_snapshot("geoboundaries") or {}, "snapshot:" + scrub(str(exc))[:180]
    write_snapshot("geoboundaries", payload)
    return payload, "live"


def _fetch_geoboundaries() -> dict:
    import time

    time.sleep(10)  # robots Crawl-delay: 10
    client = PoliteClient("geoboundaries_demo", refresh=True, timeout=40, attempts=2)
    result = client.get_json(GEOBOUNDARIES, allowed_hosts={"www.geoboundaries.org"})
    if result.status_code != 200:
        raise RuntimeError(f"geoBoundaries HTTP {result.status_code}")
    body = json.loads(result.body)
    return {
        "checked_at": _now(),
        "status": "available_not_used",
        "url": GEOBOUNDARIES,
        "licence": body.get("boundaryLicense"),
        "year": body.get("boundaryYearRepresented"),
        "rate_limit": "robots.txt Crawl-delay 10. One metadata request. The geometry file is not downloaded.",
        "detail": (
            "ADM2 metadata answered. The gazetteer uses the HDX COD-AB spreadsheet "
            "because it carries Thai district names and centroids. "
            f"Geometry URL was present: {bool(body.get('gjDownloadURL'))}."
        ),
    }


def refresh() -> dict:
    report = {}
    for name, loader in (
        ("gistda", load_gistda),
        ("open_meteo", load_open_meteo),
        ("gazetteer", load_gazetteer),
        ("places", load_places),
        ("rid", load_rid),
        ("tmd", load_tmd),
        ("geoboundaries", load_geoboundaries),
    ):
        payload, origin = loader(refresh=True)
        report[name] = {"origin": origin, "keys": sorted(payload)[:12]}
        print(f"{name}: {origin}")
    write_snapshot("status", {"checked_at": _now(), "refresh": report, "sources": source_cards()})
    publish_sim_places()
    return report


def source_cards() -> list[dict]:
    """Status rows for the docs and ``make sources-status``. Reads snapshots only."""
    gistda = read_snapshot("gistda") or {}
    meteo = read_snapshot("open_meteo") or {}
    gazetteer = read_snapshot("gazetteer") or {}
    places = read_snapshot("places") or {}
    rid = read_snapshot("rid") or {}
    tmd = read_snapshot("tmd") or {}
    geo = read_snapshot("geoboundaries") or {}
    open_api = gistda.get("open_api") or {}
    arcgis = gistda.get("arcgis") or {}
    return [
        {
            "id": "gistda_open_api",
            "status": open_api.get("status") or "missing",
            "url": GISTDA_FLOOD,
            "licence": "GISTDA open API. A key is required.",
            "rate_limit": "One unauthenticated probe when the key is unset.",
            "detail": open_api.get("detail") or "No snapshot yet.",
        },
        {
            "id": "gistda_arcgis",
            "status": arcgis.get("status") or "missing",
            "url": ARCGIS,
            "licence": "Public GISTDA MapServer.",
            "rate_limit": "Two count queries.",
            "detail": (
                f"Layer 0 count={arcgis.get('layer0_flood_extent_count')}. "
                f"Layer 1 count={arcgis.get('layer1_flood_risk_count')}."
            ),
        },
        {
            "id": "open_meteo",
            "status": "ok" if meteo.get("locations") else "missing",
            "url": OPEN_METEO_FORECAST,
            "licence": meteo.get("licence") or "CC BY 4.0",
            "rate_limit": meteo.get("rate_limit") or "",
            "detail": f"Town rows={len(meteo.get('locations') or [])}.",
        },
        {
            "id": "overpass_places",
            "status": "ok" if places.get("places") else "missing",
            "url": OVERPASS,
            "licence": places.get("licence") or "ODbL",
            "rate_limit": places.get("rate_limit") or "",
            "detail": f"Stored places={len(places.get('places') or [])}.",
        },
        {
            "id": "hdx_cod_ab",
            "status": "ok" if gazetteer.get("districts") else "missing",
            "url": "https://data.humdata.org/dataset/cod-ab-tha",
            "licence": gazetteer.get("licence") or "CC BY-IGO",
            "rate_limit": gazetteer.get("rate_limit") or "",
            "detail": f"ADM2 rows={len(gazetteer.get('districts') or [])}. Tambon geometry was not stored.",
        },
        {
            "id": "geoboundaries",
            "status": geo.get("status") or "missing",
            "url": GEOBOUNDARIES,
            "licence": geo.get("licence") or "",
            "rate_limit": geo.get("rate_limit") or "",
            "detail": geo.get("detail") or "",
        },
        {
            "id": "rid_dams",
            "status": "ok" if rid.get("dams") else "missing",
            "url": RID_DAMS,
            "licence": rid.get("licence") or "",
            "rate_limit": rid.get("rate_limit") or "",
            "detail": rid.get("scope") or "",
        },
        {
            "id": "tmd",
            "status": tmd.get("status") or "missing",
            "url": "https://data.tmd.go.th/",
            "licence": "Not stored.",
            "rate_limit": tmd.get("rate_limit") or "",
            "detail": tmd.get("detail") or "",
        },
    ]


def status_report() -> str:
    lines = ["Public demo sources (snapshots only, no network)"]
    for card in source_cards():
        lines.append(
            f"{card['id']}: {card['status']} | {card['url']} | {card['detail']}"
        )
    return "\n".join(lines)


def publish_sim_places() -> None:
    """Write the town page's place file from the snapshots. No network."""
    places = (read_snapshot("places") or {}).get("places") or []
    rid = read_snapshot("rid") or {}
    labels = {}
    for building_id, kind in LABEL_BUILDINGS.items():
        picked = _pick_label(places, kind)
        if picked:
            labels[building_id] = picked
    names = []
    for kind in ("hospital", "school", "temple", "fire_station"):
        picked = _pick_label(places, kind)
        if picked:
            names.append(picked["name_th"])
    note = (
        "Street names in this block stay placeholders. Public places in Lampang, "
        "Phrae, Nan, and Phayao are OpenStreetMap names"
        + (": " + ", ".join(names) + "." if names else ".")
        + " RID northern reservoir totals have no coordinates, so they are not pinned to a house."
    )
    body = {
        "note": note,
        "labels": labels,
        "places": places,
        "reservoirs": {
            "date": rid.get("date"),
            "scope": rid.get("scope"),
            "dams": rid.get("dams") or [],
        },
    }
    path = ROOT / "ui" / "sim" / "data" / "places.json"
    path.write_text(json.dumps(body, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _pick_label(places: list[dict], kind: str) -> dict | None:
    ranked = [row for row in places if row.get("kind") == kind and str(row.get("province") or "").startswith("Lampang")]
    if not ranked:
        ranked = [row for row in places if row.get("kind") == kind]

    def score(row: dict) -> tuple:
        name = row.get("name") or ""
        district = row.get("district") or ""
        value = 0
        if district.startswith("Mueang Lampang"):
            value += 8
        elif district.startswith("Mueang"):
            value += 4
        if kind == "school" and "บ้าน" in name:
            value -= 5
        if kind == "temple" and "บ้าน" in name:
            value -= 3
        if kind == "fire_station":
            value += min(len(name), 40) / 8
        return (value, -len(district), name)

    ranked.sort(key=score, reverse=True)
    if not ranked:
        return None
    row = ranked[0]
    return {"name_th": row.get("name_th") or row["name"], "name_en": row.get("name_en") or row["name"]}


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if "--refresh" in args:
        refresh()
    print(status_report())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
