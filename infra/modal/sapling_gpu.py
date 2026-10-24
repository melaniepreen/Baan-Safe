"""48GB-class gate for the Sapling Modal app. No Modal import.

The product decision `sapling.gpu` stays TODO_HUMAN. This module only checks
a value a human has already exported.
"""

from __future__ import annotations

from infra.modal.common import UnsetDecision, parse_gpu

# Modal strings at or above 48 GB. Bare `A100` is the 40 GB part in this repo.
MODAL_48GB_OR_LARGER = ("L40S", "A100-80GB", "H100", "H100!", "H200")


def require_sapling_gpu(spec: str) -> str:
    """Return a Modal GPU string, or refuse a board that cannot hold Sapling."""
    raw = spec.strip()
    if raw == "A6000":
        raise UnsetDecision(
            "A6000 is the self-hosted 48 GB board in infra/HARDWARE.md. "
            "It is not a Modal GPU string. On Modal, export SAPLING_GPU=L40S."
        )
    gpu = parse_gpu(raw, allow_cpu=False)
    if gpu is None:
        raise UnsetDecision("Sapling does not run on CPU. See infra/HARDWARE.md.")
    name, _, count = gpu.partition(":")
    if name not in MODAL_48GB_OR_LARGER:
        raise UnsetDecision(
            f"Sapling needs a 48GB-class GPU. {gpu} is below that. "
            "Use L40S on Modal, or an A6000 when self-hosting. See infra/HARDWARE.md."
        )
    if count:
        raise UnsetDecision(
            f"Sapling is one checkpoint on one 48GB-class GPU. {gpu} asks for more than one."
        )
    return gpu
