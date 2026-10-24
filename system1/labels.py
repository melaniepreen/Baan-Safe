"""System 1 hypothesis templates. They come from the policy service.

This module does not open the YAML files. The local YAML adapter is the
only reader. Thai hypotheses are templates unless the label says the Thai
is a quotation.
"""

from __future__ import annotations

from policies.service import get_service


def hypotheses(
    lang: str = "en",
    *,
    version: str | None = None,
    run_id: str | None = None,
) -> list[dict[str, object]]:
    body = get_service().labels(lang=lang, version=version, run_id=run_id)
    rows = body["labels"]
    if not isinstance(rows, list):
        raise ValueError("Policy service returned no label list.")
    return rows
