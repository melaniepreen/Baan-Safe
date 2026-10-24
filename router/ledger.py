"""In-process dispatch reservation ledger. Owner: Moly.

Reservations live for the life of the process and reset on restart — nothing
is written to disk. A case re-decided on a later turn keeps the reservations
it still holds and frees the ones that are gone. A human can confirm or cancel
holds via the API without changing RouterDecision / Dispatch contracts.
"""

from __future__ import annotations

from collections.abc import Iterable

Reservation = tuple[str, str]  # (resource_id, need value)

_HOLDS: dict[str, set[Reservation]] = {}
_CONFIRMED: dict[str, set[Reservation]] = {}


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


def reserved_total(resource_id: str) -> int:
    """How many reservations any case holds on this resource."""
    return sum(
        1
        for holds in _HOLDS.values()
        for rid, _need in holds
        if rid == resource_id
    )


def holds(case_id: str) -> set[Reservation]:
    return set(_HOLDS.get(case_id, set()))


def confirmed(case_id: str) -> set[Reservation]:
    return set(_CONFIRMED.get(case_id, set()))


def release_case(case_id: str, keep: Iterable[Reservation]) -> None:
    """Drop this case's reservations that are not in `keep`."""
    keep_set = set(keep)
    _HOLDS[case_id] = set(_HOLDS.get(case_id, set())) & keep_set
    if case_id in _CONFIRMED:
        _CONFIRMED[case_id] = set(_CONFIRMED.get(case_id, set())) & keep_set
        if not _CONFIRMED[case_id]:
            _CONFIRMED.pop(case_id, None)


def confirm_case(case_id: str) -> set[Reservation]:
    """Mark every current hold for this case as confirmed. Returns the set.

    Raises KeyError when the case has no holds.
    """
    current = holds(case_id)
    if not current:
        raise KeyError(case_id)
    _CONFIRMED[case_id] = set(current)
    return set(current)


def cancel_case(case_id: str) -> set[Reservation]:
    """Release every hold (and confirmation) for this case. Returns released.

    Raises KeyError when the case has nothing to release.
    """
    released = holds(case_id) | confirmed(case_id)
    if not released:
        raise KeyError(case_id)
    _HOLDS.pop(case_id, None)
    _CONFIRMED.pop(case_id, None)
    return released


def reset() -> None:
    _HOLDS.clear()
    _CONFIRMED.clear()
