"""Adapter interface: fetch, normalise, version.

A live adapter returns only text that the source itself contained.
Amounts, thresholds, and eligibility sentences that are not in the payload
are not filled in. If a source cannot be fetched, it is a candidate in
policies/sources/candidates.py, not an adapter that guesses.
"""

from __future__ import annotations

from typing import Protocol

from policies.schema import NormalisedLabel, NormalisedRule


class PolicySourceAdapter(Protocol):
    source_id: str

    def fetch(self) -> dict[str, object]:
        """Read the source. The returned mapping is the raw payload."""

    def version(self, fetched: dict[str, object]) -> str:
        """Stable id for this payload. Same bytes must yield the same version."""

    def normalise(
        self,
        fetched: dict[str, object],
        *,
        source_version: str,
    ) -> tuple[list[NormalisedRule], list[NormalisedLabel]]:
        """Map the payload onto the shared rule and label schema."""
