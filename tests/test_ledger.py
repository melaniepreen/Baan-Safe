"""In-process reservation ledger: reserve, confirm, cancel, stock totals."""

from __future__ import annotations

import pytest

from router import ledger


def test_reserve_and_reserved_by_others():
    ledger.reserve("case-a", "amb-1", "medical")
    assert ledger.holds("case-a") == {("amb-1", "medical")}
    assert ledger.reserved_by_others("amb-1", "case-a") == 0
    assert ledger.reserved_by_others("amb-1", "case-b") == 1
    assert ledger.reserved_total("amb-1") == 1


def test_confirm_marks_holds_without_releasing():
    ledger.reserve("case-a", "boat-1", "rescue")
    marked = ledger.confirm_case("case-a")
    assert marked == {("boat-1", "rescue")}
    assert ledger.confirmed("case-a") == {("boat-1", "rescue")}
    assert ledger.holds("case-a") == {("boat-1", "rescue")}
    assert ledger.reserved_total("boat-1") == 1


def test_confirm_without_holds_raises():
    with pytest.raises(KeyError):
        ledger.confirm_case("missing")


def test_cancel_releases_holds_and_confirmation():
    ledger.reserve("case-a", "shelter-1", "shelter")
    ledger.confirm_case("case-a")
    released = ledger.cancel_case("case-a")
    assert released == {("shelter-1", "shelter")}
    assert ledger.holds("case-a") == set()
    assert ledger.confirmed("case-a") == set()
    assert ledger.reserved_total("shelter-1") == 0


def test_cancel_without_holds_raises():
    with pytest.raises(KeyError):
        ledger.cancel_case("missing")


def test_release_case_prunes_confirmed():
    ledger.reserve("case-a", "amb-1", "medical")
    ledger.reserve("case-a", "boat-1", "rescue")
    ledger.confirm_case("case-a")
    ledger.release_case("case-a", keep={("amb-1", "medical")})
    assert ledger.holds("case-a") == {("amb-1", "medical")}
    assert ledger.confirmed("case-a") == {("amb-1", "medical")}


def test_confirm_is_idempotent():
    ledger.reserve("case-a", "welfare-1", "water")
    first = ledger.confirm_case("case-a")
    again = ledger.confirm_case("case-a")
    assert first == again == {("welfare-1", "water")}
