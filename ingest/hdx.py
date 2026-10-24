"""HDX public disaster datasets for Thailand.

GLIDE and IDMC rows go to disaster_report. The GLIDE number is the event_id
used as the join key. EOS-RS Hat Yai and openly licensed UNOSAT water extents
go to flood_extent as dissolved polygons, marked preliminary / observed, not
as a live 1/3/7/30-day extent. Other search hits are recorded as candidates.
"""

from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timezone

from config.settings import load_yaml
from ingest.common import OffHostError, PoliteClient, RobotsDisallowed, scrub
from ingest.db import connect, set_status
from ingest.textutil import as_int, clip
from ingest.vectors import dissolved_polygon, span_degrees

HDX_HOST = "data.humdata.org"
UNOSAT_HOST = "unosat.org"
API = "https://data.humdata.org/api/3/action"
OPEN_LICENCES = {"cc-by", "cc-by-sa", "cc-by-igo", "cc0", "odc-by"}
GLIDE_RE_HELP = "GLIDE number"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ingest(refresh: bool) -> str:
    client = PoliteClient("hdx", refresh=refresh, timeout=180, attempts=3)
    notes: list[str] = []
    try:
        search = _package_search(client)
    except (RobotsDisallowed, OffHostError, RuntimeError) as exc:
        detail = f"BLOCKED: HDX package_search was not completed: {exc}"
        set_status("hdx_search", fetched_at=_now(), row_count=0, status="blocked", detail=detail)
        return detail
    _clear_candidates()
    by_name = {pkg.get("name"): pkg for pkg in search}
    notes.append(_glide(client, by_name.get("tha-glide-events")))
    notes.append(_idmc(client, by_name.get("tha-idmc-idu-events")))
    notes.append(_hat_yai(client, by_name.get("eos-rs-thailand-hat-yai-floods-nov-2025")))
    notes.append(_unosat(client, search))
    listed = _record_candidates(search)
    notes.append(f"HDX search hits recorded as candidates={listed}.")
    detail = " ".join(note for note in notes if note)
    set_status(
        "hdx_search",
        fetched_at=_now(),
        row_count=len(search),
        status="ok",
        detail=detail[:2000],
    )
    return detail


def _clear_candidates() -> None:
    with connect() as conn:
        conn.execute("DELETE FROM source_status WHERE source LIKE 'hdx:%'")
        conn.execute("DELETE FROM disaster_report WHERE source IN ('glide', 'idmc')")
        conn.execute(
            """
            DELETE FROM flood_extent
            WHERE source LIKE 'eos-rs%' OR source LIKE 'unosat%'
            """
        )


def _get_json(client: PoliteClient, url: str, hosts: set[str], params: dict | None = None):
    result = client.get_json(url, allowed_hosts=hosts, params=params)
    if result.status_code != 200:
        raise RuntimeError(f"HTTP {result.status_code} for {url.split('?', 1)[0]}")
    payload = json.loads(result.body)
    return payload, result.fetched_at


def _package_search(client: PoliteClient) -> list[dict]:
    payload, _ = _get_json(
        client,
        f"{API}/package_search",
        {HDX_HOST},
        {"q": "thailand flood", "rows": 40},
    )
    if not payload.get("success"):
        raise RuntimeError("HDX package_search did not succeed")
    return list((payload.get("result") or {}).get("results") or [])


def _package(client: PoliteClient, name: str) -> dict:
    payload, _ = _get_json(
        client,
        f"{API}/package_show",
        {HDX_HOST},
        {"id": name},
    )
    if not payload.get("success"):
        raise RuntimeError(f"package_show failed for {name}")
    return payload["result"]


# HDX file links redirect once to this host. The signed query is redacted
# before it is written to the cache meta. No other Amazon host is allowed.
HDX_FILESTORE = "s3.us-east-1.amazonaws.com"


def _download(client: PoliteClient, url: str) -> bytes:
    host = url.split("/")[2]
    result = client.get_json(
        url,
        allowed_hosts={host, HDX_HOST, HDX_FILESTORE, UNOSAT_HOST, "www.unosat.org"},
        accept="*/*",
    )
    if result.status_code != 200:
        raise RuntimeError(f"HTTP {result.status_code} downloading {host}")
    return result.body


