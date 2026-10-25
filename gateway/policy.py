"""Policy precheck note. Owner: Moly.

The field precheck (gateway/chooser.py) evaluates the System 2 triggers in
config/escalation.yaml against extracted fields and policy flags. This module
only records that result on the decision. It does not read medical fields and
it does not change priority or route.
"""

from __future__ import annotations

from collections.abc import Sequence


def precheck_notes(triggers: Sequence[str] = ()) -> list[str]:
    fired = ", ".join(triggers) if triggers else "none"
    return [
        "policy precheck: System 2 triggers from config/escalation.yaml "
        f"evaluated; fired: {fired}"
    ]
