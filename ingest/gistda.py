"""GISTDA flood polygons.

The documented open API needs an API key. Without one this module records the
sign-up steps and falls back to the public ArcGIS MapServer only.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from ingest.common import OffHostError, PoliteClient, RobotsDisallowed
from ingest.db import connect, set_status

PORTAL = "gistdaportal.gistda.or.th"
MAPSERVER = (
    "https://gistdaportal.gistda.or.th/arcgis/rest/services/app/GISTDA_flood/MapServer"
)
GATEWAY = "api-gateway.gistda.or.th"
SIGNUP = (
    "GISTDA open API requires an API key. Sign-up steps: "
    "1) Open https://api-gateway.gistda.or.th (registration is also described at "
    "https://api-gateway.gistda.or.th/v2). "
    "2) Create an API key. "
    "3) Export it as GISTDA_API_KEY in the environment (do not commit it). "
    "4) Re-run `make ingest-refresh`. "
    "Documented extent URL pattern: "
    "https://api-gateway.gistda.or.th/api/2.0/resources/gi-service/v1.0/disasters/"
    "flood-extent-1day?lat={latitude}&lon={longitude}&api_key=REDACTED "
    "(same family for 3, 7 and 30 day windows, plus repeated-flood areas). "
    "Catalogue: https://opendata.gistda.or.th/dataset/flood-disaster-data "
    "and https://disaster.gistda.or.th/services/open-api. "
    "Contact published on the catalogue: disaster@gistda.or.th."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ingest(refresh: bool) -> str:
    """Ingest public flood polygons. Returns a status detail string."""
    key = os.environ.get("GISTDA_API_KEY", "").strip()
    if not key:
        detail = (
            "BLOCKED: " + SIGNUP + " "
            "The open API was not called. Falling back to the public ArcGIS MapServer."
        )
    else:
        detail = _try_keyed_api(refresh, key)

    fallback = _arcgis(refresh)
    combined = detail + " " + fallback
    return combined


def _try_keyed_api(refresh: bool, key: str) -> str:
    """Call the documented extent endpoints. The key is never written to disk."""
    client = PoliteClient("gistda", refresh=refresh, timeout=40)
    windows = {
        "1d": "flood-extent-1day",
        "3d": "flood-extent-3day",
        "7d": "flood-extent-7day",
        "30d": "flood-extent-30day",
    }
    notes = []
    # A single public probe point is not a chosen demo event. The keyed API,
    # per its published URL, is a point query. Without a human demo anchor we
    # still ask the API at the centroid of the public MapServer extent only
    # when a key exists. That centroid is data, not a household.
    lat, lon = 18.3, 100.0
    for window, slug in windows.items():
        url = (
            "https://api-gateway.gistda.or.th/api/2.0/resources/gi-service/v1.0/"
            f"disasters/{slug}"
        )
        try:
            result = client.get_json(
                url,
                allowed_hosts={GATEWAY},
                params={"lat": lat, "lon": lon, "api_key": key},
            )
        except (RobotsDisallowed, OffHostError) as exc:
            notes.append(f"{window}: {exc}")
            continue
        if result.status_code != 200:
            notes.append(f"{window}: HTTP {result.status_code}")
            continue
        stored = _store_keyed_payload(result.body, window)
        notes.append(f"{window}: stored {stored}")
    set_status(
        "gistda_open_api",
        fetched_at=_now(),
        row_count=0,
        status="keyed",
        detail="; ".join(notes) or "keyed API returned no features",
    )
    return "Keyed API attempted. " + "; ".join(notes)


def _store_keyed_payload(body: bytes, window: str) -> int:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return 0
    features = []
    if isinstance(payload, dict):
        features = payload.get("features") or payload.get("results") or []
    stored = 0
    with connect() as conn:
        for feature in features:
            geom = feature.get("geometry") if isinstance(feature, dict) else None
            if not geom:
                continue
            props = feature.get("properties") or {}
            conn.execute(
                """
                INSERT INTO flood_extent
                    (event_id, date, geometry, source, duration_window, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    str(props.get("event_id") or props.get("id") or f"gistda-{window}"),
                    props.get("date") or props.get("datetime"),
                    json.dumps(geom),
                    "gistda-open-api",
                    window,
                    props.get("confidence"),
                ),
            )
            stored += 1
    return stored


def _arcgis(refresh: bool) -> str:
    client = PoliteClient("gistda", refresh=refresh, timeout=60)
    try:
        layer0 = client.get_json(
            f"{MAPSERVER}/0/query",
            allowed_hosts={PORTAL},
            params={"where": "1=1", "returnCountOnly": "true", "f": "json"},
        )
        layer1 = client.get_json(
            f"{MAPSERVER}/1/query",
            allowed_hosts={PORTAL},
            params={
                "where": "1=1",
                "outFields": "objectid,f_area,tam_rai,org_code",
                "f": "geojson",
                "outSR": "4326",
                "resultRecordCount": "1000",
            },
        )
    except RobotsDisallowed as exc:
        set_status(
            "gistda_arcgis",
            fetched_at=_now(),
            row_count=0,
            status="blocked",
            detail=str(exc),
        )
        return f"ArcGIS fallback blocked by robots.txt: {exc}"
    except OffHostError as exc:
        set_status(
            "gistda_arcgis",
            fetched_at=_now(),
            row_count=0,
            status="blocked",
            detail=str(exc),
        )
        return f"ArcGIS fallback stopped: {exc}"

    layer0_count = None
    if layer0.status_code == 200:
        try:
            layer0_count = json.loads(layer0.body).get("count")
        except json.JSONDecodeError:
            layer0_count = None
    stored = 0
    if layer1.status_code == 200:
        payload = json.loads(layer1.body)
        features = payload.get("features") or []
        with connect() as conn:
            for feature in features:
                geom = feature.get("geometry")
                if not geom:
                    continue
                props = feature.get("properties") or {}
                conn.execute(
                    """
                    INSERT INTO flood_extent
                        (event_id, date, geometry, source, duration_window, confidence)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        f"gistda-mapserver-layer1-{props.get('objectid')}",
                        layer1.fetched_at[:10],
                        json.dumps(geom),
                        MAPSERVER + "/1",
                        "flood_risk_layer",
                        None,
                    ),
                )
                stored += 1
    detail = (
        f"ArcGIS MapServer public fallback. Layer 0 (flood-affected extent) count="
        f"{layer0_count}. Layer 1 (flood-risk polygons) stored={stored} with "
        "duration_window=flood_risk_layer. These are not 1/3/7/30-day extents and "
        "they are not repeated-flood frequencies. repeat_flood was not filled "
        "because the frequency API needs the GISTDA key."
    )
    status = "ok" if stored else "empty"
    set_status(
        "gistda_arcgis",
        fetched_at=layer1.fetched_at if layer1.status_code == 200 else _now(),
        row_count=stored,
        status=status,
        detail=detail,
    )
    set_status(
        "gistda_open_api",
        fetched_at=_now(),
        row_count=0,
        status="blocked",
        detail=SIGNUP,
    )
    return detail