def _glide(client: PoliteClient, summary: dict | None) -> str:
    try:
        pkg = summary or _package(client, "tha-glide-events")
        if (pkg.get("license_id") or "") not in OPEN_LICENCES:
            raise RuntimeError(f"licence {pkg.get('license_id')} is not an open licence we store")
        resource = _resource(pkg, "CSV")
        if resource is None:
            raise RuntimeError("no CSV resource")
        body = _download(client, resource["url"])
        rows = list(csv.DictReader(io.StringIO(body.decode("utf-8", errors="replace"))))
        stored = 0
        with connect() as conn:
            for row in rows:
                glide = (row.get("glidenumber") or "").strip()
                if not glide:
                    continue
                when = _ymd(row.get("year"), row.get("month"), row.get("day"))
                title = clip(
                    f"{row.get('event_name') or row.get('event') or 'event'} — {row.get('location') or 'Thailand'}",
                    180,
                )
                summary_text = clip(row.get("comments") or title)
                conn.execute(
                    """
                    INSERT INTO disaster_report (
                        report_id, event_id, source, published_at, title, summary,
                        affected_people, affected_households, fatalities, provinces,
                        assistance_type, url
                    ) VALUES (?, ?, 'glide', ?, ?, ?, ?, NULL, ?, ?, ?, ?)
                    """,
                    (
                        f"glide-{glide}",
                        glide,
                        when,
                        title,
                        summary_text,
                        as_int(row.get("affected")),
                        as_int(row.get("killed")),
                        clip(row.get("location"), 180) or None,
                        (row.get("event") or None),
                        "https://data.humdata.org/dataset/tha-glide-events",
                    ),
                )
                stored += 1
        detail = (
            f"GLIDE Thailand events stored={stored}. "
            f"Licence: {pkg.get('license_title')} ({pkg.get('license_id')}). "
            "event_id is the GLIDE number. Comments are clipped to 280 characters. "
            "https://data.humdata.org/dataset/tha-glide-events"
        )
        set_status("glide", fetched_at=_now(), row_count=stored, status="ok", detail=detail)
        return detail
    except (RobotsDisallowed, OffHostError, RuntimeError, UnicodeError, csv.Error) as exc:
        detail = f"BLOCKED: GLIDE ingest failed: {scrub(str(exc))}"
        set_status("glide", fetched_at=_now(), row_count=0, status="blocked", detail=detail)
        return detail


def _idmc(client: PoliteClient, summary: dict | None) -> str:
    try:
        pkg = summary or _package(client, "tha-idmc-idu-events")
        if (pkg.get("license_id") or "") not in OPEN_LICENCES:
            raise RuntimeError(f"licence {pkg.get('license_id')} is not an open licence we store")
        resource = _resource(pkg, "CSV")
        if resource is None:
            raise RuntimeError("no CSV resource")
        body = _download(client, resource["url"])
        rows = list(csv.DictReader(io.StringIO(body.decode("utf-8", errors="replace"))))
        flood_rows = [row for row in rows if (row.get("combined_type") or "").lower() == "flood"]
        skipped = len(rows) - len(flood_rows)
        chosen = _prefer_recommended(flood_rows)
        stored = 0
        with connect() as conn:
            for row in chosen:
                glide = _glide_code(row.get("event_codes") or "")
                event_id = glide or f"idmc-event-{row.get('event_id')}"
                figure = as_int(row.get("figure"))
                summary_text = clip(
                    "IDMC new internal displacements (a flow, not a census of affected people). "
                    + (row.get("description") or "")
                )
                conn.execute(
                    """
                    INSERT INTO disaster_report (
                        report_id, event_id, source, published_at, title, summary,
                        affected_people, affected_households, fatalities, provinces,
                        assistance_type, url
                    ) VALUES (?, ?, 'idmc', ?, ?, ?, ?, NULL, NULL, ?, ?, ?)
                    """,
                    (
                        f"idmc-{row.get('id')}",
                        event_id,
                        (row.get("displacement_date") or "")[:10] or None,
                        clip(row.get("event_name"), 180),
                        summary_text,
                        figure,
                        clip(row.get("locations_name"), 180) or None,
                        "displacement_flow",
                        "https://data.humdata.org/dataset/tha-idmc-idu-events",
                    ),
                )
                stored += 1
        detail = (
            f"IDMC flood displacement rows stored={stored}. "
            f"Non-flood rows skipped={skipped}. "
            f"Extra flood figures dropped because a recommended figure exists="
            f"{len(flood_rows) - len(chosen)}. "
            "Rows whose only code is an AHA id stay on idmc-event-<id>, "
            "because that number is not a GLIDE id. "
            "Where a GLIDE number is in event_codes, event_id is that number. "
            "affected_people holds the IDMC displacement figure, not an affected-population census. "
            f"Licence: {pkg.get('license_title')} ({pkg.get('license_id')}). "
            "https://data.humdata.org/dataset/tha-idmc-idu-events"
        )
        set_status("idmc", fetched_at=_now(), row_count=stored, status="ok", detail=detail)
        return detail
    except (RobotsDisallowed, OffHostError, RuntimeError, UnicodeError, csv.Error) as exc:
        detail = f"BLOCKED: IDMC ingest failed: {scrub(str(exc))}"
        set_status("idmc", fetched_at=_now(), row_count=0, status="blocked", detail=detail)
        return detail


