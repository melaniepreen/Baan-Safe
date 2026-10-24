"""Caller address taken from the session request.

A public address is kept as the request reported it. Loopback and private
addresses are not a caller's network, so the town demo stores one fixed
Thai access-network stub and marks that row simulated.
"""

from __future__ import annotations

import ipaddress

from fastapi import Request

STUB_IP = "171.6.84.23"


def _candidate(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return ""


def _public(value: str) -> bool:
    try:
        parsed = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_reserved
        or parsed.is_unspecified
    )


def resolve_caller_ip(request: Request) -> tuple[str, bool]:
    raw = _candidate(request)
    if _public(raw):
        return raw, False
    return STUB_IP, True


def stamp_caller_ip(state, request: Request) -> tuple[str, bool]:
    existing = state.resources.get("caller_ip")
    if existing:
        return str(existing), bool(state.resources.get("caller_ip_simulated"))
    ip, simulated = resolve_caller_ip(request)
    state.resources["caller_ip"] = ip
    state.resources["caller_ip_simulated"] = simulated
    return ip, simulated
