"""GISTDA flood polygons.

The feature API needs GISTDA_API_KEY (environment or gitignored .env). The key
is never written to SQLite, cache URLs, or the status text. Without a key this
module records that fact and still loads the public ArcGIS risk layer.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone

from config.envfile import load_env_file
from config.settings import load_yaml
from ingest.common import OffHostError, PoliteClient, RobotsDisallowed, scrub
from ingest.db import connect, set_status

PORTAL = "gistdaportal.gistda.or.th"
MAPSERVER = (
    "https://gistdaportal.gistda.or.th/arcgis/rest/services/app/GISTDA_flood/MapServer"
)
GATEWAY = "api-gateway.gistda.or.th"
FEATURES = "https://api-gateway.gistda.or.th/api/2.0/resources/features/flood"
FREQ = "https://api-gateway.gistda.or.th/api/2.0/resources/features/flood-freq"
WINDOWS = {"1d": "1day", "3d": "3days", "7d": "7days", "30d": "30days"}
SIGNUP = (
    "GISTDA open API requires an API key. Put GISTDA_API_KEY in the environment "
    "or in the gitignored .env file. Do not commit it. Registration: "
    "https://api-gateway.gistda.or.th and https://api-gateway.gistda.or.th/v2. "
    "Feature paths: /api/2.0/resources/features/flood/{1day,3days,7days,30days} "
    "and /api/2.0/resources/features/flood-freq with api_key, limit, offset, pv_idn. "
    "Catalogue: https://opendata.gistda.or.th/dataset/flood-disaster-data. "
    "Contact: disaster@gistda.or.th."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ingest(refresh: bool) -> str:
    """Ingest GISTDA polygons. Returns a status detail string. Never prints the key."""
    load_env_file()
    _clear_own_rows()
    key = os.environ.get("GISTDA_API_KEY", "").strip()
    if not key:
        detail = "BLOCKED: " + SIGNUP + " The open API was not called."
        set_status(
            "gistda_open_api",
            fetched_at=_now(),
            row_count=0,
            status="blocked",
            detail=detail,
        )
    else:
        detail = _try_keyed_api(refresh, key)
    fallback = _arcgis(refresh)
    return detail + " " + fallback


def _clear_own_rows() -> None:
    with connect() as conn:
        conn.execute(
            """
            DELETE FROM flood_extent
            WHERE source = 'gistda-open-api'
               OR source LIKE '%GISTDA_flood/MapServer%'
            """
        )
        conn.execute("DELETE FROM repeat_flood WHERE source LIKE 'gistda%'")


def _try_keyed_api(refresh: bool, key: str) -> str:
    cfg = load_yaml("ingest.yaml").get("gistda") or {}
    page = int(cfg.get("page_limit", 100))
    extent_cap = int(cfg.get("max_extent_features_per_window", 800))
    repeat_cap = int(cfg.get("max_repeat_features", 400))
    provinces = [int(code) for code in cfg.get("province_codes") or []]
    client = PoliteClient("gistda", refresh=refresh, timeout=50, attempts=2)
    notes = [
        "GISTDA_API_KEY was read from the environment and was not written to "
        "the database, the cache URL, or this note."
    ]
    stored_extents = 0
    for window, slug in WINDOWS.items():
        url = f"{FEATURES}/{slug}"
        payload, error = _fetch(client, url, key, {"limit": 1, "offset": 0})
        if error:
            notes.append(f"{window} national: {error}")
            if error.startswith("HTTP 401") or error.startswith("HTTP 403"):
                break
            continue
        matched = _matched(payload)
        notes.append(f"{window} national numberMatched={matched}")
        if not matched:
            continue
        kept = _spread(client, key, url, window, provinces, extent_cap, page, "extent")
        stored_extents += kept
        notes.append(f"{window} stored={kept} cap={extent_cap} provinces={provinces}")
    active = _province_hits(client, key, f"{FEATURES}/7days")
    notes.append("7d numberMatched by province (nonzero only): " + (", ".join(active) or "none"))
    freq_payload, freq_error = _fetch(client, FREQ, key, {"limit": 1, "offset": 0})
    if freq_error:
        notes.append(f"flood-freq national: {freq_error}")
    else:
        notes.append(f"flood-freq national numberMatched={_matched(freq_payload)}")
    repeat_kept = _spread(client, key, FREQ, "repeat", provinces, repeat_cap, page, "repeat")
    notes.append(f"repeat stored={repeat_kept} cap={repeat_cap}")
    detail = " ".join(notes)
    set_status(
        "gistda_open_api",
        fetched_at=_now(),
        row_count=stored_extents,
        status="ok" if stored_extents or repeat_kept else "empty",
        detail=scrub(detail, key),
    )
    return scrub(detail, key)


def _spread(client, key, url, window, provinces, cap, page, kind) -> int:
    """Store up to `cap` features.

    Extents walk the province list and skip empties, so a window that only
    has water in the last configured province still stores that water.
    Repeat-flood rows are split evenly: every configured province has
    frequency polygons, and one province must not take the whole cap.
    """
    if not provinces or cap <= 0:
        return 0
    if kind == "repeat":
        return _spread_even(client, key, url, window, provinces, cap, page, kind)
    stored = 0
    for province in provinces:
        if stored >= cap:
            break
        offset = 0
        got = 0
        while stored < cap:
            limit = min(page, cap - stored)
            payload, error = _fetch(
                client,
                url,
                key,
                {"limit": limit, "offset": offset, "pv_idn": province},
            )
            if error:
                print(f"gistda {window} pv_idn={province} {error}", flush=True)
                break
            features = payload.get("features") or []
            if not features:
                break
            kept = _store_features(features, window, kind, limit)
            got += kept
            stored += kept
            offset += len(features)
            print(
                f"gistda {window} pv_idn={province} page_stored={kept} running={got}",
                flush=True,
            )
            if len(features) < limit or kept == 0:
                break
    return stored


def _spread_even(client, key, url, window, provinces, cap, page, kind) -> int:
    quota = cap // len(provinces)
    extra = cap % len(provinces)
    stored = 0
    for index, province in enumerate(provinces):
        limit_for = quota + (1 if index < extra else 0)
        if limit_for <= 0:
            continue
        offset = 0
        got = 0
        while got < limit_for:
            limit = min(page, limit_for - got)
            payload, error = _fetch(
                client,
                url,
                key,
                {"limit": limit, "offset": offset, "pv_idn": province},
            )
            if error or not payload:
                break
            features = payload.get("features") or []
            if not features:
                break
            kept = _store_features(features, window, kind, limit)
            got += kept
            stored += kept
            offset += len(features)
            if len(features) < limit or kept == 0:
                break
    return stored


def _fetch(client, url, key, params: dict) -> tuple[dict | None, str | None]:
    try:
        result = client.get_json(
            url,
            allowed_hosts={GATEWAY},
            params={**params, "api_key": key},
        )
    except (RobotsDisallowed, OffHostError, RuntimeError) as exc:
        return None, scrub(str(exc), key)
    if result.status_code != 200:
        return None, f"HTTP {result.status_code}"
    try:
        payload = json.loads(result.body)
    except json.JSONDecodeError:
        return None, "response was not JSON"
    if not isinstance(payload, dict):
        return None, "unexpected payload"
    return payload, None


def _province_hits(client, key: str, url: str) -> list[str]:
    """Count-only probe. Stores nothing. One feature page per province code."""
    hits = []
    for code in range(10, 97):
        payload, error = _fetch(client, url, key, {"limit": 1, "offset": 0, "pv_idn": code})
        if error or not payload:
            continue
        matched = _matched(payload) or 0
        if matched:
            hits.append(f"{code}:{matched}")
            print(f"gistda 7d scan pv_idn={code} numberMatched={matched}", flush=True)
    return hits


def _matched(payload: dict | None) -> int | None:
    if not payload:
        return None
    for name in ("numberMatched", "number_matched", "totalFeatures"):
        if payload.get(name) is not None:
            try:
                return int(payload[name])
            except (TypeError, ValueError):
                return None
    return None


def _store_features(features: list, window: str, kind: str, limit: int) -> int:
    stored = 0
    with connect() as conn:
        for feature in features:
            if stored >= limit:
                break
            if not isinstance(feature, dict):
                continue
            geom = feature.get("geometry")
            if not isinstance(geom, dict):
                continue
            props = {
                str(name).lower(): value
                for name, value in (feature.get("properties") or {}).items()
                if not str(name).startswith("_") and str(name).lower() not in {"mongo_id"}
            }
            object_id = props.get("objectid") or props.get("h3_address")
            if object_id in (None, ""):
                object_id = hashlib.sha256(
                    json.dumps(geom, sort_keys=True).encode()
                ).hexdigest()[:16]
            if kind == "repeat":
                freq = props.get("freq")
                try:
                    frequency = float(freq) if freq is not None and freq != "" else None
                except (TypeError, ValueError):
                    frequency = None
                conn.execute(
                    """
                    INSERT INTO repeat_flood (area_id, geometry, frequency, source)
                    VALUES (?, ?, ?, 'gistda-open-api')
                    """,
                    (f"{props.get('pv_idn')}-{object_id}", json.dumps(geom), frequency),
                )
            else:
                conn.execute(
                    """
                    INSERT INTO flood_extent
                        (event_id, date, geometry, source, duration_window, confidence)
                    VALUES (?, ?, ?, 'gistda-open-api', ?, NULL)
                    """,
                    (
                        f"gistda-{window}-{props.get('pv_idn')}-{object_id}",
                        None,
                        json.dumps(geom),
                        window,
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
        "they are not repeated-flood frequencies."
    )
    status = "ok" if stored else "empty"
    set_status(
        "gistda_arcgis",
        fetched_at=layer1.fetched_at if layer1.status_code == 200 else _now(),
        row_count=stored,
        status=status,
        detail=detail,
    )
    return detail
