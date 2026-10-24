"""Composable flood-caller traits and the scripted default backend."""

from sim.callers.catalog import CATALOG
from sim.callers.model import model_public
from sim.callers.persona import CallerSpec, CallerTurn, HiddenPersona
from sim.callers.scripted import compose, revelation_turns, speak
from sim.callers.traits import N_TURNS, TRAIT_IDS, URGENCY_CUE

__all__ = [
    "CATALOG",
    "CallerSpec",
    "CallerTurn",
    "HiddenPersona",
    "N_TURNS",
    "TRAIT_IDS",
    "URGENCY_CUE",
    "compose",
    "model_public",
    "revelation_turns",
    "speak",
]
