"""ReliefWeb is not an active source.

The owner removed it. robots.txt on api.reliefweb.int disallows /v2/, and the
API also requires a pre-approved appname. This module does not send a request.
"""

from __future__ import annotations

from datetime import datetime, timezone

from ingest.db import set_status

RETIRED = (
    "RETIRED: ReliefWeb is not an active source. "
    "https://api.reliefweb.int/robots.txt disallows /v2/ for every user agent, "
    "and every call needs a pre-approved appname "
    "(https://apidoc.reliefweb.int/parameters#appname). "
    "No request is sent. Disaster reports come from GLIDE, IDMC, and GDACS."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ingest(refresh: bool = False) -> str:
    del refresh
    set_status(
        "reliefweb",
        fetched_at=_now(),
        row_count=0,
        status="retired",
        detail=RETIRED,
    )
    return RETIRED
