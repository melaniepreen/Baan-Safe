"""Policy and safeguarding pre-check. Owner: Moly.

Enrichment flags are attached in gateway.route. This module only records that
escalation and safeguarding rules were not evaluated. It does not read medical
fields and it does not change priority or route.
"""

from __future__ import annotations


def precheck_notes() -> list[str]:
    return ["safeguarding and escalation rules were not evaluated"]
