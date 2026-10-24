"""Scripted caller. Default backend. Does not call a model."""

from __future__ import annotations

from sim.callers.persona import CallerSpec, CallerTurn
from sim.callers.traits import N_TURNS, URGENCY_CUE


def speak(spec: CallerSpec, turn_index: int, backend: str = "scripted") -> CallerTurn:
    """Public utterance plus a private trace. The private trace stays off the transcript."""
    if backend == "scripted":
        return compose(spec, turn_index)
    if backend == "model":
        from sim.callers.model import model_public

        # The model stub has no hidden reasoning trace. Token-level
        # self-distillation is future work and is not implemented.
        return CallerTurn(
            index=turn_index,
            public_text=model_public(spec, turn_index),
            private_trace="model private trace is not implemented in this stub",
        )
    raise ValueError(f"unknown caller backend {backend!r}")


def compose(spec: CallerSpec, turn_index: int) -> CallerTurn:
    """Apply each active trait, then the location and urgency rules."""
    traits = set(spec.traits)
    public: list[str] = []
    private: list[str] = []
    persona = spec.persona

    if "needs_repeating" in traits:
        public.append("What? Please say that again.")
        private.append("I missed the last sentence and I am not adding a new fact.")
    if "elderly_hearing" in traits:
        public.append("Please speak louder. I did not hear you.")
        private.append("I did not catch the question. I will not guess an answer.")
    if "panicked_fragmented" in traits:
        public.append("Water. House. Please.")
        private.append("I am speaking in fragments and skipping details.")
    if "code_switches" in traits:
        public.append("น้ำในบ้าน. Water in the house.")
        private.append("I am switching between Thai and English.")
    if "proxy" in traits:
        public.append("I am calling for someone else in the household.")
        private.append("The need belongs to the household. I am the proxy caller.")
    if "distrusts_authorities" in traits:
        public.append("I do not want to give details to officials.")
        private.append("I am holding facts back. I do not trust the office.")
    if "poor_line" in traits:
        public.append("The line is breaking up.")
        private.append("Part of what I mean will not be heard.")
    if "under_reports" in traits:
        public.append("It is only a little water and we are fine.")
        private.append(
            f"True urgency is {persona.true_urgency}. I am saying it is milder."
        )
    elif "over_reports" in traits:
        public.append("Everyone is dying.")
        private.append(
            f"True urgency is {persona.true_urgency}. I am saying it is worse."
        )
    else:
        cue = URGENCY_CUE[persona.true_urgency]
        public.append(cue[:1].upper() + cue[1:] + ".")
        private.append("I am stating the urgency cue that matches the hidden urgency.")
    if "contradicts" in traits:
        if turn_index == 0:
            public.append("There are two people.")
            private.append("The next turn will give a different count. The hidden count stays fixed.")
        else:
            public.append("No, there are five people.")
            private.append("This count contradicts the earlier turn. The hidden count is unchanged.")
    if "omits_location" in traits:
        private.append(
            f"I am not saying the district. Hidden location is {persona.location}."
        )
    else:
        public.append(f"We are in {persona.location}.")
        private.append("I included the district on this public turn.")
    if turn_index == 0:
        private.append("This is the first turn.")
    else:
        private.append(f"This is a later turn, index {turn_index}.")
        if "omits_location" in traits:
            public.append("I still will not name the place.")
        elif "under_reports" in traits:
            public.append("It is still only a little water.")
        elif "needs_repeating" in traits:
            public.append("Please repeat the last thing you said.")
        else:
            public.append("I am still on the line.")
    if not public:
        public.append("Synthetic caller. We need help.")
        private.append("No trait added a public fragment.")
    return CallerTurn(
        index=turn_index,
        public_text=" ".join(public),
        private_trace=" ".join(private),
    )


def revelation_turns(spec: CallerSpec, turns: int = N_TURNS) -> tuple[int | None, int | None]:
    """First public turn that states the hidden district, and the true urgency cue.

    None means the script never said that fact. The private trace is not read.
    """
    cue = URGENCY_CUE[spec.persona.true_urgency].lower()
    location = spec.persona.location.lower()
    location_at: int | None = None
    urgency_at: int | None = None
    for index in range(turns):
        text = compose(spec, index).public_text.lower()
        if location_at is None and location in text:
            location_at = index
        if urgency_at is None and cue in text:
            urgency_at = index
    return location_at, urgency_at
