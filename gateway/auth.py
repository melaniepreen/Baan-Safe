"""Auth pre-check for the Mubit gateway. Owner: Moly.

The scheme is gateway.auth in config/decisions.yaml. While that is TODO_HUMAN
this stub records the gap and does not reject the request.
"""

from __future__ import annotations

from config.settings import unset_decisions


def status() -> str:
    if unset_decisions(["gateway.auth"]):
        return "auth scheme is TODO_HUMAN; request was not rejected"
    return "auth scheme is set; the stub does not enforce it yet"
