"""Write the golden scenarios, graduation set, and mock files.

Run once from the repo root. The JSON files are the artefacts the validator reads.
"""

from __future__ import annotations

import json
from pathlib import Path

from contracts.models import CaseState, MemoryItem, Outcome
from paths import ROOT

FIXTURES = ROOT / "fixtures"
MOCKS = ROOT / "mocks"

DISTRICTS = [
    "Mae Mo District, Lampang",
    "Mae Tha District, Lampang",
    "Sop Prap District, Lampang",
    "Den Chai District, Phrae",
    "Long District, Phrae",
    "Mueang Phrae District, Phrae",
    "Wang Chin District, Phrae",
    "Song District, Phrae",
    "Sung Men District, Phrae",
    "Rong Kwang District, Phrae",
    "Nong Muang Khai District, Phrae",
    "Wiang Sa District, Nan",
    "Ban Luang District, Nan",
    "Chiang Muan District, Phayao",
]


def turns(lines: list[tuple[str, str]]) -> list[dict]:
    clock = 0
    rows = []
    for index, (speaker, text) in enumerate(lines):
        if index:
            clock += 3800 + index * 250
        rows.append({"t_ms": clock, "speaker": speaker, "text": text})
    if not 4 <= len(rows) <= 12:
        raise RuntimeError(f"turn count {len(rows)}")
    return rows


def fields(**kwargs) -> dict:
    base = {
        "location": None,
        "location_confidence": None,
        "people_count": None,
        "vulnerable": [],
        "medical": False,
        "danger": [],
        "needs": [],
    }
    base.update(kwargs)
    return base


def scenario(
    fid: str,
    title: str,
    tags: list[str],
    dialogue: list[tuple[str, str]],
    field_values: dict,
    expected: dict,
    notes: str,
    caller: str,
    flags: list[str] | None = None,
    hour: int = 8,
) -> dict:
    stream = turns(dialogue)
    return {
        "id": fid,
        "title": title,
        "tags": tags,
        "transcript_stream": stream,
        "case_state": {
            "case_id": fid,
            "caller_id_hash": caller,
            "transcript": stream,
            "fields": field_values,
            "memory_context": [],
            "policy_flags": flags or [],
            "resources": {},
            "received_at": f"2026-10-23T{hour:02d}:15:00Z",
        },
        "expected": expected,
        "notes": notes,
    }


def expect(system, priority, route, needs, human, missing=None, questions=None) -> dict:
    return {
        "system": system,
        "priority": priority,
        "route": route,
        "needs": needs,
        "requires_human": human,
        "missing_evidence": missing or [],
        "acceptable_next_questions": questions or [],
    }


def s1_match(expected: dict, reason: str, confidence: float = 0.93) -> dict:
    return {
        "system": "system_1",
        "outcome": "fast_route",
        "priority": expected["priority"],
        "needs": expected["needs"],
        "route": expected["route"],
        "confidence": confidence,
        "reason": reason,
        "reasoning": None,
        "missing_evidence": expected["missing_evidence"],
        "next_question": None,
        "requires_human": expected["requires_human"],
        "escalate": False,
        "latency_ms": 22,
    }


def s1_defer(reason: str, priority: str = "P3", route: str = "information_only", needs=None) -> dict:
    return {
        "system": "system_1",
        "outcome": "escalate",
        "priority": priority,
        "needs": needs or ["information"],
        "route": route,
        "confidence": 0.42,
        "reason": reason,
        "reasoning": None,
        "missing_evidence": [],
        "next_question": None,
        "requires_human": False,
        "escalate": True,
        "latency_ms": 16,
    }


def s2_match(expected: dict, reason: str, reasoning: str) -> dict:
    question = None
    if expected["acceptable_next_questions"]:
        question = expected["acceptable_next_questions"][0]
    return {
        "system": "system_2",
        "outcome": "reasoned_recommendation",
        "priority": expected["priority"],
        "needs": expected["needs"],
        "route": expected["route"],
        "confidence": 0.84,
        "reason": reason,
        "reasoning": reasoning,
        "missing_evidence": expected["missing_evidence"],
        "next_question": question,
        "requires_human": expected["requires_human"],
        "escalate": False,
        "latency_ms": 88,
    }