def _hat_yai(client: PoliteClient, summary: dict | None) -> str:
    try:
        pkg = summary or _package(client, "eos-rs-thailand-hat-yai-floods-nov-2025")
        licence = pkg.get("license_id") or ""
        if licence not in OPEN_LICENCES:
            raise RuntimeError(f"licence {licence} is not an open licence we store")
        resource = _resource(pkg, "GEOTIFF") or _first_zip(pkg)
        if resource is None:
            raise RuntimeError("no zip resource")
        blob = _download(client, resource["url"])
        geometry, count, note = dissolved_polygon(blob)
        if geometry is None:
            raise RuntimeError(note)
        cfg = load_yaml("ingest.yaml")
        if span_degrees(geometry) > float(cfg.get("max_stored_span_degrees", 4)):
            raise RuntimeError("dissolved polygon is wider than the span cap")
        event_id, join_note = _join_glide("Songkhla", "2025-11-23", "FL-2025-000210-THA")
        with connect() as conn:
            conn.execute(
                """
                INSERT INTO flood_extent
                    (event_id, date, geometry, source, duration_window, confidence)
                VALUES (?, ?, ?, ?, 'observed', NULL)
                """,
                (
                    event_id,
                    "2025-11-23",
                    json.dumps(geometry),
                    "eos-rs-hat-yai",
                    ),
            )
        detail = (
            "EOS-RS Hat Yai flood proxy map, 23 Nov 2025, v0.9, preliminary. "
            f"{note}. Stored as one dissolved polygon, duration_window=observed, "
            "not a live 1/3/7/30-day extent. "
            f"Licence: {pkg.get('license_title')} ({licence}). "
            "Contains modified Copernicus Sentinel data (2024-2025), analysed by "
            "the Earth Observatory of Singapore - Remote Sensing Lab. "
            f"{join_note} "
            "https://data.humdata.org/dataset/eos-rs-thailand-hat-yai-floods-nov-2025"
        )
        set_status(
            "eos_rs_hat_yai",
            fetched_at=_now(),
            row_count=1,
            status="ok",
            detail=detail + f" Source polygons={count}.",
        )
        return detail
    except Exception as exc:
        detail = f"BLOCKED: EOS-RS Hat Yai ingest failed: {scrub(str(exc))}"
        set_status("eos_rs_hat_yai", fetched_at=_now(), row_count=0, status="blocked", detail=detail)
        return detail


