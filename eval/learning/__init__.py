"""Held-out correction scoreboard. Owner: Melanie.

Stub only. A correction side and a held-out side are split by call, so Thai
and English variants stay together. Arms are scored on the held-out side.
Seeds are fixed.

The shape is a no-feedback run, a with-feedback run, and a shuffled control.
This package does not copy an external benchmark. It does not call Mubit,
train weights, or promote a version. `make eval-learning` writes the report.
"""

from eval.learning.harness import run

__all__ = ["run"]
