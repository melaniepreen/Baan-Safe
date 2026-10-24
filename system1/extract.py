"""Keyword extraction for the fast path. Owner: Moly.

This is the decided `system1.extraction_method` (`rules-only`). Keyword
phrases are English: caller turns are sentence-split, matched against phrase
and regex families, and a match is dropped when a negator sits within the
three words before it. District names also match the Thai and English
gazetteer.
Aid phrases and minimising phrases are exempt from negation — "we cannot get
the payment" and "not eligible" are exactly the signal. The returned flags
are suggestions for `CaseState.policy_flags`; the gateway attaches them.
"""

from __future__ import annotations

import re

from contracts.models import ExtractedFields, Need, TranscriptTurn

NEGATORS = {"no", "not", "nobody", "never", "don't", "isn't", "aren't", "wasn't"}

_SENTENCE_END = re.compile(r"[.!?]+")
_WORD = re.compile(r"[a-z']+")

NEED_PHRASES: list[tuple[Need, tuple[str, ...]]] = [
    (Need.water, ("drinking water", "bottles", "water bottles", "water to drink", "need water", "only need water")),
    (Need.food, ("rice", "food", "eat")),
    (Need.shelter, ("shelter",)),
    (
        Need.evacuation,
        (
            "evacuate",
            "evacuation",
            "leave the house",
            "move to a shelter",
            "should leave",
            "time to leave",
            "need to leave",
            "told to leave",
        ),
    ),
    (Need.power, ("power", "electricity", "blackout")),
    (Need.rescue, ("trapped", "can't get out", "cannot get out", "on the roof", "help us get out")),
    (
        Need.medical,
        (
            "oxygen",
            "medicine",
            "dialysis",
            "hurt",
            "injured",
            "bleeding",
            "sick",
            "breathing",
            "unconscious",
            "injury",
        ),
    ),
]

# A word directly before "shelter" that makes it a landmark, not a need.
SHELTER_SKIP_BEFORE = {"bus"}

INFORMATION_PATTERNS = (
    r"\bwhen\s+(will|does|do|is|are|can|should|would)\b",
    r"\bwhat time\b",
    r"\bis the\b[^.!?]*\bopen\b",
    r"\bupdate\b",
)

# Aid phrases are exempt from negation: "we cannot get the payment" and
# "not eligible" are the aid signal itself.
AID_PHRASES = (
    "payment",
    "compensation",
    "relief money",
    "aid",
    "eligible",
    "exception",
)
AID_PATTERNS = (r"\bhousehold list\b", r"\bthe list\b")
AID_EXCEPTION_PHRASES = (
    "cannot get",
    "can't get",
    "not eligible",
    "refused",
    "denied",
    "rejected",
    "exception",
)
AID_EXCEPTION_PATTERNS = (re.compile(r"\bnot on (?:the\s+)?\w*\s*list\b"),)

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

_WATER_AT_BUILDING = re.compile(
    r"\b(?:water|it)\s+(?:is\s+|was\s+)?"
    r"(?:at|near|over|up to|past|reaching|reached|against)\s+the\s+"
    r"(?:door|doorway|step|steps|stairs|floor)\b"
)
_WATER_INSIDE_HOUSE = re.compile(
    r"\b(?:water|it)\s+(?:is\s+|was\s+)?"
    r"(?:in|inside|entering|coming into|coming in)\s+the\s+"
    r"(?:house|home|room|rooms|flat)\b"
)
_WATER_IN_STREET = re.compile(
    r"\b(?:water|it)\s+(?:is\s+|was\s+)?"
    r"(?:in|inside|entering|coming into|coming in|near|along|at|past)\s+the\s+"
    r"(?:lane|road|street|soi)\b"
)
_WATER_AT_STREET_END = re.compile(
    r"\b(?:water|it)\s+(?:is\s+|was\s+)?at the end of the\s+"
    r"(?:lane|road|street|soi)\b"
)

VULNERABLE_PHRASES: dict[str, tuple[str, ...]] = {
    "elderly": ("grandmother", "grandfather", "elderly", "old"),
    "child": ("child", "baby", "kid", "son", "daughter", "infant"),
    "oxygen_dependent": ("oxygen",),
    "immobile": (
        "can't walk",
        "cannot walk",
        "wheelchair",
        "bedridden",
        "bed-bound",
        "immobile",
        "can't climb",
    ),
}