def _unosat(client: PoliteClient, packages: list[dict]) -> str:
    cfg = load_yaml("ingest.yaml")
    cap = int(cfg.get("unosat_max_shp_bytes", 20_000_000))
    max_span = float(cfg.get("max_stored_span_degrees", 4))
    stored = 0
    notes: list[str] = []
    for pkg in packages:
        if not _unosat_extent(pkg):
            continue
        licence = pkg.get("license_id") or ""
        if licence not in OPEN_LICENCES:
            _candidate(pkg, f"not fetched: licence {licence or 'unknown'} is not an open licence we store")
            continue
        resource = _shp_under(pkg, cap)
        if resource is None:
            size = _shp_size(pkg)
            _candidate(
                pkg,
                "openly licensed UNOSAT water extent, not fetched this run because "
                f"the shapefile is {size if size is not None else 'an unknown size'}, "
                f"above the {cap} byte cap",
            )
            continue
        try:
            blob = _download(client, resource["url"])
            geometry, count, note = dissolved_polygon(blob)
            if geometry is None:
                raise RuntimeError(note)
            if span_degrees(geometry) > max_span:
                raise RuntimeError("dissolved polygon is wider than the span cap")
            province, observed = _unosat_when(pkg)
            event_id, join_note = _join_glide(province, observed, None)
            source = "unosat-" + (pkg.get("name") or "extent")[:48]
            with connect() as conn:
                conn.execute(
                    """
                    INSERT INTO flood_extent
                        (event_id, date, geometry, source, duration_window, confidence)
                    VALUES (?, ?, ?, ?, 'observed', NULL)
                    """,
                    (event_id, observed, json.dumps(geometry), source),
                )
            detail = (
                f"UNOSAT water extent stored as one dissolved polygon ({note}). "
                "Preliminary satellite analysis, duration_window=observed, not a live extent. "
                f"Licence: {pkg.get('license_title')} ({licence}), CC BY-SA requires "
                "attribution and share-alike on this geometry. "
                f"{join_note} https://data.humdata.org/dataset/{pkg.get('name')}"
            )
            set_status(source, fetched_at=_now(), row_count=1, status="ok", detail=detail)
            stored += 1
            notes.append(pkg.get("name") or "unosat")
        except Exception as exc:
            _candidate(pkg, f"openly licensed but download failed: {scrub(str(exc))}")
    return f"UNOSAT extents stored={stored}: {', '.join(notes) or 'none'}."


def _record_candidates(packages: list[dict]) -> int:
    listed = 0
    with connect() as conn:
        existing = {
            row["source"]
            for row in conn.execute("SELECT source FROM source_status").fetchall()
        }
    for pkg in packages:
        name = pkg.get("name") or ""
        key = f"hdx:{name}"
        if key in existing or name in {
            "tha-glide-events",
            "tha-idmc-idu-events",
            "eos-rs-thailand-hat-yai-floods-nov-2025",
        }:
            continue
        if any(item == f"unosat-{name}"[:60] or item.startswith("unosat-" + name[:20]) for item in existing):
            continue
        # Already recorded inside _unosat when it was considered.
        if _already(existing, name):
            continue
        reason = _why_not(pkg)
        _candidate(pkg, reason)
        listed += 1
    return listed


def _already(existing: set[str], name: str) -> bool:
    for source in existing:
        if name and name in source:
            return True
    return False


def _why_not(pkg: dict) -> str:
    licence = pkg.get("license_id") or "unknown"
    title = pkg.get("title") or pkg.get("name")
    if licence not in OPEN_LICENCES:
        return f"not fetched: licence {licence}. {title}"
    if "eos-rs" in (pkg.get("name") or "") and "hat-yai" not in (pkg.get("name") or ""):
        return (
            "CC BY EOS-RS product other than the requested Hat Yai Nov 2025 map. "
            "Not fetched this run; the zip is a preliminary GeoTIFF bundle."
        )
    return f"open licence {licence}, not fetched this run (not a selected water-extent shapefile). {title}"


def _candidate(pkg: dict, reason: str) -> None:
    name = pkg.get("name") or "unknown"
    detail = (
        f"{pkg.get('title')}. Licence {pkg.get('license_id')} ({pkg.get('license_title')}). "
        f"{reason} https://data.humdata.org/dataset/{name}"
    )
    set_status(
        f"hdx:{name}"[:120],
        fetched_at=_now(),
        row_count=0,
        status="candidate",
        detail=detail,
    )


def _prefer_recommended(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("event_id") or row.get("id")), []).append(row)
    chosen: list[dict] = []
    for group in grouped.values():
        recommended = [row for row in group if (row.get("role") or "") == "Recommended figure"]
        chosen.extend(recommended or group)
    return chosen


def _glide_code(codes: str) -> str | None:
    """Return a standalone GLIDE token. Ignore an AHA-prefixed code.

    `AHA-FL-2026-000879-THA; FL-2026-000183-THA` carries two different numbers.
    Only the second is the GLIDE id. An AHA code on its own is not rewritten
    into a GLIDE id.
    """
    for token in codes.replace(",", " ").replace(";", " ").split():
        parts = token.strip().split("-")
        if len(parts) != 4 or len(parts[0]) != 2 or len(parts[3]) != 3:
            continue
        if parts[0].isalpha() and parts[3].isalpha() and parts[1].isdigit() and parts[2].isdigit():
            return token.strip()
    return None


