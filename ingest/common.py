"""Polite HTTP client: robots.txt, cache, per-host rate limit, retries.

The client never follows a redirect onto a host that was not passed in
`allowed_hosts`.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urljoin, urlparse

import httpx

from paths import ROOT

RAW_ROOT = ROOT / "data" / "raw"


class RobotsDisallowed(RuntimeError):
    pass


class OffHostError(RuntimeError):
    pass


def user_agent() -> str:
    contact = os.environ.get("BAANSAFE_CONTACT", "").strip()
    if contact:
        return f"BaanSafe-hackathon/0.1 (contact: {contact})"
    return "BaanSafe-hackathon/0.1 (contact: set in .env)"


_SECRET_MARKERS = ("key", "token", "signature", "credential", "secret", "password")


def _secret_param(name: str) -> bool:
    lowered = name.lower().replace("-", "_")
    return any(marker in lowered for marker in _SECRET_MARKERS)


def _looks_like_robots(text: str) -> bool:
    head = text.lstrip()[:200].lower()
    if head.startswith("<!doctype") or head.startswith("<html"):
        return False
    lowered = text.lower()
    return "user-agent" in lowered or "disallow" in lowered


def robots_allows(robots_text: str | None, path: str) -> bool:
    """Return True if `path` is allowed for a generic user agent.

    A missing file, an HTML error page, or a body that is not robots.txt
    is treated as no restrictions. Group matching is the `*` group.
    """
    if not robots_text or not _looks_like_robots(robots_text):
        return True
    groups: list[dict] = []
    current: dict | None = None
    for raw in robots_text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            current = {"agents": [value.lower()], "rules": []}
            groups.append(current)
            continue
        if current is None:
            continue
        if key == "user-agent" or key in {"allow", "disallow"}:
            if key == "user-agent":
                current["agents"].append(value.lower())
            else:
                current["rules"].append((key, value))
    star_rules: list[tuple[str, str]] = []
    for group in groups:
        if "*" in group["agents"]:
            star_rules.extend(group["rules"])
    if not star_rules:
        return True
    best_len = -1
    best_allow = True
    for kind, prefix in star_rules:
        if prefix == "":
            continue
        if path.startswith(prefix) and len(prefix) > best_len:
            best_len = len(prefix)
            best_allow = kind == "allow"
        elif path.startswith(prefix) and len(prefix) == best_len and kind == "allow":
            best_allow = True
    return best_allow


def _star_directives(robots_text: str | None) -> dict[str, list[str]]:
    """Return directive values for the `*` group. Non-robots bodies yield nothing."""
    found: dict[str, list[str]] = {}
    if not robots_text or not _looks_like_robots(robots_text):
        return found
    agents: list[str] = []
    saw_directive = False
    in_star = False
    for raw in robots_text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip()
        if key == "user-agent":
            if saw_directive:
                agents = []
                saw_directive = False
            agents.append(value.lower())
            in_star = "*" in agents
            continue
        saw_directive = True
        if in_star:
            found.setdefault(key, []).append(value)
    return found


def request_interval_seconds(robots_text: str | None) -> float | None:
    """Parse `Request-rate: requests/seconds` for the `*` group.

    `1/60` means one request every 60 seconds. The longest interval wins.
    """
    best: float | None = None
    for raw in _star_directives(robots_text).get("request-rate", []):
        if "/" not in raw:
            continue
        count_text, seconds_text = raw.split("/", 1)
        try:
            count = float(count_text.strip())
            seconds = float(seconds_text.strip())
        except ValueError:
            continue
        if count <= 0 or seconds < 0:
            continue
        interval = seconds / count
        best = interval if best is None else max(best, interval)
    return best


def visit_windows_minutes(robots_text: str | None) -> list[tuple[int, int]]:
    """Parse `Visit-time: HHMM-HHMM` ranges as minutes from midnight, UTC."""
    windows: list[tuple[int, int]] = []
    for raw in _star_directives(robots_text).get("visit-time", []):
        if "-" not in raw:
            continue
        start_text, end_text = raw.split("-", 1)
        try:
            start = _hhmm_minutes(start_text)
            end = _hhmm_minutes(end_text)
        except ValueError:
            continue
        windows.append((start, end))
    return windows


def _hhmm_minutes(token: str) -> int:
    text = token.strip()
    if len(text) != 4 or not text.isdigit():
        raise ValueError(text)
    hours = int(text[:2])
    minutes = int(text[2:])
    if hours > 23 or minutes > 59:
        raise ValueError(text)
    return hours * 60 + minutes


def visit_open(robots_text: str | None, moment: datetime) -> bool:
    """Return True if `moment` (UTC) is inside a Visit-time range.

    No Visit-time directive means the site did not restrict the clock.
    A range is inclusive of both endpoint minutes. Ranges that pass
    midnight are honoured.
    """
    windows = visit_windows_minutes(robots_text)
    if not windows:
        return True
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    minute = moment.astimezone(timezone.utc).hour * 60 + moment.astimezone(timezone.utc).minute
    for start, end in windows:
        if start <= end and start <= minute <= end:
            return True
        if start > end and (minute >= start or minute <= end):
            return True
    return False


def robots_readable(text: str | None) -> bool:
    """True only when the body is a robots.txt file, not an error page."""
    return bool(text) and _looks_like_robots(text)


def scrub(text: str, secret: str | None = None) -> str:
    """Remove query secrets and, when provided, a known secret value."""
    import re

    cleaned = re.sub(
        r"(?i)([?&][^=&\s\"']*(?:key|token|signature|credential|secret|password)[^=&\s\"']*=)[^&\s\"']+",
        r"\1REDACTED",
        text,
    )
    if secret and len(secret) >= 8 and secret in cleaned:
        cleaned = cleaned.replace(secret, "REDACTED")
    return cleaned


def _redact(url: str) -> str:
    # Never persist an API key that arrived in a query string.
    parts = url.split("?")
    if len(parts) == 1:
        return url
    kept = []
    for pair in parts[1].split("&"):
        name = pair.split("=", 1)[0].lower()
        if _secret_param(name):
            kept.append(f"{name}=REDACTED")
        else:
            kept.append(pair)
    return parts[0] + "?" + "&".join(kept)


def _public_query(items: dict) -> str:
    pairs: list[tuple[str, str]] = []
    for key, value in items.items():
        if _secret_param(str(key)):
            pairs.append((str(key), "REDACTED"))
        else:
            pairs.append((str(key), "" if value is None else str(value)))
    return urlencode(sorted(pairs))


@dataclass
class FetchResult:
    body: bytes
    status_code: int
    url: str
    from_cache: bool
    fetched_at: str


class PoliteClient:
    def __init__(
        self,
        source: str,
        refresh: bool = False,
        timeout: float = 45.0,
        attempts: int = 4,
        require_robots: bool = False,
    ) -> None:
        self.source = source
        self.refresh = refresh
        self.timeout = timeout
        self.attempts = attempts
        # GDACS sets this. An unreadable robots.txt then refuses the request
        # instead of treating the site as unrestricted.
        self.require_robots = require_robots
        self._last: dict[str, float] = {}
        self._robots: dict[str, str | None] = {}
        self._interval: dict[str, float] = {}
        self.user_agent = user_agent()

    def get_json(
        self,
        url: str,
        *,
        allowed_hosts: set[str],
        params: dict | None = None,
        ignore_robots: bool = False,
        accept: str = "application/json",
    ) -> FetchResult:
        return self._request(
            "GET",
            url,
            allowed_hosts=allowed_hosts,
            params=params,
            ignore_robots=ignore_robots,
            accept=accept,
        )

    def post(
        self,
        url: str,
        *,
        allowed_hosts: set[str],
        data: dict[str, str],
        ignore_robots: bool = False,
    ) -> FetchResult:
        return self._request(
            "POST",
            url,
            allowed_hosts=allowed_hosts,
            data=data,
            ignore_robots=ignore_robots,
        )

    def _cache_paths(self, method: str, url: str, extra: str) -> tuple[Path, Path]:
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        material = json.dumps({"m": method, "u": _redact(url), "e": extra}, sort_keys=True)
        digest = hashlib.sha256(material.encode()).hexdigest()[:24]
        folder = RAW_ROOT / self.source / day
        return folder / f"{digest}.bin", folder / f"{digest}.meta.json"

    def _wait(self, host: str) -> None:
        needed = self._interval.get(host, 1.0)
        last = self._last.get(host, 0.0)
        gap = time.monotonic() - last
        if gap < needed:
            time.sleep(needed - gap)
        self._last[host] = time.monotonic()

    def _robots_text(self, client: httpx.Client, origin: str, host: str) -> str | None:
        if host in self._robots:
            return self._robots[host]
        self._wait(host)
        try:
            # application/json makes www.gdacs.org answer 406 with an HTML
            # page, which hides Request-rate and Visit-time. Ask for text.
            response = client.get(
                urljoin(origin, "/robots.txt"),
                headers={"Accept": "text/plain, */*;q=0.1"},
            )
        except httpx.HTTPError:
            self._robots[host] = None
            return None
        if response.status_code == 404:
            self._robots[host] = None
            return None
        text = response.text if response.status_code == 200 else None
        self._robots[host] = text
        return text

    def _request(
        self,
        method: str,
        url: str,
        *,
        allowed_hosts: set[str],
        params: dict | None = None,
        data: dict[str, str] | None = None,
        ignore_robots: bool = False,
        accept: str = "application/json",
    ) -> FetchResult:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if host not in allowed_hosts:
            raise OffHostError(f"refusing off-list host {host}")
        extra = _public_query(params or data or {})
        body_path, meta_path = self._cache_paths(method, url, extra)
        if body_path.exists() and not self.refresh:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            # A cache written before the visit window was enforced must not
            # be replayed. Ordinary sources do not set this flag.
            if not self.require_robots or meta.get("visit_open") is True:
                return FetchResult(
                    body=body_path.read_bytes(),
                    status_code=int(meta.get("status_code", 200)),
                    url=_redact(url),
                    from_cache=True,
                    fetched_at=str(meta.get("fetched_at")),
                )

        headers = {"User-Agent": self.user_agent, "Accept": accept}
        attempts = self.attempts  # initial try + retries
        with httpx.Client(timeout=self.timeout, follow_redirects=False, headers=headers) as client:
            origin = f"{parsed.scheme}://{host}"
            if not ignore_robots:
                robots = self._robots_text(client, origin, host)
                if self.require_robots and not robots_readable(robots):
                    raise RobotsDisallowed(
                        f"robots.txt on {host} could not be read; request was not sent"
                    )
                if not robots_allows(robots, parsed.path or "/"):
                    raise RobotsDisallowed(
                        f"robots.txt disallows {parsed.path} on {host}"
                    )
                interval = request_interval_seconds(robots)
                if interval is not None:
                    self._interval[host] = max(self._interval.get(host, 1.0), interval)
                if (parsed.path or "/") != "/robots.txt" and not visit_open(
                    robots, datetime.now(timezone.utc)
                ):
                    windows = visit_windows_minutes(robots)
                    pretty = ", ".join(
                        f"{start // 60:02d}{start % 60:02d}-{end // 60:02d}{end % 60:02d} UTC"
                        for start, end in windows
                    )
                    raise RobotsDisallowed(
                        f"robots.txt Visit-time on {host} allows {pretty}; "
                        "this request was not sent"
                    )
            response: httpx.Response | None = None
            current_url = url
            for attempt in range(attempts):
                current = urlparse(current_url)
                if current.hostname not in allowed_hosts:
                    raise OffHostError(f"refusing off-list host {current.hostname}")
                self._wait(current.hostname or host)
                try:
                    response = client.request(
                        method,
                        current_url,
                        params=params if current_url == url else None,
                        data=data if current_url == url else None,
                    )
                except httpx.HTTPError as exc:
                    if attempt == attempts - 1:
                        raise RuntimeError(scrub(str(exc))) from None
                    time.sleep(2**attempt)
                    continue
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location", "")
                    target = urljoin(current_url, location)
                    target_host = urlparse(target).hostname
                    if target_host not in allowed_hosts:
                        raise OffHostError(
                            f"redirect from {host} to {target_host} was not followed"
                        )
                    current_url = target
                    method = "GET"
                    continue
                if response.status_code in {429, 500, 502, 503, 504}:
                    if attempt == attempts - 1:
                        break
                    time.sleep(2**attempt)
                    continue
                break
        assert response is not None
        fetched_at = datetime.now(timezone.utc).isoformat()
        if response.status_code == 200:
            body_path.parent.mkdir(parents=True, exist_ok=True)
            body_path.write_bytes(response.content)
            meta_path.write_text(
                json.dumps(
                    {
                        "url": _redact(str(response.url)),
                        "status_code": response.status_code,
                        "fetched_at": fetched_at,
                        "source": self.source,
                        **({"visit_open": True} if self.require_robots else {}),
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        return FetchResult(
            body=response.content,
            status_code=response.status_code,
            url=_redact(str(response.url)),
            from_cache=False,
            fetched_at=fetched_at,
        )
