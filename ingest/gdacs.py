"""GDACS Thailand flood events for August–December 2025.

robots.txt on www.gdacs.org sets Request-rate 1/60 and Visit-time 0400-0645 UTC.
The polite client enforces both. Outside that window this module records the
rule and does not call the event API.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from config.settings import load_yaml
from shapely.geometry import mapping

from ingest.common import OffHostError, PoliteClient, RobotsDisallowed, scrub
from ingest.db import connect, set_status
from ingest.geo import loads
from ingest.textutil import as_int, clip
from ingest.vectors import span_degrees

HOST = "www.gdacs.org"
LIST_URL = (
    "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
    "?eventlist=FL&country=THA&fromDate=2025-08-01&toDate=2025-12-31"
)
GEOMETRY_URL = "https://www.gdacs.org/gdacsapi/api/polygons/getgeometry"
EVENT_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventdata"
TERMS = (
    "GDACS data are published as free to use by the European Commission JRC. "
    "Terms: https://www.gdacs.org/Documents/2025/GDACS_API_quickstart_v2.pdf "
    "and https://www.gdacs.org/gdacsapi/swagger/index.html."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ingest(refresh: bool) -> str:
    cfg = load_yaml("ingest.yaml")
    max_span = float(cfg.get("max_stored_span_degrees", 4))
    client = PoliteClient(
        "gdacs", refresh=refresh, timeout=60, attempts=3, require_robots=True
    )
    try:
        listing = client.get_json(LIST_URL, allowed_hosts={HOST})
    except (RobotsDisallowed, OffHostError, RuntimeError) as exc:
        detail = (
            scrub(str(exc))
            + " Existing GDACS rows were left in place. "
            + TERMS
        )
        kept = _count()
        set_status(
            "gdacs",
            fetched_at=_now(),
            row_count=kept,
            status="blocked",
            detail=detail,
        )
        return detail
    if listing.status_code != 200:
        detail = f"BLOCKED: GDACS event list HTTP {listing.status_code}. Existing rows were left in place. {TERMS}"
        set_status("gdacs", fetched_at=listing.fetched_at, row_count=_count(), status="blocked", detail=detail)
        return detail
    _clear()
    features = _features(listing.body)
    thailand = [feature for feature in features if _is_thailand(feature)]
    reports = 0
    polygons = 0
    notes = [
        f"list features={len(features)} kept for Thailand={len(thailand)}. {TERMS} "
        "The client read robots.txt as text, enforced Request-rate 1/60 and "
        "Visit-time 0400-0645 UTC, and would have refused the call if that file "
        "could not be read. "
        + (
            "The list body came from the local cache of a visit-window fetch."
            if listing.from_cache
            else "The list was fetched inside the visit window."
        )
    ]
    for feature in thailand:
        props = _props(feature)
        event_id = str(props.get("eventid") or "")
        if not event_id:
            continue
        glide = _glide(props)
        reports += _store_report(props, glide, feature.get("geometry"))
        stored, note = _store_geometry(client, props, glide, max_span, feature.get("geometry"))
        polygons += stored
        if note:
            notes.append(note)
        print(f"gdacs event {event_id} polygons={stored}", flush=True)
    detail = (
        f"Reports={reports}. Flood polygons stored={polygons}. " + " ".join(notes)
    )
    set_status(
        "gdacs",
        fetched_at=_now(),
        row_count=reports,
        status="ok" if reports else "empty",
        detail=detail,
    )
    return detail


def _count() -> int:
    with connect() as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM disaster_report WHERE source = 'gdacs'"
        ).fetchone()
    return int(row["n"])


def _clear() -> None:
    with connect() as conn:
        conn.execute("DELETE FROM disaster_report WHERE source = 'gdacs'")
        conn.execute("DELETE FROM flood_extent WHERE source = 'gdacs'")


def _features(body: bytes) -> list[dict]:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return []
    if isinstance(payload, dict):
        features = payload.get("features")
        if isinstance(features, list):
            return [item for item in features if isinstance(item, dict)]
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    return []


def _props(feature: dict) -> dict:
    raw = feature.get("properties") if isinstance(feature.get("properties"), dict) else feature
    return {str(key).lower(): value for key, value in raw.items()}


def _is_thailand(feature: dict) -> bool:
    props = _props(feature)
    iso = str(props.get("iso3") or "").upper()
    if iso == "THA":
        return True
    country = str(props.get("country") or "")
    if "thailand" in country.lower():
        return True
    affected = props.get("affectedcountries")
    if isinstance(affected, list):
        for item in affected:
            if isinstance(item, dict) and str(item.get("iso3") or "").upper() == "THA":
                return True
            if isinstance(item, str) and item.upper() == "THA":
                return True
    if isinstance(affected, str) and "THA" in affected.upper():
        return True
    return False


def _glide(props: dict) -> str | None:
    for key in ("glide", "glidenumber", "glide_id"):
        value = props.get(key)
        if isinstance(value, str) and "-" in value:
            return value.strip()
    return None


def _store_report(props: dict, glide: str | None, geometry: object) -> int:
    event_key = str(props.get("eventid") or "")
    episode = str(props.get("episodeid") or "")
    report_id = f"gdacs-{event_key}-{episode}" if episode else f"gdacs-{event_key}"
    name = props.get("name") or props.get("eventname") or f"GDACS flood {event_key}"
    description = props.get("description") or props.get("htmldescription") or ""
    severity = props.get("severitydata") if isinstance(props.get("severitydata"), dict) else {}
    severity_text = ""
    if isinstance(severity, dict):
        severity_text = str(severity.get("severitytext") or severity.get("severity") or "")
    summary = clip(
        " ".join(
            part
            for part in (
                str(name),
                f"alert {props.get('alertlevel')}" if props.get("alertlevel") else "",
                severity_text,
                str(description),
            )
            if part
        )
    )
    url = ""
    url_field = props.get("url")
    if isinstance(url_field, dict):
        url = str(url_field.get("report") or url_field.get("details") or "")
    elif isinstance(url_field, str):
        url = url_field
    point = _point(geometry)
    if point and "point" not in summary.lower():
        summary = clip(summary + f" GDACS point {point[0]:.3f},{point[1]:.3f}.")
    with connect() as conn:
        conn.execute(
            """
            INSERT INTO disaster_report (
                report_id, event_id, source, published_at, title, summary,
                affected_people, affected_households, fatalities, provinces,
                assistance_type, url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_id,
                glide or f"gdacs-{event_key}",
                "gdacs",
                str(props.get("fromdate") or "")[:10] or None,
                clip(str(name), 180),
                summary,
                as_int(props.get("population")),
                None,
                None,
                "Thailand",
                str(props.get("alertlevel") or "") or None,
                url or f"https://www.gdacs.org/report.aspx?eventtype=FL&eventid={event_key}",
            ),
        )
    return 1


