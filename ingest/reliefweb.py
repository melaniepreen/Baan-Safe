"""ReliefWeb Thailand flood reports.

Every request needs a pre-approved `appname`. Without one, this module records
the sign-up step and stores no article text.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from ingest.common import OffHostError, PoliteClient, RobotsDisallowed
from ingest.db import connect, set_status

HOST = "api.reliefweb.int"
BASE = "https://api.reliefweb.int/v2"
SIGNUP = (
    "BLOCKED: ReliefWeb requires a pre-approved appname on every request. "
    "Sign-up: https://apidoc.reliefweb.int/parameters#appname "
    "(short form linked from that page; ReliefWeb replies by email). "
    "Then export RELIEFWEB_APPNAME and re-run `make ingest-refresh`. "
    "API v1 is decommissioned; use v2. "
    "The disaster id named in the brief is fl-2025-000209-tha. "
    "No report bodies were stored."
)
SUMMARY_LIMIT = 280


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_summary(headline: str | None, title: str | None) -> str:
    text = (headline or title or "").strip()
    text = " ".join(text.split())
    if len(text) > SUMMARY_LIMIT:
        text = text[: SUMMARY_LIMIT - 1].rstrip() + "…"
    return text


def ingest(refresh: bool) -> str:
    appname = os.environ.get("RELIEFWEB_APPNAME", "").strip()
    if not appname:
        # One probe so the blocker is an observed response, not only a guess.
        # The unapproved name is not a secret. No article fields are requested.
        client = PoliteClient("reliefweb", refresh=refresh, timeout=30)
        try:
            probe = client.get_json(
                f"{BASE}/reports",
                allowed_hosts={HOST},
                params={"appname": "baansafe-hackathon", "limit": "1"},
            )
            observed = f" Probe HTTP {probe.status_code}."
        except (RobotsDisallowed, OffHostError) as exc:
            observed = f" Probe stopped: {exc}."
        detail = SIGNUP + observed
        set_status(
            "reliefweb",
            fetched_at=_now(),
            row_count=0,
            status="blocked",
            detail=detail,
        )
        return detail

    client = PoliteClient("reliefweb", refresh=refresh, timeout=40)
    stored = 0
    notes: list[str] = []
    try:
        reports = client.get_json(
            f"{BASE}/reports",
            allowed_hosts={HOST},
            params={
                "appname": appname,
                "limit": "20",
                "query[value]": "flood",
                "filter[operator]": "AND",
                "filter[conditions][0][field]": "primary_country.iso3",
                "filter[conditions][0][value]": "tha",
                "fields[include][]": ["title", "date.created", "url_alias", "source.shortname", "headline"],
            },
        )
    except (RobotsDisallowed, OffHostError) as exc:
        set_status("reliefweb", fetched_at=_now(), row_count=0, status="blocked", detail=str(exc))
        return str(exc)

    if reports.status_code != 200:
        detail = f"BLOCKED: ReliefWeb HTTP {reports.status_code} for reports. {SIGNUP}"
        set_status("reliefweb", fetched_at=_now(), row_count=0, status="blocked", detail=detail)
        return detail

    payload = json.loads(reports.body)
    # Never read body / body-html even if the API included them.
    for item in payload.get("data") or []:
        fields = item.get("fields") or {}
        if "body" in fields or "body-html" in fields:
            fields = {k: v for k, v in fields.items() if k not in {"body", "body-html"}}
        title = _as_text(fields.get("title"))
        summary = _short_summary(_as_text(fields.get("headline")), title)
        report_id = str(item.get("id"))
        url = fields.get("url_alias") or ""
        if url and url.startswith("/"):
            url = "https://reliefweb.int" + url
        source_name = ""
        source = fields.get("source")
        if isinstance(source, list) and source:
            source_name = _as_text(source[0].get("shortname") if isinstance(source[0], dict) else source[0])
        elif isinstance(source, dict):
            source_name = _as_text(source.get("shortname"))
        published = ""
        date = fields.get("date")
        if isinstance(date, dict):
            published = str(date.get("created") or "")
        _insert_report(
            report_id=report_id,
            event_id=None,
            source=source_name or "reliefweb",
            published_at=published,
            title=title,
            summary=summary,
            url=url,
        )
        stored += 1

    disaster_note = _one_disaster(client, appname)
    notes.append(disaster_note)
    detail = f"Stored {stored} report headers/summaries. " + " ".join(notes)
    set_status(
        "reliefweb",
        fetched_at=reports.fetched_at,
        row_count=stored,
        status="ok",
        detail=detail,
    )
    return detail


def _one_disaster(client: PoliteClient, appname: str) -> str:
    try:
        result = client.get_json(
            f"{BASE}/disasters",
            allowed_hosts={HOST},
            params={
                "appname": appname,
                "limit": "5",
                "query[value]": "fl-2025-000209-tha",
                "fields[include][]": ["name", "date.created", "url_alias", "status", "country.name"],
            },
        )
    except (RobotsDisallowed, OffHostError) as exc:
        return f"Disaster query stopped: {exc}"
    if result.status_code != 200:
        return f"Disaster query HTTP {result.status_code}."
    payload = json.loads(result.body)
    found = 0
    for item in payload.get("data") or []:
        fields = item.get("fields") or {}
        fields.pop("body", None)
        fields.pop("body-html", None)
        name = _as_text(fields.get("name"))
        countries = fields.get("country") or []
        provinces = ", ".join(
            _as_text(c.get("name")) for c in countries if isinstance(c, dict)
        )
        url = fields.get("url_alias") or ""
        if url and str(url).startswith("/"):
            url = "https://reliefweb.int" + str(url)
        _insert_report(
            report_id=f"disaster-{item.get('id')}",
            event_id="fl-2025-000209-tha",
            source="reliefweb",
            published_at=_as_text((fields.get("date") or {}).get("created") if isinstance(fields.get("date"), dict) else None),
            title=name,
            summary=_short_summary(name, name),
            url=str(url),
            provinces=provinces or None,
        )
        found += 1
    return f"Disaster query stored {found} header rows for fl-2025-000209-tha."


def _as_text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _insert_report(**kwargs: object) -> None:
    summary = str(kwargs.get("summary") or "")
    if len(summary) > SUMMARY_LIMIT:
        summary = summary[: SUMMARY_LIMIT - 1] + "…"
    with connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO disaster_report (
                report_id, event_id, source, published_at, title, summary,
                affected_people, affected_households, fatalities, provinces,
                assistance_type, url
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL, ?, NULL, ?)
            """,
            (
                kwargs.get("report_id"),
                kwargs.get("event_id"),
                kwargs.get("source"),
                kwargs.get("published_at"),
                kwargs.get("title"),
                summary,
                kwargs.get("provinces"),
                kwargs.get("url"),
            ),
        )
