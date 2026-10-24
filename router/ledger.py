"""In-process dispatch reservation ledger. Owner: Moly.

Reservations live for the life of the process and reset on restart — nothing
is written to disk. A case re-decided on a later turn keeps the reservations
it still holds and frees the ones that are gone.
"""

from __future__ import annotations

from collections.abc import Iterable

Reservation = tuple[str, str]  # (resource_id, need value)

_HOLDS: dict[str, set[Reservation]] = {}


def reserve(case_id: str, resource_id: str, need: str) -> None:
    _HOLDS.setdefault(case_id, set()).add((resource_id, need))


def reserved_by_others(resource_id: str, case_id: str) -> int:
    """How many reservations other cases hold on this resource."""
    return sum(
        1
        for other, holds in _HOLDS.items()
        if other != case_id
        for rid, _need in holds
        if rid == resource_id
    )


def holds(case_id: str) -> set[Reservation]:
    return set(_HOLDS.get(case_id, set()))


def release_case(case_id: str, keep: Iterable[Reservation]) -> None:
    """Drop this case's reservations that are not in `keep`."""
    _HOLDS[case_id] = set(_HOLDS.get(case_id, set())) & set(keep)


def reset() -> None:
    _HOLDS.clear()