def _store_geometry(client, props, glide, max_span: float, list_geometry: object) -> tuple[int, str]:
    event_key = str(props.get("eventid") or "")
    payload = None
    error = None
    try:
        result = client.get_json(
            GEOMETRY_URL,
            allowed_hosts={HOST},
            params={"eventtype": "FL", "eventid": event_key},
        )
        if result.status_code == 200:
            payload = json.loads(result.body)
        else:
            error = f"geometry HTTP {result.status_code}"
    except (RobotsDisallowed, OffHostError, RuntimeError, json.JSONDecodeError) as exc:
        error = scrub(str(exc))
    features = _features(json.dumps(payload).encode()) if isinstance(payload, (dict, list)) else []
    chosen = _affected(features)
    if not chosen and _is_polygon(list_geometry):
        chosen = [list_geometry]
    if not chosen and error:
        # One fallback, still inside the rate limit.
        try:
            detail = client.get_json(
                EVENT_URL,
                allowed_hosts={HOST},
                params={"eventtype": "FL", "eventid": event_key},
            )
            if detail.status_code == 200:
                fallback = _features(detail.body)
                chosen = _affected(fallback) or [
                    feature.get("geometry")
                    for feature in fallback
                    if _is_polygon(feature.get("geometry"))
                ]
        except (RobotsDisallowed, OffHostError, RuntimeError):
            pass
    stored = 0
    skipped = 0
    with connect() as conn:
        for geometry in chosen:
            if not _is_polygon(geometry):
                continue
            geometry = _repair(geometry)
            if geometry is None:
                skipped += 1
                continue
            try:
                wide = span_degrees(geometry)
            except Exception:
                skipped += 1
                continue
            if wide > max_span:
                skipped += 1
                continue
            conn.execute(
                """
                INSERT INTO flood_extent
                    (event_id, date, geometry, source, duration_window, confidence)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    glide or f"gdacs-{event_key}",
                    str(props.get("fromdate") or "")[:10] or None,
                    json.dumps(geometry),
                    "gdacs",
                    "observed",
                    None,
                ),
            )
            stored += 1
    note = ""
    if skipped:
        note = (
            f"event {event_key}: skipped {skipped} geometry features wider than "
            f"{max_span:g} degrees or unreadable."
        )
    elif error and not stored:
        note = f"event {event_key}: {error}"
    return stored, note


def _affected(features: list[dict]) -> list:
    polygons = []
    affected = []
    for feature in features:
        geometry = feature.get("geometry")
        if not _is_polygon(geometry):
            continue
        props = _props(feature)
        kind = str(props.get("class") or "").lower()
        polygons.append(geometry)
        if kind in {"poly_affected", "affected"}:
            affected.append(geometry)
    return affected or polygons


def _is_polygon(geometry: object) -> bool:
    return isinstance(geometry, dict) and geometry.get("type") in {"Polygon", "MultiPolygon"}


def _repair(geometry: dict) -> dict | None:
    """Drop empty rings. GDACS occasionally emits a component with too few points."""
    try:
        geom = loads(json.dumps(geometry))
    except Exception:
        return None
    if not geom.is_valid:
        geom = geom.buffer(0)
    if geom.is_empty or geom.geom_type not in {"Polygon", "MultiPolygon"}:
        return None
    return mapping(geom)


def _point(geometry: object) -> tuple[float, float] | None:
    if not isinstance(geometry, dict) or geometry.get("type") != "Point":
        return None
    coords = geometry.get("coordinates") or []
    if len(coords) < 2:
        return None
    lon, lat = float(coords[0]), float(coords[1])
    return lat, lon
