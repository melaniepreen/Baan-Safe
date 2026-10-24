"""Held-out correction scoreboard. Owner: Melanie.

Stub only. A correction side and a held-out side are split by group_id, so
Thai and English variants stay together. Arm C can read human rows only, or
human plus coach. Arms are scored on the held-out side.
Seeds are fixed.

The shape is a no-feedback run, a with-feedback run, and a shuffled control.
Arms are also scored on held-out caller trait combinations.
This package does not copy an external benchmark. It does not call Mubit,
train weights, or promote a version. `make eval-learning` writes the report.
"""

from eval.learning.harness import run

__all__ = ["run"]
