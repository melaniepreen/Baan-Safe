"""Generate the synthetic town the simulation renders.

The renderer does not invent layout. It reads the JSON this script writes:

- ui/sim/data/streets.json  romanised Sukhumvit names and centerlines
- ui/sim/data/flood.json    local-metre flood polygons, not WGS84
- ui/sim/data/town.json     buildings, households, graph, demo routes

Coordinates are metres on a local grid. y increases south, toward the camera.
They are not longitude/latitude and they are not street addresses.
Household objects stay inside the v0.2 Household contract: a district label,
never a house number.

Run from the repo root:

    python3 ui/sim/build_town.py
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).resolve().parent / "data"
FIXTURES = ROOT / "fixtures" / "scenarios"
MOCKS = ROOT / "mocks" / "resources.json"
MEMORY = ROOT / "mocks" / "memory_context"

# Vertical road centers (x) and horizontal road centers (y). y grows south.
# Soi Ho Nuea exists only south of the main road so the school can be one long block.
V_KHLONG, V_WAT, V_TALAT, V_HO, V_FAI = 48, 132, 228, 324, 420
H_BON, H_MAIN, H_LANG = 72, 196, 312


def r2(value: float) -> float:
    return round(float(value), 2)


def write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def point_in_ring(x: float, y: float, ring: list[list[float]]) -> bool:
    inside = False
    count = len(ring)
    for index in range(count):
        x1, y1 = ring[index]
        x2, y2 = ring[(index + 1) % count]
        if (y1 > y) != (y2 > y):
            x_cross = (x2 - x1) * (y - y1) / (y2 - y1 + 1e-12) + x1
            if x < x_cross:
                inside = not inside
    return inside


def depth_at(x: float, y: float, features: list[dict]) -> float:
    best = 0.0
    for feature in features:
        rings = feature["geometry"]["coordinates"]
        if not point_in_ring(x, y, rings[0]):
            continue
        if any(point_in_ring(x, y, hole) for hole in rings[1:]):
            continue
        best = max(best, float(feature["properties"]["depth_m"]))
    return best


def boxes_overlap(a: dict, b: dict, pad: float = 0.6) -> bool:
    return not (
        a["x"] + a["w"] + pad <= b["x"]
        or b["x"] + b["w"] + pad <= a["x"]
        or a["y"] + a["d"] + pad <= b["y"]
        or b["y"] + b["d"] + pad <= a["y"]
    )


def fixture_summary(fixture_id: str) -> dict:
    body = json.loads((FIXTURES / f"{fixture_id}.json").read_text(encoding="utf-8"))
    fields = body["case_state"]["fields"]
    return {
        "fixture_id": fixture_id,
        "title": body["title"],
        "expected_system": body["expected"]["system"],
        "expected_priority": body["expected"]["priority"],
        "expected_route": body["expected"]["route"],
        "expected_needs": body["expected"]["needs"],
        "requires_human": body["expected"]["requires_human"],
        "location": fields.get("location"),
        "people_count": fields.get("people_count"),
        "vulnerable": fields.get("vulnerable") or [],
        "danger": fields.get("danger") or [],
        "needs": fields.get("needs") or [],
        "opening": next(
            (turn["text"] for turn in body["transcript_stream"] if turn["speaker"] == "caller"),
            body["title"],
        ),
    }


def scenario_ids() -> list[str]:
    index = json.loads((ROOT / "fixtures" / "index.json").read_text(encoding="utf-8"))
    return [row["id"] for row in index["scenarios"]]


def household(fixture_id: str, summary: dict) -> dict:
    return {
        "household_id": f"hh-{fixture_id.lower()}",
        "member_ids": [f"synthetic:{fixture_id.lower()}"],
        "location_label": summary["location"],
        "people_count": summary["people_count"],
    }


def load_resources() -> list[dict]:
    snapshot = json.loads(MOCKS.read_text(encoding="utf-8"))
    units = []
    for group in ("boats", "ambulances", "shelters", "welfare_points"):
        for row in snapshot[group]:
            units.append(
                {
                    "resource_id": row["id"],
                    "kind": row["kind"],
                    "name": {
                        "boat-fictional-01": "Rescue boat",
                        "amb-fictional-01": "Clinic ambulance",
                        "shelter-fictional-01": "Evacuation shelter",
                        "welfare-fictional-01": "Sun Chuai Lue Nam Thuam",
                    }.get(row["id"], row["name"]),
                    "district": row["district"],
                    "available": row["available"],
                }
            )
    return units


def street(
    street_id: str,
    name_th: str,
    name_en: str,
    kind: str,
    axis: str,
    fixed: float,
    start: float,
    end: float,
    width_m: float,
    labels: list | None = None,
) -> dict:
    if axis == "h":
        points = [[start, fixed], [end, fixed]]
    else:
        points = [[fixed, start], [fixed, end]]
    row = {
        "id": street_id,
        "name_th": name_th,
        "name_en": name_en,
        "kind": kind,
        "axis": axis,
        "fixed": fixed,
        "start": start,
        "end": end,
        "width_m": width_m,
        "points": points,
        "poles": kind == "main",
    }
    if labels:
        row["labels"] = labels
    return row


def span_labels(north: str, south: str, start: float, end: float) -> list[dict]:
    """Odd soi on the north side of Thanon Sukhumvit, even soi on the south side."""
    span = end - start

    def row(name: str, y: float) -> dict:
        return {"name_th": name, "name_en": name, "t": round((y - start) / span, 4)}

    return [row(north, (start + H_MAIN) / 2), row(south, (H_MAIN + end) / 2)]


def build_streets() -> list[dict]:
    return [
        street(
            "thanon-chamlong-nam-thuam",
            "Thanon Sukhumvit",
            "Thanon Sukhumvit",
            "main",
            "h",
            H_MAIN,
            16,
            524,
            16,
        ),
        street(
            "soi-chamlong-bon",
            "Thanon Phetchaburi Tat Mai",
            "Thanon Phetchaburi Tat Mai",
            "soi",
            "h",
            H_BON,
            56,
            470,
            6.5,
        ),
        street(
            "soi-chamlong-lang",
            "Thanon At Narong",
            "Thanon At Narong",
            "soi",
            "h",
            H_LANG,
            56,
            490,
            7,
        ),
        street(
            "soi-chamlong-khlong",
            "Soi Sukhumvit 39",
            "Soi Sukhumvit 39",
            "soi",
            "v",
            V_KHLONG,
            24,
            400,
            5.5,
            labels=span_labels("Soi Sukhumvit 39", "Soi Sukhumvit 24", 24, 400),
        ),
        street(
            "soi-chamlong-wat-fa",
            "Soi Sukhumvit 49",
            "Soi Sukhumvit 49",
            "soi",
            "v",
            V_WAT,
            24,
            400,
            7,
            labels=span_labels("Soi Sukhumvit 49", "Soi Sukhumvit 36", 24, 400),
        ),
        street(
            "soi-chamlong-talat",
            "Soi Sukhumvit 55",
            "Soi Sukhumvit 55",
            "soi",
            "v",
            V_TALAT,
            32,
            396,
            7,
            labels=span_labels("Soi Sukhumvit 55", "Soi Sukhumvit 38", 32, 396),
        ),
        street(
            "soi-chamlong-ho-nuea",
            "Soi Sukhumvit 40",
            "Soi Sukhumvit 40",
            "soi",
            "v",
            V_HO,
            H_MAIN,
            404,
            7.5,
        ),
        street(
            "soi-chamlong-fai",
            "Soi Sukhumvit 63",
            "Soi Sukhumvit 63",
            "soi",
            "v",
            V_FAI,
            40,
            380,
            6.5,
            labels=span_labels("Soi Sukhumvit 63", "Soi Sukhumvit 42", 40, 380),
        ),
        street("khlong-chamlong", "Khlong Saen Saep", "Khlong Saen Saep", "canal", "v", 22, 30, 400, 14),
    ]


def build_flood() -> dict:
    temple_hole = [[142, 326], [220, 326], [220, 392], [142, 392]]
    features = [
        poly(
            "haz-flood-canal",
            1.6,
            "Khlong Saen Saep along the west edge of the block.",
            [[[0, 8], [34, 8], [34, 412], [0, 412]]],
        ),
        poly(
            "haz-flood-south-deep",
            0.9,
            "Deeper standing water in the southern lanes. The Wat That Thong compound is the dry hole.",
            [[[30, 328], [530, 328], [530, 412], [30, 412]], temple_hole],
        ),
        poly(
            "haz-flood-streets",
            0.45,
            "Shallow floodwater on Thanon Sukhumvit and the lanes south of it.",
            [[[30, 180], [530, 180], [530, 328], [30, 328]]],
        ),
        poly(
            "haz-flood-soi-khlong",
            0.35,
            "Water sitting in the northern section of Soi Sukhumvit 39.",
            [[[V_KHLONG - 4, 40], [V_KHLONG + 4, 40], [V_KHLONG + 4, 180], [V_KHLONG - 4, 180]]],
        ),
        poly(
            "haz-flood-soi-wat-fa",
            0.35,
            "Water sitting in the northern section of Soi Sukhumvit 49.",
            [[[V_WAT - 4.2, 36], [V_WAT + 4.2, 36], [V_WAT + 4.2, 180], [V_WAT - 4.2, 180]]],
        ),
        poly(
            "haz-flood-soi-talat",
            0.35,
            "Water sitting in the northern section of Soi Sukhumvit 55.",
            [[[V_TALAT - 4.2, 40], [V_TALAT + 4.2, 40], [V_TALAT + 4.2, 180], [V_TALAT - 4.2, 180]]],
        ),
        poly(
            "haz-flood-soi-fai",
            0.35,
            "Water sitting in the northern section of Soi Sukhumvit 63.",
            [[[V_FAI - 4, 48], [V_FAI + 4, 48], [V_FAI + 4, 180], [V_FAI - 4, 180]]],
        ),
        poly(
            "haz-flood-soi-bon",
            0.3,
            "Shallow water on Thanon Phetchaburi Tat Mai.",
            [[[56, H_BON - 3.6], [470, H_BON - 3.6], [470, H_BON + 3.6], [56, H_BON + 3.6]]],
        ),
    ]
    return {
        "type": "FeatureCollection",
        "properties": {
            "crs_note": "Local metres. x east, y south toward the fixed camera. Not WGS84. Not a household address.",
            "live_layer": "/map/flood is the ingested WGS84 flood polygons. This file is the block overlay.",
        },
        "features": features,
    }


def poly(hazard_id: str, depth_m: float, summary: str, rings: list) -> dict:
    return {
        "type": "Feature",
        "properties": {
            "hazard_id": hazard_id,
            "kind": "flood",
            "summary": summary,
            "location_label": "Sukhumvit, Watthana",
            "depth_m": depth_m,
        },
        "geometry": {"type": "Polygon", "coordinates": rings},
    }


def hazards_from(flood: dict) -> list[dict]:
    return [
        {
            "hazard_id": feature["properties"]["hazard_id"],
            "kind": "flood",
            "summary": feature["properties"]["summary"],
            "location_label": "Sukhumvit, Watthana",
        }
        for feature in flood["features"]
    ]


def base_building(**kwargs) -> dict:
    building = {
        "id": kwargs["id"],
        "kind": kwargs["kind"],
        "name_th": kwargs.get("name_th"),
        "name_en": kwargs.get("name_en"),
        "x": r2(kwargs["x"]),
        "y": r2(kwargs["y"]),
        "w": r2(kwargs["w"]),
        "d": r2(kwargs["d"]),
        "floors": kwargs["floors"],
        "roof": kwargs["roof"],
        "wall": kwargs.get("wall", "plaster"),
        "street_id": kwargs.get("street_id"),
        "household": kwargs.get("household"),
        "fixture_id": kwargs.get("fixture_id"),
        "fixture": kwargs.get("fixture"),
        "resource_id": kwargs.get("resource_id"),
        "sim_status": kwargs.get("sim_status", "clear"),
        "water_m": r2(kwargs.get("water_m", 0)),
        "tiers": kwargs.get("tiers"),
        "landmark": kwargs.get("landmark", False),
    }
    return {key: value for key, value in building.items() if value is not None}


_THAI_SCRIPT = re.compile(r"[\u0e00-\u0e7f]")


def place_label(building_id: str, fallback_th: str, fallback_en: str) -> tuple[str, str]:
    """Romanised name for this plot.

    ui/sim/data/places.json keeps the Lampang, Phrae, Nan, and Phayao catalog.
    A Thai label from that catalog is not drawn on the Sukhumvit block.
    """
    path = ROOT / "ui" / "sim" / "data" / "places.json"
    if not path.is_file():
        return fallback_th, fallback_en
    label = (json.loads(path.read_text(encoding="utf-8")).get("labels") or {}).get(building_id) or {}
    name_th = label.get("name_th") or fallback_th
    name_en = label.get("name_en") or fallback_en
    if _THAI_SCRIPT.search(name_th) or _THAI_SCRIPT.search(name_en):
        return fallback_th, fallback_en
    return name_th, name_en


def landmarks(resources: dict[str, dict], summaries: dict[str, dict]) -> list[dict]:
    def res(resource_id: str) -> str:
        if resource_id not in resources:
            raise SystemExit(f"missing mock resource {resource_id}")
        return resource_id

    return [
        base_building(
            id="bldg-school",
            kind="school",
            name_th=place_label("bldg-school", "XCL American School", "XCL American School")[0],
            name_en=place_label("bldg-school", "XCL American School", "XCL American School")[1],
            x=238,
            y=92,
            w=122,
            d=34,
            floors=4,
            roof="pink",
            wall="plaster",
            street_id="soi-chamlong-bon",
            landmark=True,
        ),
        base_building(
            id="bldg-tower-white",
            kind="concrete",
            name_th=place_label("bldg-tower-white", "White apartment block", "White apartment block")[0],
            name_en=place_label("bldg-tower-white", "White apartment block", "White apartment block")[1],
            x=436,
            y=22,
            w=26,
            d=24,
            floors=5,
            roof="flat_white",
            wall="concrete",
            street_id="soi-chamlong-fai",
            landmark=True,
        ),
        base_building(
            id="bldg-tower-pink",
            kind="concrete",
            name_th=place_label("bldg-tower-pink", "Baan Chompoo Apartment", "Baan Chompoo Apartment")[0],
            name_en=place_label("bldg-tower-pink", "Baan Chompoo Apartment", "Baan Chompoo Apartment")[1],
            x=58,
            y=18,
            w=24,
            d=22,
            floors=4,
            roof="flat_pink",
            wall="concrete",
            street_id="soi-chamlong-khlong",
            landmark=True,
        ),
        base_building(
            id="bldg-shelter",
            kind="shelter",
            name_th="Evacuation shelter",
            name_en="Evacuation shelter",
            x=236,
            y=158,
            w=42,
            d=22,
            floors=2,
            roof="grey",
            wall="plaster",
            street_id="thanon-chamlong-nam-thuam",
            resource_id=res("shelter-fictional-01"),
            landmark=True,
        ),
        base_building(
            id="bldg-clinic",
            kind="clinic",
            name_th="Clinic",
            name_en="Clinic",
            x=392,
            y=158,
            w=18,
            d=16,
            floors=2,
            roof="flat_white",
            wall="concrete",
            street_id="thanon-chamlong-nam-thuam",
            resource_id=res("amb-fictional-01"),
            landmark=True,
        ),
        base_building(
            id="bldg-welfare",
            kind="welfare",
            name_th="Sun Chuai Lue Nam Thuam",
            name_en="Sun Chuai Lue Nam Thuam",
            x=156,
            y=40,
            w=12,
            d=8,
            floors=1,
            roof="grey",
            wall="plaster",
            street_id="soi-chamlong-talat",
            resource_id=res("welfare-fictional-01"),
            landmark=True,
        ),
        base_building(
            id="bldg-jetty",
            kind="jetty",
            name_th="Jetty",
            name_en="Jetty",
            x=8,
            y=188,
            w=18,
            d=12,
            floors=1,
            roof="brown",
            wall="wood",
            street_id="khlong-chamlong",
            resource_id=res("boat-fictional-01"),
            landmark=True,
            water_m=0.4,
        ),
        base_building(
            id="bldg-temple",
            kind="temple",
            name_th="Wat That Thong",
            name_en="Wat That Thong",
            x=158,
            y=334,
            w=30,
            d=20,
            floors=1,
            roof="brown_tiered",
            wall="wood",
            street_id="soi-chamlong-wat-fa",
            tiers=3,
            landmark=True,
            water_m=0,
        ),
        base_building(
            id="bldg-sala",
            kind="temple",
            name_th=place_label("bldg-sala", "Sala", "Sala")[0],
            name_en=place_label("bldg-sala", "Sala", "Sala")[1],
            x=150,
            y=360,
            w=16,
            d=12,
            floors=1,
            roof="brown_tiered",
            wall="wood",
            street_id="soi-chamlong-wat-fa",
            tiers=2,
            landmark=True,
            water_m=0,
        ),
        base_building(
            id="bldg-stupa",
            kind="stupa",
            name_th="Chedi",
            name_en="Chedi",
            x=198,
            y=344,
            w=9,
            d=9,
            floors=1,
            roof="stupa",
            wall="plaster",
            street_id="soi-chamlong-talat",
            landmark=True,
            water_m=0,
        ),
        fixture_house("bldg-f01", "F01", summaries, 148, 22, 10, 11, "soi-chamlong-wat-fa", "clear", 0, "red", 1),
        fixture_house("bldg-f04", "F04", summaries, 444, 158, 12, 12, "soi-chamlong-fai", "clear", 0, "blue", 2),
        fixture_house(
            "bldg-f06", "F06", summaries, 334, 214, 11, 12, "soi-chamlong-ho-nuea", "at_risk", 0.08, "red", 2
        ),
        fixture_house(
            "bldg-f08", "F08", summaries, 60, 226, 10, 11, "soi-chamlong-khlong", "flooded", 1.1, "grey", 1
        ),
        fixture_house(
            "bldg-f10", "F10", summaries, 142, 228, 10, 12, "soi-chamlong-wat-fa", "needs_help", 0.4, "blue", 2
        ),
        fixture_house(
            "bldg-f12", "F12", summaries, 168, 292, 10, 11, "soi-chamlong-talat", "at_risk", 0.2, "grey", 2
        ),
    ]


def water_status(x: float, y: float, w: float, d: float, floors: int, flood: dict) -> tuple[str, float]:
    water = depth_at(x + w / 2, y + d / 2, flood["features"])
    if water >= 0.75 and floors == 1:
        status = "flooded"
    elif water >= 0.25:
        status = "at_risk"
    else:
        status = "clear"
    return status, water


def fixture_house(
    building_id: str,
    fixture_id: str,
    summaries: dict[str, dict],
    x: float,
    y: float,
    w: float,
    d: float,
    street_id: str,
    status: str,
    water_m: float,
    roof: str,
    floors: int,
) -> dict:
    summary = summaries[fixture_id]
    stored = {key: value for key, value in summary.items() if key != "opening"}
    return base_building(
        id=building_id,
        kind="house",
        x=x,
        y=y,
        w=w,
        d=d,
        floors=floors,
        roof=roof,
        wall="plaster",
        street_id=street_id,
        household=household(fixture_id, summary),
        fixture_id=fixture_id,
        fixture=stored,
        sim_status=status,
        water_m=water_m,
        landmark=True,
    )


def place_remaining(summaries: dict[str, dict], flood: dict) -> list[dict]:
    """Houses for the scenario calls that are not already a landmark.

    F07 is the school question, F16 is the shelter volunteer, and F09 is the
    same household as F08. Those three attach to buildings that already exist.
    """
    specs = [
        ("F02", 90, 24, "soi-chamlong-bon", "red", 1),
        ("F03", 300, 22, "soi-chamlong-bon", "blue", 1),
        ("F05", 372, 22, "soi-chamlong-fai", "grey", 1),
        ("F11", 88, 252, "soi-chamlong-khlong", "blue", 1),
        ("F13", 188, 22, "soi-chamlong-wat-fa", "grey", 1),
        ("F14", 70, 338, "soi-chamlong-lang", "red", 1),
        ("F15", 250, 348, "soi-chamlong-talat", "grey", 2),
        ("F17", 368, 236, "soi-chamlong-ho-nuea", "red", 2),
        ("F18", 456, 236, "soi-chamlong-fai", "blue", 1),
        ("C01-a", 188, 248, "soi-chamlong-wat-fa", "red", 1),
        ("C01-b", 368, 348, "soi-chamlong-lang", "grey", 1),
    ]
    houses = []
    for fixture_id, x, y, street_id, roof, floors in specs:
        status, water = water_status(x, y, 10, 11, floors, flood)
        houses.append(
            fixture_house(
                f"bldg-{fixture_id.lower()}",
                fixture_id,
                summaries,
                x,
                y,
                10,
                11,
                street_id,
                status,
                water,
                roof,
                floors,
            )
        )
    return houses


def attach_call(building: dict, fixture_id: str, summaries: dict[str, dict]) -> None:
    summary = summaries[fixture_id]
    building["fixture_id"] = fixture_id
    building["fixture"] = {key: value for key, value in summary.items() if key != "opening"}
    building["household"] = household(fixture_id, summary)
    building["landmark"] = True


def memory_lines(fixture_id: str) -> list[dict]:
    path = MEMORY / f"{fixture_id}.json"
    if not path.exists():
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    return [{"kind": row.get("kind"), "summary": row.get("summary")} for row in rows]


def build_calls(ids: list[str], summaries: dict[str, dict], buildings: list[dict]) -> list[dict]:
    by_fixture: dict[str, str] = {}
    for building in buildings:
        if building.get("fixture_id"):
            by_fixture[building["fixture_id"]] = building["id"]
        for extra in building.get("also_fixture_ids") or []:
            by_fixture[extra] = building["id"]
    calls = []
    for fixture_id in ids:
        summary = summaries[fixture_id]
        if fixture_id not in by_fixture:
            raise SystemExit(f"no building for call {fixture_id}")
        calls.append(
            {
                "id": fixture_id,
                "title": summary["title"],
                "opening": summary["opening"],
                "building_id": by_fixture[fixture_id],
                "expected_priority": summary["expected_priority"],
                "expected_system": summary["expected_system"],
                "expected_route": summary["expected_route"],
                "memory": memory_lines(fixture_id),
            }
        )
    return calls


def fill_houses(rng: random.Random, reserved: list[dict], flood: dict, trees: list[dict]) -> list[dict]:
    """Pack ordinary lots into the blocks between the drawn roads."""
    blocks = [
        # North of the upper soi. Columns skip Soi Ho Nuea; that lane starts at the main road.
        (54, 14, 126, 66),
        (138, 14, 222, 66),
        (234, 14, 414, 66),
        (428, 14, 520, 66),
        # Between the upper soi and the main road. The wide middle cell holds the school.
        (54, 78, 126, 184),
        (138, 78, 222, 184),
        (234, 78, 414, 184),
        (428, 78, 516, 184),
        # South of the main road, four cells plus the strip east of the power-line soi.
        (54, 208, 126, 306),
        (138, 208, 222, 306),
        (234, 208, 318, 306),
        (332, 208, 414, 306),
        (428, 208, 508, 306),
        # Foreground, toward the camera. The temple compound is reserved inside the second cell.
        (54, 320, 126, 396),
        (138, 320, 222, 396),
        (234, 320, 318, 396),
        (332, 320, 414, 396),
        (428, 320, 500, 388),
    ]
    houses: list[dict] = []
    serial = 1
    for x0, y0, x1, y1 in blocks:
        y = y0 + 1.2
        while y + 10 < y1:
            row_depth = 10.5 if y < 320 else 11
            x = x0 + 1.0
            while x + 7.2 < x1:
                if rng.random() < 0.22:
                    pocket = rng.uniform(9, 14)
                    tree_box = {"x": x + 1, "y": y + 1, "w": 6, "d": row_depth - 2}
                    if pocket > 8 and not any(boxes_overlap(tree_box, other, 0.2) for other in reserved):
                        trees.append(
                            {
                                "id": f"tree-p{len(trees) + 1:03d}",
                                "kind": "rain",
                                "x": r2(x + pocket * 0.45),
                                "y": r2(y + row_depth * 0.5),
                                "r": rng.choice([8, 9, 10, 11]),
                            }
                        )
                    x += pocket
                    continue
                width = rng.choice([7.6, 8.4, 9.2, 10.2, 11.4])
                depth = row_depth - rng.choice([0, 0.4, 0.8])
                if x + width > x1 - 0.8:
                    break
                lot = {"x": x, "y": y, "w": width, "d": depth}
                if any(boxes_overlap(lot, other) for other in reserved):
                    x += width + 1.2
                    continue
                south = y >= 320
                shophouse = abs((y + depth) - 186) < 6 or abs(y - 208) < 4
                if south and rng.random() < 0.62:
                    kind, roof, wall, floors = "wood_house", "brown", "wood", 1
                elif shophouse:
                    kind, wall, floors = "shophouse", "plaster", 2
                    roof = rng.choice(["red", "blue", "grey"])
                else:
                    kind, wall = "house", "plaster"
                    roof = rng.choices(["red", "blue", "grey"], weights=[5, 3, 3])[0]
                    floors = rng.choices([1, 2, 3], weights=[3, 6, 1])[0]
                center_x = x + width / 2
                center_y = y + depth / 2
                water = depth_at(center_x, center_y, flood["features"])
                if water >= 0.75 and floors == 1:
                    status = "flooded"
                elif water >= 0.25:
                    status = "at_risk"
                else:
                    status = "clear"
                building_id = f"bldg-{serial:04d}"
                serial += 1
                lot_full = base_building(
                    id=building_id,
                    kind=kind,
                    x=x,
                    y=y,
                    w=width,
                    d=depth,
                    floors=floors,
                    roof=roof,
                    wall=wall,
                    street_id=None,
                    household={
                        "household_id": f"hh-{building_id}",
                        "member_ids": [f"synthetic:{building_id}"],
                        "location_label": None,
                        "people_count": rng.randint(1, 6),
                    },
                    sim_status=status,
                    water_m=water,
                )
                houses.append(lot_full)
                reserved.append(lot_full)
                x += width + rng.uniform(1.1, 2.4)
            y += row_depth + rng.uniform(2.4, 3.6)
    mark_evacuated(rng, houses)
    return houses


def mark_evacuated(rng: random.Random, houses: list[dict]) -> None:
    candidates = [
        house
        for house in houses
        if house["sim_status"] in {"flooded", "at_risk"} and house["y"] > 240 and house["kind"] != "shophouse"
    ]
    rng.shuffle(candidates)
    for house in candidates[:4]:
        house["sim_status"] = "evacuated"


def hand_trees() -> list[dict]:
    specs = [
        (36, 120, 14),
        (36, 210, 15),
        (36, 300, 13),
        (36, 370, 12),
        (100, 196, 11),
        (168, 196, 10),
        (280, 196, 12),
        (360, 188, 11),
        (470, 196, 10),
        (180, 318, 16),
        (210, 378, 14),
        (150, 390, 12),
        (250, 150, 9),
        (200, 70, 13),
        (300, 48, 12),
        (90, 40, 11),
        (500, 80, 13),
        (70, 340, 12),
        (360, 350, 14),
        (450, 340, 11),
        (260, 250, 10),
        (400, 250, 11),
    ]
    trees = []
    for index, (x, y, radius) in enumerate(specs, start=1):
        trees.append({"id": f"tree-{index:03d}", "kind": "rain", "x": x, "y": y, "r": radius})
    return trees


def gap_trees(rng: random.Random, buildings: list[dict], trees: list[dict]) -> None:
    spots = [(90, 100), (180, 120), (300, 200), (380, 280), (120, 260), (480, 250), (250, 360), (80, 180)]
    serial = len(trees) + 1
    for x, y in spots:
        if any(abs(tree["x"] - x) < 8 and abs(tree["y"] - y) < 8 for tree in trees):
            continue
        trees.append({"id": f"tree-{serial:03d}", "kind": "rain", "x": x, "y": y, "r": rng.choice([8, 9, 10])})
        serial += 1
    kept = []
    for tree in trees:
        blocked = False
        for building in buildings:
            if (
                building["x"] - 1 <= tree["x"] <= building["x"] + building["w"] + 1
                and building["y"] - 1 <= tree["y"] <= building["y"] + building["d"] + 1
            ):
                blocked = True
                break
        if not blocked:
            kept.append(tree)
    trees[:] = kept


def graph_from_streets(streets: list[dict], flood: dict) -> dict:
    horizontals = [row for row in streets if row["axis"] == "h"]
    verticals = [row for row in streets if row["axis"] == "v"]
    points: dict[tuple[float, float], str] = {}

    def node(x: float, y: float) -> str:
        key = (r2(x), r2(y))
        if key not in points:
            points[key] = f"n{len(points) + 1:03d}"
        return points[key]

    raw_edges: list[tuple[str, str, str, float, float]] = []

    def add_edge(a: str, b: str, street_id: str, x1: float, y1: float, x2: float, y2: float) -> None:
        if abs(x1 - x2) < 0.05 and abs(y1 - y2) < 0.05:
            return
        raw_edges.append((a, b, street_id, r2((x1 + x2) / 2), r2((y1 + y2) / 2)))

    for road in horizontals:
        y = road["fixed"]
        xs = [road["start"], road["end"]]
        for other in verticals:
            if other["start"] - 0.01 <= y <= other["end"] + 0.01 and road["start"] - 0.01 <= other["fixed"] <= road["end"] + 0.01:
                xs.append(other["fixed"])
        xs = sorted({r2(value) for value in xs})
        for left, right in zip(xs, xs[1:]):
            add_edge(node(left, y), node(right, y), road["id"], left, y, right, y)
    for road in verticals:
        x = road["fixed"]
        ys = [road["start"], road["end"]]
        for other in horizontals:
            if other["start"] - 0.01 <= x <= other["end"] + 0.01 and road["start"] - 0.01 <= other["fixed"] <= road["end"] + 0.01:
                ys.append(other["fixed"])
        ys = sorted({r2(value) for value in ys})
        for top, bottom in zip(ys, ys[1:]):
            add_edge(node(x, top), node(x, bottom), road["id"], x, top, x, bottom)

    street_kind = {row["id"]: row["kind"] for row in streets}
    edges = []
    for index, (start, end, street_id, mid_x, mid_y) in enumerate(raw_edges, start=1):
        # Recover length from node table after all nodes exist.
        edges.append(
            {
                "id": f"e{index:03d}",
                "from": start,
                "to": end,
                "street_id": street_id,
                "mid_x": mid_x,
                "mid_y": mid_y,
                "kind": street_kind[street_id],
            }
        )
    nodes = [{"id": node_id, "x": x, "y": y} for (x, y), node_id in points.items()]
    by_id = {row["id"]: row for row in nodes}
    finished = []
    for edge in edges:
        a = by_id[edge["from"]]
        b = by_id[edge["to"]]
        length = ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5
        water = depth_at(edge["mid_x"], edge["mid_y"], flood["features"])
        if edge["kind"] == "canal" or water >= 1.2:
            modes = ["boat"]
        else:
            modes = []
            if water < 0.85:
                modes.append("foot")
            if water < 0.28:
                modes.append("road")
            if water >= 0.25:
                modes.append("boat")
        finished.append(
            {
                "id": edge["id"],
                "from": edge["from"],
                "to": edge["to"],
                "street_id": edge["street_id"],
                "length_m": r2(length),
                "depth_m": r2(water),
                "modes": modes,
            }
        )
    finished = subdivide(nodes, finished, 42)
    return {"nodes": nodes, "edges": finished}


def subdivide(nodes: list[dict], edges: list[dict], max_len: float) -> list[dict]:
    by_id = {row["id"]: row for row in nodes}
    serial_n = len(nodes) + 1
    serial_e = 1
    output = []
    for edge in edges:
        a = by_id[edge["from"]]
        b = by_id[edge["to"]]
        pieces = max(1, int(edge["length_m"] // max_len))
        chain = [a]
        for step in range(1, pieces):
            t = step / pieces
            node = {
                "id": f"n{serial_n:03d}",
                "x": r2(a["x"] + (b["x"] - a["x"]) * t),
                "y": r2(a["y"] + (b["y"] - a["y"]) * t),
            }
            serial_n += 1
            nodes.append(node)
            by_id[node["id"]] = node
            chain.append(node)
        chain.append(b)
        for left, right in zip(chain, chain[1:]):
            length = ((left["x"] - right["x"]) ** 2 + (left["y"] - right["y"]) ** 2) ** 0.5
            output.append(
                {
                    "id": f"e{serial_e:03d}",
                    "from": left["id"],
                    "to": right["id"],
                    "street_id": edge["street_id"],
                    "length_m": r2(length),
                    "depth_m": edge["depth_m"],
                    "modes": list(edge["modes"]),
                }
            )
            serial_e += 1
    return output


def closest_on_edges(x: float, y: float, graph: dict, modes: set[str]) -> tuple[dict, float, float]:
    by_id = {row["id"]: row for row in graph["nodes"]}
    best = None
    best_d = 1e18
    best_point = (x, y)
    for edge in graph["edges"]:
        if modes.isdisjoint(edge["modes"]):
            continue
        a = by_id[edge["from"]]
        b = by_id[edge["to"]]
        dx, dy = b["x"] - a["x"], b["y"] - a["y"]
        length_sq = dx * dx + dy * dy
        t = 0.0 if length_sq == 0 else max(0.0, min(1.0, ((x - a["x"]) * dx + (y - a["y"]) * dy) / length_sq))
        px, py = a["x"] + dx * t, a["y"] + dy * t
        dist = (px - x) ** 2 + (py - y) ** 2
        if dist < best_d:
            best_d = dist
            best = edge
            best_point = (px, py)
    if best is None:
        raise SystemExit(f"no edge for modes {modes}")
    return best, best_point[0], best_point[1]


def insert_anchor(graph: dict, x: float, y: float, modes: list[str]) -> str:
    """Drop a driveway from a building centroid onto the nearest edge that allows `modes`."""
    edge, px, py = closest_on_edges(x, y, graph, set(modes))
    by_id = {row["id"]: row for row in graph["nodes"]}
    a = by_id[edge["from"]]
    b = by_id[edge["to"]]

    def nearest_end(node: dict) -> bool:
        return (node["x"] - px) ** 2 + (node["y"] - py) ** 2 <= 1.0

    if nearest_end(a):
        split_id, px, py = a["id"], a["x"], a["y"]
    elif nearest_end(b):
        split_id, px, py = b["id"], b["x"], b["y"]
    else:
        split_id = f"n{len(graph['nodes']) + 1:03d}"
        graph["nodes"].append({"id": split_id, "x": r2(px), "y": r2(py)})
        graph["edges"] = [row for row in graph["edges"] if row["id"] != edge["id"]]
        serial = len(graph["edges"]) + 1

        def link(start: dict, end_id: str, end_x: float, end_y: float) -> None:
            nonlocal serial
            length = ((start["x"] - end_x) ** 2 + (start["y"] - end_y) ** 2) ** 0.5
            if length < 0.4:
                return
            graph["edges"].append(
                {
                    "id": f"e{serial:03d}",
                    "from": start["id"],
                    "to": end_id,
                    "street_id": edge["street_id"],
                    "length_m": r2(length),
                    "depth_m": edge["depth_m"],
                    "modes": list(edge["modes"]),
                }
            )
            serial += 1
            graph["_edge_seq"] = serial

        link(a, split_id, px, py)
        link({"id": split_id, "x": r2(px), "y": r2(py)}, b["id"], b["x"], b["y"])

    driveway = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
    anchor_id = f"n{len(graph['nodes']) + 1:03d}"
    graph["nodes"].append({"id": anchor_id, "x": r2(x), "y": r2(y)})
    if driveway < 0.4:
        return split_id
    serial = len(graph["edges"]) + 1
    graph["edges"].append(
        {
            "id": f"e{serial:03d}",
            "from": anchor_id,
            "to": split_id,
            "street_id": edge["street_id"],
            "length_m": r2(driveway),
            "depth_m": edge["depth_m"],
            "modes": modes,
        }
    )
    return anchor_id


def shortest(graph: dict, start: str, goal: str, mode: str) -> list[str]:
    import heapq

    adj: dict[str, list[tuple[str, float]]] = {row["id"]: [] for row in graph["nodes"]}
    for edge in graph["edges"]:
        if mode not in edge["modes"]:
            continue
        adj[edge["from"]].append((edge["to"], edge["length_m"]))
        adj[edge["to"]].append((edge["from"], edge["length_m"]))
    dist = {start: 0.0}
    prev: dict[str, str] = {}
    heap = [(0.0, start)]
    while heap:
        so_far, current = heapq.heappop(heap)
        if current == goal:
            break
        if so_far != dist.get(current):
            continue
        for nxt, weight in adj[current]:
            candidate = so_far + weight
            if candidate < dist.get(nxt, 1e18):
                dist[nxt] = candidate
                prev[nxt] = current
                heapq.heappush(heap, (candidate, nxt))
    if goal not in dist:
        raise SystemExit(f"no {mode} path from {start} to {goal}")
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    return path


def path_length(graph: dict, node_ids: list[str]) -> float:
    by_id = {row["id"]: row for row in graph["nodes"]}
    total = 0.0
    for left, right in zip(node_ids, node_ids[1:]):
        a, b = by_id[left], by_id[right]
        total += ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5
    return r2(total)


def centroid(building: dict) -> tuple[float, float]:
    return building["x"] + building["w"] / 2, building["y"] + building["d"] / 2


def _interior(building: dict, x: float, y: float, pad: float = 0.05) -> bool:
    return (
        building["x"] + pad < x < building["x"] + building["w"] - pad
        and building["y"] + pad < y < building["y"] + building["d"] - pad
    )


def _hits_others(buildings: list[dict], x1: float, y1: float, x2: float, y2: float, ignore_id: str) -> bool:
    steps = max(4, int((((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5) / 1.5))
    for step in range(1, steps):
        t = step / steps
        x = x1 + (x2 - x1) * t
        y = y1 + (y2 - y1) * t
        for building in buildings:
            if building["id"] == ignore_id:
                continue
            if _interior(building, x, y, 0.05):
                return True
    return False


def _on_street(x: float, y: float, streets: list[dict], slack: float = 1.2) -> bool:
    for street in streets:
        half = street["width_m"] / 2 + slack
        if street["axis"] == "h":
            if street["start"] - 0.5 <= x <= street["end"] + 0.5 and abs(y - street["fixed"]) <= half:
                return True
        elif street["start"] - 0.5 <= y <= street["end"] + 0.5 and abs(x - street["fixed"]) <= half:
            return True
    return False


def join_street(graph: dict, x: float, y: float) -> str:
    """Split the nearest street edge at (x, y) and return that node. No driveway."""
    edge, px, py = closest_on_edges(x, y, graph, {"foot", "road", "boat"})
    by_id = {row["id"]: row for row in graph["nodes"]}
    a = by_id[edge["from"]]
    b = by_id[edge["to"]]

    def nearest_end(node: dict) -> bool:
        return (node["x"] - px) ** 2 + (node["y"] - py) ** 2 <= 1.0

    if nearest_end(a):
        return a["id"]
    if nearest_end(b):
        return b["id"]
    split_id = f"n{len(graph['nodes']) + 1:03d}"
    graph["nodes"].append({"id": split_id, "x": r2(px), "y": r2(py)})
    graph["edges"] = [row for row in graph["edges"] if row["id"] != edge["id"]]
    serial = graph.setdefault("_edge_seq", len(graph["edges"]) + 50)

    def link(start: dict, end_id: str, end_x: float, end_y: float) -> None:
        nonlocal serial
        length = ((start["x"] - end_x) ** 2 + (start["y"] - end_y) ** 2) ** 0.5
        if length < 0.4:
            return
        graph["edges"].append(
            {
                "id": f"e{serial:03d}",
                "from": start["id"],
                "to": end_id,
                "street_id": edge["street_id"],
                "length_m": r2(length),
                "depth_m": edge["depth_m"],
                "modes": list(edge["modes"]),
                "lane": False,
            }
        )
        serial += 1

    link(a, split_id, px, py)
    link({"id": split_id, "x": r2(px), "y": r2(py)}, b["id"], b["x"], b["y"])
    graph["_edge_seq"] = serial
    return split_id


def _add_node(graph: dict, x: float, y: float) -> str:
    for node in graph["nodes"]:
        if abs(node["x"] - x) < 0.35 and abs(node["y"] - y) < 0.35:
            return node["id"]
    node_id = f"n{len(graph['nodes']) + 1:03d}"
    graph["nodes"].append({"id": node_id, "x": r2(x), "y": r2(y)})
    return node_id


def _add_edge(graph: dict, start: str, end: str, modes: list[str], lane: bool, depth: float, street_id: str) -> None:
    if start == end:
        return
    for edge in graph["edges"]:
        if {edge["from"], edge["to"]} == {start, end}:
            return
    by_id = {row["id"]: row for row in graph["nodes"]}
    a, b = by_id[start], by_id[end]
    length = ((a["x"] - b["x"]) ** 2 + (a["y"] - b["y"]) ** 2) ** 0.5
    if length < 0.3:
        return
    serial = graph.setdefault("_edge_seq", len(graph["edges"]) + 50)
    graph["_edge_seq"] = serial + 1
    graph["edges"].append(
        {
            "id": f"e{serial:03d}",
            "from": start,
            "to": end,
            "street_id": street_id,
            "length_m": r2(length),
            "depth_m": r2(depth),
            "modes": modes,
            "lane": lane,
        }
    )


def _straight_access(building: dict, buildings: list[dict], streets: list[dict]) -> list[tuple[float, float]] | None:
    """A single clear segment from the frontage to a street centerline."""
    cx, cy = centroid(building)
    best = None
    best_len = 1e18
    for street in streets:
        if street["axis"] == "h":
            if not (street["start"] <= cx <= street["end"]):
                continue
            px, py = cx, street["fixed"]
        else:
            if not (street["start"] <= cy <= street["end"]):
                continue
            px, py = street["fixed"], cy
        door_x = min(max(px, building["x"]), building["x"] + building["w"])
        door_y = min(max(py, building["y"]), building["y"] + building["d"])
        # Step just outside the footprint, toward the street.
        if abs(door_y - building["y"]) < 0.08:
            door_y -= 0.6
        elif abs(door_y - (building["y"] + building["d"])) < 0.08:
            door_y += 0.6
        elif abs(door_x - building["x"]) < 0.08:
            door_x -= 0.6
        elif abs(door_x - (building["x"] + building["w"])) < 0.08:
            door_x += 0.6
        length = ((door_x - px) ** 2 + (door_y - py) ** 2) ** 0.5
        if length < 0.8 or length > 48 or length >= best_len:
            continue
        if _hits_others(buildings, door_x, door_y, px, py, building["id"]):
            continue
        if _interior(building, (door_x + px) / 2, (door_y + py) / 2, -0.2):
            continue
        best = [(r2(door_x), r2(door_y)), (r2(px), r2(py))]
        best_len = length
    return best


def _astar_access(building: dict, buildings: list[dict], streets: list[dict]) -> list[tuple[float, float]] | None:
    cell = 1.5
    cols = int(540 / cell)
    rows = int(420 / cell)

    def blocked(i: int, j: int) -> bool:
        if i < 0 or j < 0 or i >= cols or j >= rows:
            return True
        x, y = (i + 0.5) * cell, (j + 0.5) * cell
        if _on_street(x, y, streets, 0.4):
            return False
        for other in buildings:
            if _interior(other, x, y, 0.02):
                return True
        return False

    cx, cy = centroid(building)
    starts = []
    for x, y in (
        (cx, building["y"] - 1.1),
        (cx, building["y"] + building["d"] + 1.1),
        (building["x"] - 1.1, cy),
        (building["x"] + building["w"] + 1.1, cy),
    ):
        i, j = int(x / cell), int(y / cell)
        if not blocked(i, j):
            starts.append((i, j))
    if not starts:
        return None
    import heapq

    heap = []
    prev: dict[tuple[int, int], tuple[int, int]] = {}
    cost = {}
    for start in starts:
        heapq.heappush(heap, (0, start[0], start[1]))
        cost[start] = 0
    found = None
    seen = 0
    while heap and seen < 20000:
        so_far, i, j = heapq.heappop(heap)
        if cost.get((i, j)) != so_far:
            continue
        seen += 1
        x, y = (i + 0.5) * cell, (j + 0.5) * cell
        if _on_street(x, y, streets, 0.2) and (i, j) not in starts:
            found = (i, j)
            break
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nxt = (i + di, j + dj)
            if blocked(*nxt):
                continue
            nx, ny = (nxt[0] + 0.5) * cell, (nxt[1] + 0.5) * cell
            step = 1 if _on_street(nx, ny, streets, 0.4) else 6
            candidate = so_far + step
            if candidate < cost.get(nxt, 1e18):
                cost[nxt] = candidate
                prev[nxt] = (i, j)
                heapq.heappush(heap, (candidate, nxt[0], nxt[1]))
    if found is None:
        return None
    cells = [found]
    while cells[-1] not in starts and cells[-1] in prev:
        cells.append(prev[cells[-1]])
    cells.reverse()
    points = [((i + 0.5) * cell, (j + 0.5) * cell) for i, j in cells]
    simple = [points[0]]
    for point in points[1:]:
        if len(simple) >= 2:
            ax, ay = simple[-2]
            bx, by = simple[-1]
            if (abs(ax - bx) < 0.2 and abs(bx - point[0]) < 0.2) or (
                abs(ay - by) < 0.2 and abs(by - point[1]) < 0.2
            ):
                simple[-1] = point
                continue
        simple.append(point)
    return [(r2(x), r2(y)) for x, y in simple]


def link_building(graph: dict, building: dict, buildings: list[dict], streets: list[dict], flood: dict) -> str:
    """Connect a frontage to the street graph. Returns the door node."""
    cached = graph.setdefault("_doors", {})
    if building["id"] in cached:
        return cached[building["id"]]
    points = _straight_access(building, buildings, streets) or _astar_access(building, buildings, streets)
    if not points:
        raise SystemExit(f"no clear access lane for {building['id']}")
    street_node = join_street(graph, points[-1][0], points[-1][1])
    door = _add_node(graph, points[0][0], points[0][1])
    previous = door
    street_id = "lane-" + building["id"]
    for x, y in points[1:-1]:
        nxt = _add_node(graph, x, y)
        depth = depth_at((x + points[0][0]) / 2, (y + points[0][1]) / 2, flood["features"])
        _add_edge(graph, previous, nxt, ["foot"], True, depth, street_id)
        previous = nxt
    end_x, end_y = points[-1]
    by_id = {row["id"]: row for row in graph["nodes"]}
    landing = by_id[street_node]
    depth = depth_at((points[0][0] + end_x) / 2, (points[0][1] + end_y) / 2, flood["features"])
    straight = len(points) == 2
    clear = straight and not _hits_others(buildings, points[0][0], points[0][1], end_x, end_y, building["id"])
    modes = ["foot"]
    if depth < 0.85:
        modes = ["foot"]
    elif clear and depth >= 0.25:
        modes = ["boat"]
    else:
        modes = ["foot"]
    if depth >= 0.25 and clear and depth < 0.85:
        modes = ["foot", "boat"]
    _add_edge(graph, previous, street_node, modes, True, depth, street_id)
    # Keep the stored door on the frontage even if the street node is the start.
    if abs(landing["x"] - points[0][0]) < 0.4 and abs(landing["y"] - points[0][1]) < 0.4:
        door = street_node
    cached[building["id"]] = door
    return door


def _incident_modes(graph: dict, node_id: str) -> set[str]:
    modes: set[str] = set()
    for edge in graph["edges"]:
        if node_id in (edge["from"], edge["to"]):
            modes.update(edge["modes"])
    return modes


def _edge_mode(edge: dict, prefer: str) -> str:
    if prefer in edge["modes"]:
        return prefer
    for mode in ("foot", "road", "boat"):
        if mode in edge["modes"]:
            return mode
    return edge["modes"][0]


def _multimodal(graph: dict, start: str, goal: str, prefer: str) -> list[dict] | None:
    """Shortest path that may change mode where the drawn edge changes mode."""
    if start == goal:
        return [{"mode": prefer, "node_ids": [start]}]
    import heapq

    adj: dict[str, list[tuple[str, float, str]]] = {row["id"]: [] for row in graph["nodes"]}
    for edge in graph["edges"]:
        if not edge["modes"]:
            continue
        mode = _edge_mode(edge, prefer)
        adj[edge["from"]].append((edge["to"], edge["length_m"], mode))
        adj[edge["to"]].append((edge["from"], edge["length_m"], mode))
    dist = {start: 0.0}
    prev: dict[str, tuple[str, str]] = {}
    heap = [(0.0, start)]
    while heap:
        so_far, current = heapq.heappop(heap)
        if current == goal:
            break
        if so_far != dist.get(current):
            continue
        for nxt, weight, mode in adj[current]:
            candidate = so_far + weight
            if candidate < dist.get(nxt, 1e18):
                dist[nxt] = candidate
                prev[nxt] = (current, mode)
                heapq.heappush(heap, (candidate, nxt))
    if goal not in dist:
        return None
    nodes = [goal]
    modes = []
    while nodes[-1] != start:
        earlier, mode = prev[nodes[-1]]
        modes.append(mode)
        nodes.append(earlier)
    nodes.reverse()
    modes.reverse()
    legs = []
    bucket = [nodes[0]]
    current = modes[0] if modes else prefer
    for node, mode in zip(nodes[1:], modes):
        if mode != current:
            legs.append({"mode": current, "node_ids": bucket})
            bucket = [bucket[-1], node]
            current = mode
        else:
            bucket.append(node)
    legs.append({"mode": current, "node_ids": bucket})
    return legs


def _legs(graph: dict, origin: str, dest: str, prefer: str) -> tuple[list[dict], str | None]:
    legs = _multimodal(graph, origin, dest, prefer)
    if not legs:
        return [], "No connected path on the drawn roads or water."
    used = {leg["mode"] for leg in legs}
    note = None
    if used != {prefer}:
        note = (
            f"Preferred {prefer}. The drawn network changes mode along this run: "
            + ", ".join(leg["mode"] for leg in legs)
            + "."
        )
    return legs, note


def build_response_routes(
    graph: dict,
    buildings: dict[str, dict],
    calls: list[dict],
    streets: list[dict],
    flood: dict,
) -> list[dict]:
    """One drawn path per call from the depot that priority uses.

    Rescue prefers the jetty by boat. Evacuation and welfare prefer foot,
    and use a flooded street only when that street is the connected mode.
    """
    bases = {
        "rescue": "bldg-jetty",
        "evac": "bldg-shelter",
        "welfare": "bldg-welfare",
        "notice": "bldg-school",
    }
    roles = {
        "rescue": ("bldg-jetty", "boat", "rescue_coordination"),
        "evac": ("bldg-shelter", "foot", "shelter_placement"),
        "welfare": ("bldg-welfare", "foot", "welfare_distribution"),
        "notice": ("bldg-school", "foot", "information_only"),
    }
    all_buildings = list(buildings.values())
    doors = {}
    for building_id in {call["building_id"] for call in calls} | set(bases.values()):
        doors[building_id] = link_building(graph, buildings[building_id], all_buildings, streets, flood)
    routes = []
    seen = set()
    for call in calls:
        for role, (base_id, prefer, contract) in roles.items():
            key = (call["building_id"], role)
            if key in seen:
                # Second call on the same house (F09) reuses the geometry.
                previous = next(row for row in routes if row["building_id"] == call["building_id"] and row["role"] == role)
                routes.append({**previous, "id": f"resp-{call['id']}-{role}", "call_id": call["id"]})
                continue
            seen.add(key)
            origin = doors[base_id]
            dest = doors[call["building_id"]]
            # Rescue and supply run from the depot to the house.
            # Evacuation runs from the house to the shelter, which is the same street path.
            start, goal = (dest, origin) if role == "evac" else (origin, dest)
            legs, note = _legs(graph, start, goal, prefer)
            if not legs:
                raise SystemExit(f"no {role} path for {call['id']}: {note}")
            length = 0.0
            for leg in legs:
                length += path_length(graph, leg["node_ids"])
                for left, right in zip(leg["node_ids"], leg["node_ids"][1:]):
                    if not any(
                        leg["mode"] in edge["modes"] and {edge["from"], edge["to"]} == {left, right}
                        for edge in graph["edges"]
                    ):
                        raise SystemExit(f"gap in {call['id']} {role}")
            routes.append(
                {
                    "id": f"resp-{call['id']}-{role}",
                    "call_id": call["id"],
                    "building_id": call["building_id"],
                    "base_id": base_id,
                    "role": role,
                    "prefer": prefer,
                    "contract_route": contract,
                    "legs": legs,
                    "length_m": r2(length),
                    "note": note,
                }
            )
    graph.pop("_doors", None)
    graph.pop("_edge_seq", None)
    return routes


def build_routes(graph: dict, buildings: dict[str, dict]) -> list[dict]:
    specs = [
        {
            "id": "route-f06-evac",
            "label": "F06 walk to the evacuation shelter",
            "fixture_id": "F06",
            "contract_route": "shelter_placement",
            "needs": ["evacuation"],
            "mode": "foot",
            "from_building": "bldg-f06",
            "to_building": "bldg-shelter",
        },
        {
            "id": "route-f10-rescue",
            "label": "F10 boat from the jetty",
            "fixture_id": "F10",
            "contract_route": "rescue_coordination",
            "needs": ["rescue", "medical"],
            "mode": "boat",
            "from_building": "bldg-jetty",
            "to_building": "bldg-f10",
        },
    ]
    routes = []
    for spec in specs:
        start_b = buildings[spec["from_building"]]
        end_b = buildings[spec["to_building"]]
        sx, sy = centroid(start_b)
        ex, ey = centroid(end_b)
        start_node = insert_anchor(graph, sx, sy, [spec["mode"]])
        end_node = insert_anchor(graph, ex, ey, [spec["mode"]])
        node_ids = shortest(graph, start_node, end_node, spec["mode"])
        routes.append(
            {
                **spec,
                "from_node": start_node,
                "to_node": end_node,
                "node_ids": node_ids,
                "length_m": path_length(graph, node_ids),
                "source": "mock",
                "note": (
                    "contracts.Route is the dispatch category, not a polyline. "
                    "This path is the shortest allowed walk on the drawn street graph."
                ),
            }
        )
    return routes


def main() -> None:
    rng = random.Random(1370)
    ids = scenario_ids()
    summaries = {fixture_id: fixture_summary(fixture_id) for fixture_id in ids}
    resources = {row["resource_id"]: row for row in load_resources()}
    streets = build_streets()
    flood = build_flood()
    special = landmarks(resources, summaries)
    for building in special:
        if building["id"] == "bldg-f08":
            building["also_fixture_ids"] = ["F09"]
        if building["id"] == "bldg-school":
            attach_call(building, "F07", summaries)
        if building["id"] == "bldg-shelter":
            attach_call(building, "F16", summaries)
    special.extend(place_remaining(summaries, flood))
    for index, left in enumerate(special):
        for right in special[index + 1 :]:
            if boxes_overlap(left, right, 0.4):
                raise SystemExit(f"call buildings overlap: {left['id']} and {right['id']}")
    reserved = [dict(row) for row in special]
    reserved.append({"id": "temple-grounds", "x": 144, "y": 324, "w": 78, "d": 70})
    trees = hand_trees()
    houses = fill_houses(rng, reserved, flood, trees)
    buildings = houses + special
    gap_trees(rng, buildings, trees)
    graph = graph_from_streets(streets, flood)
    by_building = {row["id"]: row for row in buildings}
    calls = build_calls(ids, summaries, buildings)
    response_routes = build_response_routes(graph, by_building, calls, streets, flood)
    routes = build_routes(graph, by_building)
    town = {
        "meta": {
            "id": "synthetic-operator-block",
            "title": "Sukhumvit block, Watthana",
            "district_anchor": (
                "Fixture households stay labelled with their district (Lampang, Phrae, Nan, Phayao). "
                "data.demo_event is still TODO_HUMAN. Drawn streets use Sukhumvit names in local metres."
            ),
            "disclaimer": (
                "Local-metre picture of streets around Soi Sukhumvit 49 in Watthana, Bangkok. Not a cadastral survey. "
                "EOS-RS eos-rs-thailand-flood-bangkok-sep-2026 is listed in data/SOURCES.md and was not fetched. "
                "Household location_label stays the fixture district. Plots are local metres, not home addresses. "
                "Wat That Thong stands on Thanon Sukhumvit beside BTS Ekkamai; this block draws the compound on the south side of the drawn road. "
                "Khlong Saen Saep is drawn along the west edge. "
                "Access lanes link each call house to the nearest clear street or canal. "
                "data.demo_event is still TODO_HUMAN."
            ),
            "projection": "fixed isometric 2:1. x east, y south toward the camera. z up.",
            "camera": {"look_at": [186, 214], "zoom_px_per_m": 5.6},
            "world": {"width_m": 540, "depth_m": 420},
            "contracts": "Household, Hazard, Resource, and Route enum from contracts v0.2. sim_status is a UI field.",
            "api": {
                "resources": "/resources",
                "fixture": "/fixtures/{id}",
                "triage": "/triage",
                "context": "/context",
                "map_flood": "/map/flood",
                "map_facilities": "/map/facilities",
            },
        },
        "hazards": hazards_from(flood),
        "resources": list(resources.values()),
        "graph": graph,
        "routes": routes,
        "response_routes": response_routes,
        "calls": calls,
        "buildings": buildings,
        "trees": trees,
    }
    write(DATA / "streets.json", {"note": town["meta"]["disclaimer"], "streets": streets})
    write(DATA / "flood.json", flood)
    write(DATA / "town.json", town)
    counts: dict[str, int] = {}
    for building in buildings:
        counts[building["sim_status"]] = counts.get(building["sim_status"], 0) + 1
    print(f"buildings {len(buildings)} trees {len(trees)} nodes {len(graph['nodes'])} edges {len(graph['edges'])}")
    print("status", counts)
    for route in routes:
        print(route["id"], route["length_m"], "m", len(route["node_ids"]), "nodes", route["mode"])
    missing = [route for route in response_routes if not route["legs"]]
    print(f"response routes {len(response_routes)} missing {len(missing)}")
    for route in response_routes:
        if route.get("note"):
            print(route["id"], route["note"])


if __name__ == "__main__":
    main()