def memory(memory_id: str, kind: str, summary: str, relevance: float, source: str | None) -> dict:
    return {
        "memory_id": memory_id,
        "kind": kind,
        "summary": summary,
        "relevance": relevance,
        "source_case_id": source,
    }


def build() -> list[dict]:
    d = DISTRICTS
    rows = []

    rows.append(scenario(
        "F01", "Drinking water, dry ground", ["system_1", "clear", "welfare"],
        [
            ("caller", "Hello, we need drinking water for the house."),
            ("operator", "Is anyone hurt, or is water inside the rooms?"),
            ("caller", "No. Um, the ground is dry. We just ran out of bottles."),
            ("operator", "Which district are you calling from?"),
            ("caller", f"We are in {d[0]}, near the blue temple."),
            ("operator", "How many people, and can you reach the market?"),
            ("caller", "Four of us. The market is open. We only need water."),
        ],
        fields(location=d[0], location_confidence=0.94, people_count=4, needs=["water"]),
        expect("system_1", "P3", "welfare_distribution", ["water"], False),
        "Clear same-day water request. District is complete and there is no danger sign.",
        "synthetic:f01", hour=8,
    ))

    rows.append(scenario(
        "F02", "Rice finished, no danger", ["system_1", "clear", "welfare"],
        [
            ("caller", "Our rice is finished. Can someone bring food today?"),
            ("operator", "Is the house flooding, or is anyone sick?"),
            ("caller", "Neither. Sorry, I should have said that first."),
            ("operator", "Where are you?"),
            ("caller", f"{d[1]}, by the invented stone arch. Not a street address."),
            ("operator", "How many people are eating there?"),
            ("caller", "Three. Two adults and one child. Everyone can walk."),
        ],
        fields(location=d[1], location_confidence=0.91, people_count=3, vulnerable=["child"], needs=["food"]),
        expect("system_1", "P3", "welfare_distribution", ["food"], False),
        "Food only, child is with adults, no medical need and no water in the house. A human may still want a welfare check because a child was mentioned.",
        "synthetic:f02", hour=9,
    ))

    rows.append(scenario(
        "F03", "Which shelter has space", ["system_1", "clear", "shelter"],
        [
            ("caller", "Which shelter still has space tonight?"),
            ("operator", "Are you in the water now?"),
            ("caller", "No. We are dry. We just want a place if the rain comes back."),
            ("operator", "Which district?"),
            ("caller", f"{d[2]}. We can see the invented green gate."),
            ("operator", "How many would come?"),
            ("caller", "Two adults. We have a motorbike and we can travel."),
        ],
        fields(location=d[2], location_confidence=0.9, people_count=2, needs=["shelter"]),
        expect("system_1", "P3", "shelter_placement", ["shelter"], False),
        "Shelter information while the callers are dry and mobile. Not a rescue.",
        "synthetic:f03", hour=9,
    ))

    rows.append(scenario(
        "F04", "Power cut, people are safe", ["system_1", "clear", "power"],
        [
            ("caller", "The power has been out since morning."),
            ("operator", "Is anyone trapped, or is there water near the house?"),
            ("caller", "No water. We are fine. We have candles."),
            ("operator", "Where is the house, at district level?"),
            ("caller", f"{d[3]}, near the invented clock tower."),
            ("operator", "Do you need a medic or a rescue?"),
            ("caller", "No. I only want to know when the power comes back."),
        ],
        fields(location=d[3], location_confidence=0.92, people_count=2, needs=["power"]),
        expect("system_1", "P3", "information_only", ["power"], False),
        "Power has no route of its own in config/routes.yaml, so this starting label uses information_only. Flagged for sign-off.",
        "synthetic:f04", hour=10,
    ))

    rows.append(scenario(
        "F05", "When is the flood update published", ["system_1", "clear", "information"],
        [
            ("caller", "What time does the district post the flood news?"),
            ("operator", "Are you calling because someone is in danger?"),
            ("caller", "No, no. Just the time of the update."),
            ("operator", "Which district are you asking about?"),
            ("caller", f"{d[4]}. I am at the invented tea stall."),
            ("operator", "Anyone with you who needs help today?"),
            ("caller", "Just me. This is only a question."),
        ],
        fields(location=d[4], location_confidence=0.95, people_count=1, needs=["information"]),
        expect("system_1", "P4", "information_only", ["information"], False),
        "Information only. No welfare and no danger.",
        "synthetic:f05", hour=10,
    ))

    rows.append(scenario(
        "F06", "Evacuation today, full details", ["system_1", "clear", "evacuation"],
        [
            ("caller", "They told our lane to move to a shelter today."),
            ("operator", "Is anyone unable to walk, or on oxygen?"),
            ("caller", "No. All five of us can walk. No medicine machines."),
            ("operator", "Which district, and do you already have a shelter name?"),
            ("caller", f"{d[5]}. They said the invented north hall. I do not know the road number."),
            ("operator", "Is water inside the house?"),
            ("caller", "Not yet. It is at the end of the lane. We should leave this afternoon."),
        ],
        fields(location=d[5], location_confidence=0.9, people_count=5, danger=["rising_water"], needs=["evacuation"]),
        expect("system_1", "P2", "shelter_placement", ["evacuation"], False),
        "Urgent evacuation with a known district and mobile people. requires_human is false in this starting label. Flagged: a human may want every evacuation confirmed.",
        "synthetic:f06", hour=11,
    ))

    rows.append(scenario(
        "F07", "Is the school open tomorrow", ["system_1", "clear", "information"],
        [
            ("caller", "Is the school open tomorrow?"),
            ("operator", "Which district is the school in?"),
            ("caller", f"{d[6]}. The invented riverside school, not a home."),
            ("operator", "Is your household flooding?"),
            ("caller", "No. I am only asking about the school."),
            ("operator", "Anyone sick at home?"),
            ("caller", "No. Thank you."),
        ],
        fields(location=d[6], location_confidence=0.93, people_count=1, needs=["information"]),
        expect("system_1", "P4", "information_only", ["information"], False),
        "Non-urgent question. P4 information_only.",
        "synthetic:f07", hour=11,
    ))

    shared = "synthetic:household-canal-08"
    rows.append(scenario(
        "F08", "First call from the canal household", ["system_1", "duplicate"],
        [
            ("caller", "We need drinking water. This is the household by the market canal."),
            ("operator", "Is water in the house?"),
            ("caller", "No. Dry floor. Three people."),
            ("operator", "Which district?"),
            ("caller", f"{d[7]}, near the invented blue shutter shop."),
            ("operator", "Has anyone called us about this already?"),
            ("caller", "I don't think so. First time."),
        ],
        fields(location=d[7], location_confidence=0.9, people_count=3, needs=["water"]),
        expect("system_1", "P3", "duplicate_merge", ["water"], False),
        "Pair with F09, same synthetic caller hash. Both are labelled duplicate_merge so the pair scores as a merge. A human may instead label only F09 as the duplicate and F08 as welfare_distribution. Flagged for sign-off.",
        shared, hour=12,
    ))
    rows.append(scenario(
        "F09", "Same household calls again", ["system_1", "duplicate"],
        [
            ("caller", "I called earlier about water for the market-canal household."),
            ("operator", "Are you the same household, still in the same district?"),
            ("caller", f"Yes. Still {d[7]}. Sorry, the wording is a bit different."),
            ("operator", "Did the water arrive?"),
            ("caller", "Not yet. We still need the bottles. Nobody is hurt."),
            ("operator", "Same three people?"),
            ("caller", "Yes. Please do not open a second case."),
        ],
        fields(location=d[7], location_confidence=0.92, people_count=3, needs=["water"]),
        expect("system_1", "P3", "duplicate_merge", ["water"], False),
        "Second call from the F08 household. Expected route is duplicate_merge. See the sign-off note on F08.",
        shared, hour=13,
    ))

    rows.append(scenario(
        "F10", "Oxygen-dependent elderly person, rising water", ["system_2", "medical"],
        [
            ("caller", "My mother uses oxygen at night. The water is rising in the lane."),
            ("operator", "Is the water inside the room yet?"),
            ("caller", "Not inside. It is coming up the step. I am worried."),
            ("operator", "How old is she, and can she walk?"),
            ("caller", "She is elderly. She cannot walk far without help."),
            ("operator", "Which district?"),
            ("caller", f"{d[8]}, near the invented blue temple. Please hurry."),
        ],
        fields(
            location=d[8], location_confidence=0.88, people_count=2,
            vulnerable=["elderly", "oxygen_dependent"], medical=True,
            danger=["rising_water"], needs=["rescue", "medical"],
        ),
        expect("system_2", "P1", "rescue_coordination", ["rescue", "medical"], True, ["water_depth"],
               ["Is the water still outside, or has it reached the doorway?"]),
        "Medical dependency plus rising water. Life-safety, human confirms the dispatch.",
        "synthetic:f10", hour=14,
    ))

    rows.append(scenario(
        "F11", "Immobile neighbour, water at the step", ["system_2", "medical"],
        [
            ("caller", "I am next door. The person here cannot get out of bed."),
            ("operator", "Is there a medical device, or an injury you can see?"),
            ("caller", "No injury I should describe. They are immobile. Water is at the step."),
            ("operator", "Are they elderly?"),
            ("caller", "Yes. Elderly, and they cannot stand."),
            ("operator", "District?"),
            ("caller", f"{d[9]}. The house with the invented yellow gate."),
        ],
        fields(
            location=d[9], location_confidence=0.86, people_count=2,
            vulnerable=["elderly", "immobile"], medical=True,
            danger=["rising_water"], needs=["rescue", "medical"],
        ),
        expect("system_2", "P1", "rescue_coordination", ["rescue", "medical"], True, ["mobility_aid"],
               ["Is there anyone who can help them move if the water rises?"]),
        "Immobile elderly person and water at the step. Non-graphic. Human required.",
        "synthetic:f11", hour=14,
    ))

    rows.append(scenario(
        "F12", "Near the blue temple, road unknown", ["system_2", "vague_location"],
        [
            ("caller", "Water is in the lane. I don't know the road name."),
            ("operator", "What can you see?"),
            ("caller", "We are near the blue temple. That is all I know."),
            ("operator", "Which district or province?"),
            ("caller", "Um, Lampang, I think. I am not sure of the district."),
            ("operator", "How many people?"),
            ("caller", "Four. We are still upstairs. The water is not at the door yet."),
        ],
        fields(
            location="near the blue temple, Lampang", location_confidence=0.28,
            people_count=4, danger=["rising_water"], needs=["rescue"],
        ),
        expect("system_2", "P2", "rescue_coordination", ["rescue"], True, ["precise_location"],
               ["Which district or road are you near?"]),
        "Vague landmark only. Labelled P2 rather than P1 because the caller is upstairs and the water is not at the door. Flagged: a human may call this P1.",
        "synthetic:f12", hour=15,
    ))

    rows.append(scenario(
        "F13", "Shelter question, district unknown", ["system_2", "vague_location"],
        [
            ("caller", "Where can we sleep if we have to leave?"),
            ("operator", "Which district are you in?"),
            ("caller", "I don't know the district. We just arrived."),
            ("operator", "Any landmark?"),
            ("caller", "A market, I think. I cannot read the sign."),
            ("operator", "Is anyone in danger right now?"),
            ("caller", "No. We are dry. We only need a shelter name."),
        ],
        fields(location=None, location_confidence=None, people_count=3, needs=["shelter"]),
        expect("system_2", "P3", "shelter_placement", ["shelter"], False, ["location"],
               ["Which district are you in?"]),
        "Missing location with no danger sign, so the starting label stays P3 and does not require a human. Flagged: the escalation note says a null location goes to System 2, which this does, but a human may still want requires_human true.",
        "synthetic:f13", hour=15,
    ))

    rows.append(scenario(
        "F14", "Caller says fine, water at the door", ["system_2", "conflicting"],
        [
            ("caller", "We're fine. Really. No need to send anyone."),
            ("operator", "I thought I heard water. Where is it?"),
            ("caller", "It is at the door. But we are fine, please."),
            ("operator", "Who is with you?"),
            ("caller", "Two of us. We can still stand in the room."),
            ("operator", "District?"),
            ("caller", f"{d[10]}. Do not make a fuss."),
        ],
        fields(
            location=d[10], location_confidence=0.84, people_count=2,
            danger=["rising_water"], needs=["rescue"],
        ),
        expect("system_2", "P2", "rescue_coordination", ["rescue"], True, ["whether_water_is_entering"],
               ["Has the water crossed the doorway?"]),
        "Caller minimises while describing water at the door. Cautious P2 rescue, not the caller's 'we are fine'. Flagged between P1 and P2.",
        "synthetic:f14", ["conflicting_evidence"], hour=16,
    ))

    rows.append(scenario(
        "F15", "Road question while a child is crying", ["system_2", "conflicting"],
        [
            ("caller", "Is the road still open?"),
            ("operator", "I can hear a child crying. Is the child with you?"),
            ("caller", "Yes. They are upset. We only need the road."),
            ("operator", "Is anyone hurt?"),
            ("caller", "No. Please just tell me if the road is open."),
            ("operator", "Which district?"),
            ("caller", f"{d[11]}. Near the invented bus shelter."),
        ],
        fields(location=d[11], location_confidence=0.8, people_count=2, vulnerable=["child"], needs=["information"]),
        expect("system_2", "P2", "supervisor_escalation", ["information"], True, ["who_is_with_the_caller"],
               ["Is the child safe and dry where you are?"]),
        "Non-graphic. The words say information, the background says distress. Starting label is supervisor_escalation. Flagged: a human may prefer a welfare route plus a question.",
        "synthetic:f15", ["conflicting_evidence"], hour=16,
    ))

    rows.append(scenario(
        "F16", "Unaccompanied child at a shelter", ["system_2", "safeguarding"],
        [
            ("caller", "I am a volunteer at the shelter. A child arrived without an adult."),
            ("operator", "Is the child hurt?"),
            ("caller", "No. They are dry and sitting with the volunteer desk."),
            ("operator", "Do you know a guardian?"),
            ("caller", "Not yet. I do not want to put their story on this call."),
            ("operator", "Which shelter, at district level only?"),
            ("caller", f"The invented North Canal hall, {d[5]}."),
        ],
        fields(location=f"invented North Canal hall, {d[5]}", location_confidence=0.8, people_count=1, vulnerable=["child"], needs=["shelter"]),
        expect("system_2", "P2", "supervisor_escalation", ["shelter"], True, ["guardian_contact_status"],
               ["Is a named guardian expected, or should a supervisor take this now?"]),
        "Safeguarding, kept non-graphic. No description of harm. Supervisor required.",
        "synthetic:f16", ["safeguarding"], hour=17,
    ))

    rows.append(scenario(
        "F17", "Renter told they are not eligible", ["system_2", "aid_exception"],
        [
            ("caller", "They said we cannot get the payment because we rent."),
            ("operator", "Is this about a payment decision, not a rescue?"),
            ("caller", "Yes. The neighbour rents too, and they received it."),
            ("operator", "Which district is the household in?"),
            ("caller", f"{d[12]}. I will not read out an address."),
            ("operator", "Anyone in danger tonight?"),
            ("caller", "No. We need a person to look at the exception."),
        ],
        fields(location=d[12], location_confidence=0.87, people_count=4, needs=["aid_payment"]),
        expect("system_2", "P3", "aid_caseworker", ["aid_payment"], True, ["eligibility_rule"],
               ["Do you want a caseworker to review the renter exception?"]),
        "Aid eligibility edge case. No rescue. Caseworker and a human.",
        "synthetic:f17", ["aid_exception"], hour=17,
    ))

    rows.append(scenario(
        "F18", "Extra person not on the household list", ["system_2", "aid_exception"],
        [
            ("caller", "My sister is staying with us. She is not on the payment list."),
            ("operator", "Are you asking for an exception to the household list?"),
            ("caller", "Yes. I don't know if that is allowed."),
            ("operator", "District?"),
            ("caller", f"{d[13]}. Same place as the rest of the household."),
            ("operator", "Is anyone unwell or in the water?"),
            ("caller", "No. This is only the payment question."),
        ],
        fields(location=d[13], location_confidence=0.86, people_count=5, needs=["aid_payment"]),
        expect("system_2", "P3", "aid_caseworker", ["aid_payment"], True, ["household_list_rule"],
               ["Should a caseworker review the extra person on the list?"]),
        "Second aid exception. Human caseworker. Not an automated denial.",
        "synthetic:f18", ["aid_exception"], hour=18,
    ))

    naive = "Naive fast reading would label this P3 welfare_distribution for water, because the caller asks for drinking water and does not say the word rescue."
    rows.append(scenario(
        "C01-a", "Water at the door, ground floor, elderly", ["system_2", "correction_pair"],
        [
            ("caller", "Can you send drinking water?"),
            ("operator", "Tell me about the water and who is there."),
            ("caller", "It is at the door of our ground-floor flat. My father is elderly."),
            ("operator", "Can he leave if the water comes in?"),
            ("caller", "Not quickly. I thought you only sent water, though."),
            ("operator", "Which district?"),
            ("caller", f"{d[4]}, near the invented blue temple."),
        ],
        fields(
            location=d[4], location_confidence=0.9, people_count=2,
            vulnerable=["elderly"], danger=["rising_water"], needs=["rescue"],
        ),
        expect("system_2", "P1", "rescue_coordination", ["rescue"], True, ["water_depth"],
               ["Is the water still only at the door?"]),
        naive + " The expected label is P1 rescue. The correction from this case should be retrieved on C01-b.",
        "synthetic:c01a", hour=18,
    ))
    rows.append(scenario(
        "C01-b", "Same pattern after the correction", ["system_2", "correction_pair"],
        [
            ("caller", "We need water bottles, if that is what you send."),
            ("operator", "Where is the water, and who is in the flat?"),
            ("caller", "Ground floor. Water is at the door. Grandmother is elderly."),
            ("operator", "Can she walk out?"),
            ("caller", "Only with help. The flat is the one by the invented mango tree."),
            ("operator", "District?"),
            ("caller", f"{d[6]}. Please check what you did for the similar call."),
        ],
        fields(
            location=d[6], location_confidence=0.9, people_count=2,
            vulnerable=["elderly"], danger=["rising_water"], needs=["rescue"],
        ),
        expect("system_2", "P1", "rescue_coordination", ["rescue"], True, ["water_depth"],
               ["Is the water still only at the door?"]),
        "Near-identical to C01-a. Once the C01-a correction is in memory, the retrieved context must name that correction. Expected label matches the corrected one, not the naive P3 water label.",
        "synthetic:c01b", hour=19,
    ))

    graduation = []
    variations = [
        ("G01", d[0], "Water is at the door of the ground-floor flat. Grandfather is elderly."),
        ("G02", d[1], "The water reached the door. Ground-floor room. The elderly neighbour cannot hurry."),
        ("G03", d[2], "Ankle-deep at the door, ground floor, and an elderly person is inside."),
        ("G04", d[3], "The water is at the front door. Ground-floor flat. Elderly resident, no oxygen."),
    ]
    for index, (fid, district, line) in enumerate(variations):
        graduation.append(scenario(
            fid, "Graduated pattern: door, ground floor, elderly", ["graduation", "system_1", "rescue"],
            [
                ("caller", line),
                ("operator", "Is this a ground-floor place, and is the elderly person mobile?"),
                ("caller", "Ground floor. They are elderly and slow. Not a medical machine."),
                ("operator", "Which district?"),
                ("caller", f"{district}, near the invented blue temple."),
                ("operator", "How many people?"),
                ("caller", "Two. We called because of the water at the door."),
            ],
            fields(
                location=district, location_confidence=0.91, people_count=2,
                vulnerable=["elderly"], danger=["rising_water"], needs=["rescue"],
            ),
            expect("system_1", "P1", "rescue_coordination", ["rescue"], True),
            "Illustrative S1 label after this pattern graduates. graduation_threshold in config/decisions.yaml is still TODO_HUMAN, so no rule was implemented. The stub only echoes this label.",
            f"synthetic:{fid.lower()}", hour=7 + index,
        ))
    return rows, graduation