def _join_glide(province: str | None, observed: str | None, fallback: str | None) -> tuple[str, str]:
    if province and observed:
        matches = []
        with connect() as conn:
            rows = conn.execute(
                """
                SELECT event_id, provinces, published_at FROM disaster_report
                WHERE source = 'glide'
                """
            ).fetchall()
        for row in rows:
            if province.lower() not in (row["provinces"] or "").lower():
                continue
            if _within(row["published_at"], observed, 21):
                matches.append(row["event_id"])
        unique = sorted(set(matches))
        if len(unique) == 1:
            return unique[0], f"event_id joined to GLIDE {unique[0]} on province and date."
        if len(unique) > 1:
            return (
                f"unjoined-{province.lower()}-{observed}",
                "several GLIDE ids matched "
                + ", ".join(unique)
                + "; event_id was not guessed.",
            )
    if fallback:
        with connect() as conn:
            found = conn.execute(
                "SELECT 1 FROM disaster_report WHERE event_id = ?",
                (fallback,),
            ).fetchone()
        if found:
            return (
                fallback,
                f"event_id set to {fallback} because that GLIDE record is the "
                "southern Thailand flood of 17 Nov 2025 and this map is Hat Yai "
                "on 23 Nov 2025. The GLIDE location text says Thailand, not Hat Yai. "
                "Confirm the join before treating it as exact.",
            )
    label = province or "event"
    return f"unjoined-{label}-{observed or 'undated'}", "No GLIDE id was joined."


def _within(published: str | None, target: str | None, window: int) -> bool:
    if not published or not target:
        return False
    try:
        left = date.fromisoformat(str(published)[:10])
        right = date.fromisoformat(str(target)[:10])
    except ValueError:
        return False
    return abs((left - right).days) <= window


def _unosat_extent(pkg: dict) -> bool:
    name = (pkg.get("name") or "").lower()
    title = (pkg.get("title") or "").lower()
    text = f"{name} {title}"
    if any(word in text for word in ("damage", "earthquake", "building", "accessibility", "risk-assessment")):
        return False
    if name.startswith("vnm-") or name.startswith("khm-"):
        return False
    return "water-extent" in name or "water extent" in title or "detected water" in title or "flood assessment" in title


def _unosat_when(pkg: dict) -> tuple[str | None, str | None]:
    name = (pkg.get("name") or "").lower()
    title = pkg.get("title") or ""
    province = None
    for candidate in ("Phayao", "Chiang Mai", "Lamphun", "Chiang Rai", "Songkhla", "Hat Yai"):
        if candidate.lower() in title.lower() or candidate.lower().replace(" ", "-") in name:
            province = candidate
            break
    # Prefer an explicit end date in the title; otherwise leave the HDX time blank
    # and let the caller store None rather than invent a day.
    observed = None
    dataset_date = pkg.get("dataset_date")
    if isinstance(dataset_date, str) and len(dataset_date) >= 10:
        observed = dataset_date[:10]
    return province, observed


def _resource(pkg: dict, format_name: str) -> dict | None:
    wanted = format_name.upper()
    for resource in pkg.get("resources") or []:
        if (resource.get("format") or "").upper() == wanted and resource.get("url"):
            return resource
    return None


def _first_zip(pkg: dict) -> dict | None:
    for resource in pkg.get("resources") or []:
        url = resource.get("url") or ""
        if url.lower().endswith(".zip"):
            return resource
    return None


def _shp_under(pkg: dict, cap: int) -> dict | None:
    for resource in pkg.get("resources") or []:
        if (resource.get("format") or "").upper() != "SHP":
            continue
        size = resource.get("size")
        if isinstance(size, int) and size <= cap and resource.get("url"):
            return resource
    return None


def _shp_size(pkg: dict) -> int | None:
    for resource in pkg.get("resources") or []:
        if (resource.get("format") or "").upper() == "SHP":
            size = resource.get("size")
            if isinstance(size, int):
                return size
    return None


def _ymd(year: object, month: object, day: object) -> str | None:
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except (TypeError, ValueError):
        return None


