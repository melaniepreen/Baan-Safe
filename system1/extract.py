"""Keyword extraction for the fast path. Owner: Moly.

This is the decided `system1.extraction_method` (`rules-only`). English only:
caller turns are sentence-split, matched against fixed phrase lists, and a
match is dropped when a negator sits within the three words before it. The
returned flags are suggestions for `CaseState.policy_flags`; the gateway
decides whether to attach them.
"""

from __future__ import annotations

import re

from contracts.models import ExtractedFields, Need, TranscriptTurn

NEGATORS = {"no", "not", "nobody", "never", "don't", "isn't", "aren't", "wasn't"}

_SENTENCE_END = re.compile(r"[.!?]+")
_WORD = re.compile(r"[a-z']+")

NEED_PHRASES: list[tuple[Need, tuple[str, ...]]] = [
    (Need.water, ("drinking water", "bottles", "water to drink", "need water", "only need water")),
    (Need.food, ("rice", "food", "eat")),
    (Need.shelter, ("shelter",)),
    (Need.evacuation, ("evacuate", "evacuation", "leave the house")),
    (Need.power, ("power", "electricity", "blackout")),
    (Need.rescue, ("trapped", "can't get out", "on the roof", "help us get out")),
    (Need.medical, ("oxygen", "medicine", "dialysis", "hurt", "injured", "bleeding")),
    (Need.aid_payment, ("compensation", "aid payment", "eligible", "relief money")),
]

INFORMATION_PATTERNS = (
    r"\bwhen\b",
    r"\bwhat time\b",
    r"\bis the\b[^.!?]*\bopen\b",
    r"\bupdate\b",
)

DANGER_PHRASES: dict[str, tuple[str, ...]] = {
    "rising_water": (
        "water rising",
        "is rising",
        "water at the door",
        "water is at the door",
        "water at the step",
        "water is at the step",
        "water inside",
        "water is inside",
        "water coming in",
        "coming up the step",
    ),
}

VULNERABLE_PHRASES: dict[str, tuple[str, ...]] = {
    "elderly": ("grandmother", "grandfather", "elderly", "old"),
    "child": ("child", "baby", "kid", "son", "daughter", "infant"),
    "oxygen_dependent": ("oxygen",),
    "immobile": ("can't walk", "cannot walk", "wheelchair", "bedridden", "can't climb"),
}

MINIMISING_PHRASES = (
    "we are fine",
    "we're fine",
    "we're ok",
    "it's fine",
    "nothing serious",
)

ALONE_PHRASES = (
    "alone",
    "by myself",
    "no parent",
    "can't find my mum",
    "can't find my dad",
    "can't find my parents",
)

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}

_PEOPLE_COUNT = re.compile(
    r"\b(one|two|three|four|five|six|seven|eight|nine|ten|\d+)\s+"
    r"(people|persons|adults|of us)\b"
)
_JUST_ME = re.compile(r"\b(just me|only me)\b")


def _sentences(transcript: list[TranscriptTurn]) -> list[str]:
    text = " ".join(turn.text for turn in transcript if turn.speaker == "caller")
    return [part.lower() for part in _SENTENCE_END.split(text) if part.strip()]


def _negated(sentence: str, start: int) -> bool:
    """True when a negator sits within the three words before `start`."""
    words = _WORD.findall(sentence[:start])
    return any(word in NEGATORS for word in words[-3:])


def _match_any(sentence: str, phrases: tuple[str, ...]) -> bool:
    for phrase in phrases:
        for match in re.finditer(r"\b" + re.escape(phrase) + r"\b", sentence):
            if not _negated(sentence, match.start()):
                return True
    return False


def _district_names(districts: list[str] | None) -> list[str]:
    if districts is not None:
        return districts
    from ingest.db import DB_PATH, connect

    if not DB_PATH.exists():
        return []
    with connect() as conn:
        try:
            rows = conn.execute("SELECT name_en, province FROM districts").fetchall()
        except Exception:  # noqa: BLE001 — a missing table means no district list
            return []
    names = []
    for row in rows:
        name = row["name_en"]
        if not name:
            continue
        names.append(f"{name}, {row['province']}" if row["province"] else name)
    return names


def _location(sentences: list[str], districts: list[str] | None) -> tuple[str | None, float | None]:
    text = " ".join(sentences)
    for entry in _district_names(districts):
        name = entry.split(",", 1)[0].strip()
        if name and re.search(r"\b" + re.escape(name.lower()) + r"\b", text):
            return entry, 0.85
    return None, None


def _people_count(sentences: list[str]) -> int | None:
    count = None
    for sentence in sentences:
        if _JUST_ME.search(sentence):
            count = 1
        for match in _PEOPLE_COUNT.finditer(sentence):
            token = match.group(1)
            count = int(token) if token.isdigit() else NUMBER_WORDS[token]
    return count


def extract(
    transcript: list[TranscriptTurn],
    districts: list[str] | None = None,
) -> tuple[ExtractedFields, list[str]]:
    """Extract fields from caller turns and suggest policy flags."""
    sentences = _sentences(transcript)
    needs: list[Need] = []
    for need, phrases in NEED_PHRASES:
        if any(_match_any(sentence, phrases) for sentence in sentences):
            needs.append(need)
    if any(re.search(pattern, sentence) for pattern in INFORMATION_PATTERNS for sentence in sentences):
        needs.append(Need.information)
    danger = [
        tag
        for tag, phrases in DANGER_PHRASES.items()
        if any(_match_any(sentence, phrases) for sentence in sentences)
    ]
    vulnerable = [
        tag
        for tag, phrases in VULNERABLE_PHRASES.items()
        if any(_match_any(sentence, phrases) for sentence in sentences)
    ]
    medical = "oxygen_dependent" in vulnerable or Need.medical in needs
    location, confidence = _location(sentences, districts)
    fields = ExtractedFields(
        location=location,
        location_confidence=confidence,
        people_count=_people_count(sentences),
        vulnerable=vulnerable,
        medical=medical,
        danger=danger,
        needs=needs,
    )
    flags: list[str] = []
    text = " ".join(sentences)
    minimising = any(phrase in text for phrase in MINIMISING_PHRASES)
    if minimising and (danger or Need.rescue in needs or Need.medical in needs or medical):
        flags.append("conflicting_evidence")
    if "child" in vulnerable and any(phrase in text for phrase in ALONE_PHRASES):
        flags.append("safeguarding")
    return fields, flags