IMMOBILE_PATTERNS = (
    re.compile(
        r"\b(?:cannot|can't|unable to)\s+"
        r"(?:get out of bed|stand|walk|climb|move)\b"
    ),
)

MINIMISING_PHRASES = (
    "we are fine",
    "we're fine",
    "we're ok",
    "it's fine",
    "nothing serious",
    "no need to send",
    "do not make a fuss",
    "don't make a fuss",
    "only a little water",
    "it's nothing",
    "we only need",
    "just tell me",
)

ALONE_PHRASES = (
    "alone",
    "by myself",
    "no parent",
    "without an adult",
    "without a parent",
    "unaccompanied",
    "on their own",
    "can't find my mum",
    "can't find my dad",
    "can't find my parents",
    "lost my mum",
    "lost my dad",
    "lost my parents",
)

MINIMISING_VULNERABLE = {"child", "elderly", "immobile"}

# A bare English district name (no "District") matches only when it has two
# or more words and they are not all common English, so "Mae Mo" matches but
# "Hot", "Long", and "Than To" ("rather than to") do not.
COMMON_ENGLISH = {
    "a", "an", "the", "in", "on", "at", "to", "of", "and", "or", "is", "it",
    "be", "as", "by", "up", "so", "no", "go", "do", "me", "he", "we", "us",
    "than", "then", "that", "this", "with", "for", "from", "not", "but",
    "hot", "long", "song", "man", "him", "sing", "wang",
}

# Spellings callers use for gazetteer names (HDX COD-AB `name_en`). Each
# alias also matches bare.
DISTRICT_ALIASES = {
    "Watthana": "Vadhana",
    "Sathorn": "Sathon",
    "Pathumwan": "Pathum Wan",
    "Klong Toey": "Khlong Toei",
    "Khlong Toey": "Khlong Toei",
    "Ladprao": "Lat Phrao",
    "Lat Prao": "Lat Phrao",
    "Phayathai": "Phaya Thai",
    "Huay Kwang": "Huai Khwang",
    "Bangrak": "Bang Rak",
    "Thonburi": "Thon Buri",
    "Don Muang": "Don Mueang",
    "Jatujak": "Chatuchak",
}

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
}
_NUMBER = r"(one|two|three|four|five|six|seven|eight|nine|ten|\d+)"

_PEOPLE_COUNT = re.compile(_NUMBER + r"\s+(people|persons|adults|of us)\b")
_COUNT_PATTERNS = (
    re.compile(r"\bthere are " + _NUMBER + r"\b"),
    re.compile(r"\bwe are " + _NUMBER + r"\b"),
    re.compile(r"\ba family of " + _NUMBER + r"\b"),
)
_ME_AND_MY = re.compile(r"\bme and my [a-z]+\b")
_JUST_ME = re.compile(r"\b(just me|only me)\b")
_BARE_NUMBER = re.compile(r"^" + _NUMBER + r"\s*$")
_BREAKDOWN = re.compile(
    _NUMBER + r"\s+adults?\s+and\s+" + _NUMBER + r"\s+(?:child|children|kids?|infants?|babies)\b"
)


def _split(text: str) -> list[str]:
    return [part.lower() for part in _SENTENCE_END.split(text) if part.strip()]


_AFFIRMATIVE = re.compile(r"^\s*(yes|yeah|correct|that's right)\b")


def _confirmed_facts(transcript: list[TranscriptTurn]) -> list[str]:
    """Operator texts the caller confirmed with an affirmative first sentence.

    An operator question ("?") answered by "yes/yeah/correct/that's right"
    confirms the facts the operator stated. An answer that starts "No…"
    confirms nothing.
    """
    confirmed: list[str] = []
    for index, turn in enumerate(transcript[:-1]):
        if turn.speaker != "operator" or "?" not in turn.text:
            continue
        reply = transcript[index + 1]
        if reply.speaker != "caller":
            continue
        first = _split(reply.text)
        if first and _AFFIRMATIVE.match(first[0]):
            confirmed.append(turn.text)
    return confirmed


def _fact_sentences(transcript: list[TranscriptTurn]) -> list[str]:
    """Caller text plus operator-confirmed facts, in transcript order.

    Confirmed operator text counts for vulnerable, people_count, and danger
    only — never for needs or flags.
    """
    confirmed = set(_confirmed_facts(transcript))
    sentences: list[str] = []
    for turn in transcript:
        if turn.speaker == "caller" or turn.text in confirmed:
            sentences.extend(_split(turn.text))
    return sentences


