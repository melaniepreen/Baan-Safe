"""Before/after comparison for a stub model update.

Quality, latency, and token counts are taken from the two stub runs.
cost_usd stays null while llm.token_price_usd is TODO_HUMAN. This module
does not invent a price and it does not decide a case.
"""

from __future__ import annotations

from typing import Any


def compare_runs(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    return {
        "quality": {
            "metric": "route_accuracy_vs_corrected_label",
            "before": before["route_accuracy"],
            "after": after["route_accuracy"],
            "n": before.get("n", 1),
        },
        "latency_ms": {
            "before": before["latency_ms"],
            "after": after["latency_ms"],
        },
        "tokens": {
            "before": {"in": before["tokens_in"], "out": before["tokens_out"]},
            "after": {"in": after["tokens_in"], "out": after["tokens_out"]},
        },
        "cost_usd": {
            "before": None,
            "after": None,
            "reason": (
                "llm.token_price_usd is TODO_HUMAN. "
                "No USD rate was invented, so cost stays null."
            ),
        },
        "model_version": {
            "before": before["model_version"],
            "after": after["model_version"],
        },
    }
