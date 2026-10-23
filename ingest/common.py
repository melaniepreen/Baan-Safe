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


def _looks_like_robots(text: str) -> bool:
    head = text.lstrip()[:200].lower()
    if head.startswith("<!doctype") or head.startswith("<html"):
        return False
    return "user-agent" in text.lower() or "disallow" in text.lower()


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


def _redact(url: str) -> str:
    # Never persist an API key that arrived in a query string.
    parts = url.split("?")
    if len(parts) == 1:
        return url
    kept = []
    for pair in parts[1].split("&"):
        name = pair.split("=", 1)[0].lower()
        if name in {"api_key", "apikey", "key", "token", "access_token"}:
            kept.append(f"{name}=REDACTED")
        else:
            kept.append(pair)
    return parts[0] + "?" + "&".join(kept)


@dataclass
class FetchResult:
    body: bytes
    status_code: int
    url: str
    from_cache: bool
    fetched_at: str


class PoliteClient:
    def __init__(self, source: str, refresh: bool = False, timeout: float = 45.0) -> None:
        self.source = source
        self.refresh = refresh
        self.timeout = timeout
        self._last: dict[str, float] = {}
        self._robots: dict[str, str | None] = {}
        self.user_agent = user_agent()

    def get_json(
        self,
        url: str,
        *,
        allowed_hosts: set[str],
        params: dict | None = None,
        ignore_robots: bool = False,
    ) -> FetchResult:
        return self._request(
            "GET",
            url,
            allowed_hosts=allowed_hosts,
            params=params,
            ignore_robots=ignore_robots,
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
        last = self._last.get(host, 0.0)
        gap = time.monotonic() - last
        if gap < 1.0:
            time.sleep(1.0 - gap)
        self._last[host] = time.monotonic()

    def _robots_text(self, client: httpx.Client, origin: str, host: str) -> str | None:
        if host in self._robots:
            return self._robots[host]
        self._wait(host)
        try:
            response = client.get(urljoin(origin, "/robots.txt"))
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
    ) -> FetchResult:
        parsed = urlparse(url)
        host = parsed.hostname or ""
        if host not in allowed_hosts:
            raise OffHostError(f"refusing off-list host {host}")
        extra = urlencode(sorted((params or data or {}).items()))
        body_path, meta_path = self._cache_paths(method, url, extra)
        if body_path.exists() and not self.refresh:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            return FetchResult(
                body=body_path.read_bytes(),
                status_code=int(meta.get("status_code", 200)),
                url=url,
                from_cache=True,
                fetched_at=str(meta.get("fetched_at")),
            )

        headers = {"User-Agent": self.user_agent, "Accept": "application/json"}
        attempts = 4  # initial try + 3 retries
        with httpx.Client(timeout=self.timeout, follow_redirects=False, headers=headers) as client:
            origin = f"{parsed.scheme}://{host}"
            if not ignore_robots:
                robots = self._robots_text(client, origin, host)
                if not robots_allows(robots, parsed.path or "/"):
                    raise RobotsDisallowed(
                        f"robots.txt disallows {parsed.path} on {host}"
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
                except httpx.HTTPError:
                    if attempt == attempts - 1:
                        raise
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
                    },
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )
        return FetchResult(
            body=response.content,
            status_code=response.status_code,
            url=str(response.url),
            from_cache=False,
            fetched_at=fetched_at,
        )