def _sentences(transcript: list[TranscriptTurn]) -> list[str]:
    text = " ".join(turn.text for turn in transcript if turn.speaker == "caller")
    return _split(text)


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


def _match_need(sentence: str, need: Need, phrases: tuple[str, ...]) -> bool:
    for phrase in phrases:
        for match in re.finditer(r"\b" + re.escape(phrase) + r"\b", sentence):
            if _negated(sentence, match.start()):
                continue
            if need is Need.shelter:
                before = _WORD.findall(sentence[: match.start()])
                if before and before[-1] in SHELTER_SKIP_BEFORE:
                    continue
            return True
    return False


def _match_regex(sentence: str, pattern: re.Pattern) -> bool:
    return any(
        not _negated(sentence, match.start()) for match in pattern.finditer(sentence)
    )


def _district_entries(
    districts: list[str] | None,
) -> list[tuple[str, str, str | None, bool]]:
    """(match text, canonical English name, province or None, thai)."""
    if districts is not None:
        entries = []
        for entry in districts:
            name, _, province = entry.partition(",")
            canonical = name.strip()
            entries.append((canonical, canonical, province.strip() or None, False))
        return entries
    entries: list[tuple[str, str, str | None, bool]] = []
    seen: set[tuple[str, str | None, bool]] = set()

    def add(match: str | None, canonical: str | None, province: str | None, thai: bool) -> None:
        if not match or not canonical:
            return
        if thai and len(match) < 5 and not match.startswith("อำเภอ"):
            return
        key = (match, province, thai)
        if key in seen:
            return
        seen.add(key)
        entries.append((match, canonical, province, thai))

    from ingest.db import DB_PATH, connect
    from ingest.snapshots import read_snapshot

    if DB_PATH.exists():
        with connect() as conn:
            try:
                rows = conn.execute(
                    "SELECT name_en, name_th, province FROM admin_districts"
                ).fetchall()
            except Exception:  # noqa: BLE001 — a missing table means no gazetteer
                rows = []
            for row in rows:
                add(row["name_en"], row["name_en"], row["province"], False)
                add(row["name_th"], row["name_en"], row["province"], True)
            try:
                rows = conn.execute(
                    "SELECT name_en, name_th, province FROM districts"
                ).fetchall()
            except Exception:  # noqa: BLE001
                rows = []
            for row in rows:
                add(row["name_en"], row["name_en"], row["province"], False)
                add(row["name_th"], row["name_en"], row["province"], True)
    for row in (read_snapshot("gazetteer") or {}).get("districts") or []:
        canonical = row.get("name_en") or ""
        if canonical and not canonical.endswith("District"):
            canonical = f"{canonical} District"
        province = row.get("province_en") or None
        if province and not str(province).endswith("Province"):
            province = f"{province} Province"
        add(canonical, canonical, province, False)
        bare = row.get("name_en") or ""
        if _bare_name_ok(bare):
            add(bare, canonical, province, False)
        for alias, target in DISTRICT_ALIASES.items():
            if target == bare:
                add(alias, canonical, province, False)
                add(f"{alias} District", canonical, province, False)
        thai = row.get("name_th")
        add(thai, canonical, province, True)
        if thai and not str(thai).startswith("อำเภอ"):
            add(f"อำเภอ{thai}", canonical, province, True)
    return entries


def _bare_name_ok(name: str) -> bool:
    words = name.lower().split()
    return len(words) >= 2 and not all(word in COMMON_ENGLISH for word in words)


def _name_hit(match: str, text: str, thai: bool) -> bool:
    if not match:
        return False
    if thai:
        return match in text
    return re.search(r"\b" + re.escape(match.lower()) + r"\b", text) is not None


def _location(sentences: list[str], districts: list[str] | None) -> tuple[str | None, float | None]:
    entries = _district_entries(districts)
    ordered = entries
    if districts is None:
        ordered = sorted(entries, key=lambda item: len(item[0]), reverse=True)
    text = " ".join(sentences)
    found: tuple[str, str | None] | None = None
    for match, canonical, province, thai in ordered:
        if _name_hit(match, text, thai):
            found = (canonical, province)
            break
    if found is None:
        return None, None
    name, _province = found
    provinces: list[str] = []
    for _match, canonical, province, _thai in entries:
        if canonical == name and province and province not in provinces:
            provinces.append(province)
    if not provinces:
        return name, 0.85
    if len(provinces) == 1:
        return f"{name}, {provinces[0]}", 0.85
    for province in provinces:
        short = province.replace(" Province", "").lower()
        if re.search(r"\b" + re.escape(short) + r"\b", text):
            return f"{name}, {province}", 0.85
    return f"{name}, {provinces[0]}", 0.6