MEDICAL_POLICY = (
    "Policy note: an oxygen-dependent or immobile person with rising water is a life-safety case and needs a human."
)


def memories_for(fid: str) -> list[dict]:
    if fid in {"F10", "F11"}:
        return [memory(f"mem-{fid}-policy", "policy", MEDICAL_POLICY, 0.9, None)]
    if fid == "F12":
        return [memory(
            "mem-f12-failure",
            "prior_failure",
            "A previous vague-landmark case was closed as information-only and the team could not find the household. Ask for a district before closing.",
            0.8,
            "synthetic-prior-case",
        )]
    if fid == "F02":
        return [memory(
            "mem-f02-similar",
            "similar_case",
            "Similar same-day food request in a known district, with no danger signs, was handled as welfare.",
            0.55,
            "synthetic-prior-food",
        )]
    if fid == "C01-a":
        return [memory(
            "mem-c01a-similar",
            "similar_case",
            "A similar water request was once treated as welfare. That outcome was later corrected.",
            0.7,
            "synthetic-prior-water",
        )]
    if fid == "C01-b":
        return [memory(
            "mem-c01b-correction",
            "correction",
            "Correction from C01-a: water at the door, plus a ground-floor flat, plus an elderly resident, is P1 rescue, not P3 welfare.",
            0.97,
            "C01-a",
        )]
    return []


