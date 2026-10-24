"""Synthetic call groups for the held-out correction scoreboard.

People, phones, and national ids are not used. Two groups can share a pattern
so a correction on one can change the stub label of the other. A group with no
sibling cannot move a held-out score by being corrected, because that group
is then not on the held-out side.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CallGroup:
    group_id: str
    pattern: str | None
    critical: bool
    priority: str
    route: str
    action: str
    base_priority: str
    base_route: str
    base_action: str
    sapling: str
    en: str
    th: str
    source: str = "human"


@dataclass(frozen=True)
class CallVariant:
    group_id: str
    language: str
    text: str
    pattern: str | None
    critical: bool
    priority: str
    route: str
    action: str
    base_priority: str
    base_route: str
    base_action: str
    sapling: str


GROUPS: tuple[CallGroup, ...] = (
    CallGroup(
        group_id="call-water-lampang",
        pattern="water",
        critical=False,
        priority="P3",
        route="welfare_distribution",
        action="create_provisional_dispatch",
        base_priority="P4",
        base_route="information_only",
        base_action="ask_next_question",
        sapling="n/a",
        en=(
            "Synthetic caller in Mueang Lampang District. "
            "Drinking water requested. Ground is dry. No danger signs."
        ),
        th=(
            "ผู้โทรสังเคราะห์ในอำเภอเมืองลำปาง "
            "ขอรับน้ำดื่ม พื้นดินแห้ง ไม่มีสัญญาณอันตราย"
        ),
    ),
    CallGroup(
        group_id="call-water-nan",
        pattern="water",
        critical=False,
        priority="P3",
        route="welfare_distribution",
        action="create_provisional_dispatch",
        base_priority="P4",
        base_route="information_only",
        base_action="ask_next_question",
        sapling="n/a",
        en=(
            "Synthetic caller in Mueang Nan District. "
            "Drinking water requested. Ground is dry. No danger signs."
        ),
        th=(
            "ผู้โทรสังเคราะห์ในอำเภอเมืองน่าน "
            "ขอรับน้ำดื่ม พื้นดินแห้ง ไม่มีสัญญาณอันตราย"
        ),
    ),
    CallGroup(
        group_id="call-critical-phrae",
        pattern="chest",
        critical=True,
        priority="P1",
        route="rescue_coordination",
        action="create_provisional_dispatch",
        base_priority="P3",
        base_route="welfare_distribution",
        base_action="ask_next_question",
        sapling="n/a",
        en=(
            "Synthetic caller in Mueang Phrae District. "
            "Water is at chest height inside the house. People cannot leave."
        ),
        th=(
            "ผู้โทรสังเคราะห์ในอำเภอเมืองแพร่ "
            "น้ำสูงถึงระดับอกในบ้าน คนออกไม่ได้"
        ),
    ),
    CallGroup(
        group_id="call-critical-phayao",
        pattern="chest",
        critical=True,
        priority="P1",
        route="rescue_coordination",
        action="create_provisional_dispatch",
        base_priority="P3",
        base_route="welfare_distribution",
        base_action="ask_next_question",
        sapling="n/a",
        en=(
            "Synthetic caller in Mueang Phayao District. "
            "Water is at chest height inside the house. People cannot leave."
        ),
        th=(
            "ผู้โทรสังเคราะห์ในอำเภอเมืองพะเยา "
            "น้ำสูงถึงระดับอกในบ้าน คนออกไม่ได้"
        ),
    ),
    CallGroup(
        group_id="call-aid",
        pattern="aid",
        critical=False,
        priority="P3",
        route="aid_caseworker",
        action="request_more_evidence",
        base_priority="P3",
        base_route="aid_caseworker",
        base_action="request_more_evidence",
        sapling="unsure",
        en=(
            "Synthetic caller in Mueang Lampang District. "
            "Asks whether this household can receive aid. No documents on the call."
        ),
        th=(
            "ผู้โทรสังเคราะห์ในอำเภอเมืองลำปาง "
            "ถามว่าครัวเรือนนี้รับความช่วยเหลือได้หรือไม่ ไม่มีเอกสารในสาย"
        ),
    ),
    CallGroup(
        group_id="call-shelter",
        pattern=None,
        critical=False,
        priority="P2",
        route="shelter_placement",
        action="create_provisional_dispatch",
        base_priority="P2",
        base_route="shelter_placement",
        base_action="create_provisional_dispatch",
        sapling="n/a",
        en=(
            "Synthetic caller in Mueang Nan District. "
            "The house is empty. The household needs a shelter bed tonight."
        ),
        th=(
            "ผู้โทรสังเคราะห์ในอำเภอเมืองน่าน "
            "บ้านว่าง ครัวเรือนต้องการที่พักพิงคืนนี้"
        ),
    ),
    CallGroup(
        group_id="call-signal-lampang",
        pattern="signal",
        critical=False,
        priority="P3",
        route="welfare_distribution",
        action="create_provisional_dispatch",
        base_priority="P4",
        base_route="information_only",
        base_action="ask_next_question",
        sapling="n/a",
        en=(
            "Synthetic caller in Mueang Lampang District. "
            "A coach marked this welfare request. Ground is dry."
        ),
        th=(
            "ผู้โทรสังเคราะห์ในอำเภอเมืองลำปาง "
            "โค้ชบันทึกคำขอสวัสดิการนี้ พื้นดินแห้ง"
        ),
        source="coach",
    ),
    CallGroup(
        group_id="call-signal-nan",
        pattern="signal",
        critical=False,
        priority="P3",
        route="welfare_distribution",
        action="create_provisional_dispatch",
        base_priority="P4",
        base_route="information_only",
        base_action="ask_next_question",
        sapling="n/a",
        en=(
            "Synthetic caller in Mueang Nan District. "
            "A coach marked this welfare request. Ground is dry."
        ),
        th=(
            "ผู้โทรสังเคราะห์ในอำเภอเมืองน่าน "
            "โค้ชบันทึกคำขอสวัสดิการนี้ พื้นดินแห้ง"
        ),
        source="coach",
    ),
)


def group_by_id() -> dict[str, CallGroup]:
    return {group.group_id: group for group in GROUPS}


def variants(groups: tuple[CallGroup, ...] = GROUPS) -> tuple[CallVariant, ...]:
    rows: list[CallVariant] = []
    for group in groups:
        for language, text in (("en", group.en), ("th", group.th)):
            rows.append(
                CallVariant(
                    group_id=group.group_id,
                    language=language,
                    text=text,
                    pattern=group.pattern,
                    critical=group.critical,
                    priority=group.priority,
                    route=group.route,
                    action=group.action,
                    base_priority=group.base_priority,
                    base_route=group.base_route,
                    base_action=group.base_action,
                    sapling=group.sapling,
                )
            )
    return tuple(rows)