def _number(token: str) -> int:
    return int(token) if token.isdigit() else NUMBER_WORDS[token]


def _people_count(sentences: list[str]) -> int | None:
    count = None
    for sentence in sentences:
        stripped = sentence.strip()
        bare = _BARE_NUMBER.match(stripped)
        if bare:
            count = _number(bare.group(1))
        if _JUST_ME.search(stripped):
            count = 1
        if _ME_AND_MY.search(stripped):
            count = 2
        for pattern in (_PEOPLE_COUNT, *_COUNT_PATTERNS):
            for match in pattern.finditer(stripped):
                count = _number(match.group(1))
        breakdown = _BREAKDOWN.search(stripped)
        if breakdown:
            count = _number(breakdown.group(1)) + _number(breakdown.group(2))
    return count


def extract(
    transcript: list[TranscriptTurn],
    districts: list[str] | None = None,
) -> tuple[ExtractedFields, list[str]]:
    """Extract fields from caller turns and suggest policy flags."""
    sentences = _sentences(transcript)
    fact_sentences = _fact_sentences(transcript)
    needs: list[Need] = []
    for need, phrases in NEED_PHRASES:
        if any(_match_need(sentence, need, phrases) for sentence in sentences):
            needs.append(need)
    if any(re.search(pattern, sentence) for pattern in INFORMATION_PATTERNS for sentence in sentences):
        needs.append(Need.information)
    aid = any(
        re.search(r"\b" + re.escape(phrase) + r"\b", sentence)
        for sentence in sentences
        for phrase in AID_PHRASES
    ) or any(
        re.search(pattern, sentence)
        for sentence in sentences
        for pattern in AID_PATTERNS
    )
    if aid:
        needs.append(Need.aid_payment)

    water_at_door_or_house = False
    rising_water = False
    for sentence in fact_sentences:
        if _match_any(sentence, DANGER_PHRASES["rising_water"]):
            rising_water = True
        if _match_regex(sentence, _WATER_AT_BUILDING) or _match_regex(sentence, _WATER_INSIDE_HOUSE):
            rising_water = True
            water_at_door_or_house = True
        if _match_regex(sentence, _WATER_IN_STREET) or _match_regex(sentence, _WATER_AT_STREET_END):
            rising_water = True
    danger = ["rising_water"] if rising_water else []

    vulnerable = [
        tag
        for tag, phrases in VULNERABLE_PHRASES.items()
        if any(_match_any(sentence, phrases) for sentence in fact_sentences)
    ]
    if "immobile" not in vulnerable and any(
        _match_regex(sentence, pattern)
        for sentence in fact_sentences
        for pattern in IMMOBILE_PATTERNS
    ):
        vulnerable.append("immobile")

    vulnerable_hit = any(
        tag in vulnerable for tag in ("elderly", "immobile", "oxygen_dependent", "child")
    )
    if rising_water and (vulnerable_hit or water_at_door_or_house):
        if not (Need.evacuation in needs and not vulnerable_hit):
            needs.append(Need.rescue)

    medical = "oxygen_dependent" in vulnerable or Need.medical in needs
    location, confidence = _location(sentences, districts)
    fields = ExtractedFields(
        location=location,
        location_confidence=confidence,
        people_count=_people_count(fact_sentences),
        vulnerable=vulnerable,
        medical=medical,
        danger=danger,
        needs=needs,
    )
    flags: list[str] = []
    text = " ".join(sentences)
    minimising = any(phrase in text for phrase in MINIMISING_PHRASES)
    if minimising and (
        danger
        or Need.rescue in needs
        or Need.medical in needs
        or medical
        or any(tag in vulnerable for tag in MINIMISING_VULNERABLE)
    ):
        flags.append("conflicting_evidence")
    if "child" in vulnerable and any(phrase in text for phrase in ALONE_PHRASES):
        flags.append("safeguarding")
    if aid and (
        any(phrase in text for phrase in AID_EXCEPTION_PHRASES)
        or any(pattern.search(text) for pattern in AID_EXCEPTION_PATTERNS)
    ):
        flags.append("aid_exception")
    return fields, flags