def write_mocks(scenarios: list[dict]) -> None:
    for folder in ("memory_context", "s1_stub", "s2_stub"):
        path = MOCKS / folder
        path.mkdir(parents=True, exist_ok=True)
    for row in scenarios:
        fid = row["id"]
        expected = row["expected"]
        mem = memories_for(fid)
        for item in mem:
            MemoryItem.model_validate(item)
        (MOCKS / "memory_context" / f"{fid}.json").write_text(
            json.dumps(mem, indent=2) + "\n", encoding="utf-8"
        )
        if expected["system"] == "system_1":
            stub = s1_match(expected, row["notes"].split(".")[0] + ".")
        elif fid.startswith("C01-"):
            stub = s1_defer(
                "Naive fast reading treats this as a same-day water request and defers.",
                priority="P3",
                route="welfare_distribution",
                needs=["water"],
            )
        else:
            stub = s1_defer("Fast path defers this case to System 2.")
        Outcome.model_validate(stub)
        (MOCKS / "s1_stub" / f"{fid}.json").write_text(
            json.dumps(stub, indent=2) + "\n", encoding="utf-8"
        )
        if "system_2" in row["tags"]:
            reasoning = row["notes"]
            s2 = s2_match(expected, expected["priority"] + " " + expected["route"], reasoning)
            Outcome.model_validate(s2)
            (MOCKS / "s2_stub" / f"{fid}.json").write_text(
                json.dumps(s2, indent=2) + "\n", encoding="utf-8"
            )


def main() -> None:
    scenarios, graduation = build()
    (FIXTURES / "scenarios").mkdir(parents=True, exist_ok=True)
    (FIXTURES / "graduation").mkdir(parents=True, exist_ok=True)
    index_scenarios = []
    for row in scenarios:
        CaseState.model_validate(row["case_state"])
        path = FIXTURES / "scenarios" / f"{row['id']}.json"
        path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        index_scenarios.append({
            "id": row["id"],
            "title": row["title"],
            "tags": row["tags"],
            "path": f"scenarios/{row['id']}.json",
        })
    index_grad = []
    for row in graduation:
        CaseState.model_validate(row["case_state"])
        path = FIXTURES / "graduation" / f"{row['id']}.json"
        path.write_text(json.dumps(row, indent=2) + "\n", encoding="utf-8")
        index_grad.append({
            "id": row["id"],
            "title": row["title"],
            "tags": row["tags"],
            "path": f"graduation/{row['id']}.json",
        })
    index = {
        "scenarios": index_scenarios,
        "graduation": index_grad,
        "correction_pairs": [{"a": "C01-a", "b": "C01-b"}],
    }
    (FIXTURES / "index.json").write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    write_mocks(scenarios + graduation)
    resources = {
        "boats": [
            {
                "id": "boat-fictional-01",
                "kind": "boat",
                "name": "Fictional river boat A",
                "district": "Wang Chin District",
                "capacity": 6,
                "available": 2,
                "status": "available",
            }
        ],
        "ambulances": [
            {
                "id": "amb-fictional-01",
                "kind": "ambulance",
                "name": "Fictional clinic van 1",
                "district": "Mueang Phrae District",
                "capacity": 2,
                "available": 1,
                "status": "available",
            }
        ],
        "shelters": [
            {
                "id": "shelter-fictional-01",
                "kind": "shelter",
                "name": "Fictional North Canal hall",
                "district": "Den Chai District",
                "capacity": 80,
                "available": 30,
                "status": "open",
            }
        ],
        "welfare_points": [
            {
                "id": "welfare-fictional-01",
                "kind": "welfare_point",
                "name": "Fictional market-day water desk",
                "district": "Mae Mo District",
                "capacity": None,
                "available": 40,
                "status": "open",
            }
        ],
    }
    (MOCKS / "resources.json").write_text(json.dumps(resources, indent=2) + "\n", encoding="utf-8")
    print(f"scenarios {len(scenarios)} graduation {len(graduation)}")


if __name__ == "__main__":
    main()
