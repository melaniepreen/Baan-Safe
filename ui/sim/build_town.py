"""Generate the synthetic town the simulation renders.

The renderer does not invent layout. It reads the JSON this script writes:

- ui/sim/data/streets.json  placeholder names and centerlines (swap names here)
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
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(__file__).resolve().parent / "data"
FIXTURES = ROOT / "fixtures" / "scenarios"
MOCKS = ROOT / "mocks" / "resources.json"

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
    }


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
                    "name": row["name"],
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
) -> dict:
    if axis == "h":
        points = [[start, fixed], [end, fixed]]
    else:
        points = [[fixed, start], [fixed, end]]
    return {
        "id": street_id,
        "name_th": name_th,
        "name_en": f"PLACEHOLDER · {name_en}",
        "kind": kind,
        "placeholder": True,
        "axis": axis,
        "fixed": fixed,
        "start": start,
        "end": end,
        "width_m": width_m,
        "points": points,
        "poles": kind == "main",
    }


def build_streets() -> list[dict]:
    return [
        street(
            "thanon-chamlong-nam-thuam",
            "ถนนจำลองน้ำท่วม",
            "Thanon Chamlong Nam Thuam",
            "main",
            "h",
            H_MAIN,
            16,
            524,
            16,
        ),
        street("soi-chamlong-bon", "ซอยจำลองบน", "Soi Chamlong Bon", "soi", "h", H_BON, 56, 470, 6.5),
        street(
            "soi-chamlong-lang",
            "ซอยจำลองล่าง",
            "Soi Chamlong Lang",
            "soi",
            "h",
            H_LANG,
            56,
            490,
            7,
        ),
        street(
            "soi-chamlong-khlong",
            "ซอยจำลองคลอง",
            "Soi Chamlong Khlong",
            "soi",
            "v",
            V_KHLONG,
            24,
            400,
            5.5,
        ),
        street(
            "soi-chamlong-wat-fa",
            "ซอยจำลองวัดฟ้า",
            "Soi Chamlong Wat Fa",
            "soi",
            "v",
            V_WAT,
            24,
            400,
            7,
        ),
        street(
            "soi-chamlong-talat",
            "ซอยจำลองตลาด",
            "Soi Chamlong Talat",
            "soi",
            "v",
            V_TALAT,
            32,
            396,
            7,
        ),
        street(
            "soi-chamlong-ho-nuea",
            "ซอยจำลองหอเหนือ",
            "Soi Chamlong Ho Nuea",
            "soi",
            "v",
            V_HO,
            H_MAIN,
            404,
            7.5,
        ),
        street(
            "soi-chamlong-fai",
            "ซอยจำลองสายไฟ",
            "Soi Chamlong Sai Fai",
            "soi",
            "v",
            V_FAI,
            40,
            380,
            6.5,
        ),
        street("khlong-chamlong", "คลองจำลอง", "Khlong Chamlong", "canal", "v", 22, 30, 400, 14),
    ]


def build_flood() -> dict:
    temple_hole = [[142, 326], [220, 326], [220, 392], [142, 392]]
    features = [
        poly(
            "haz-flood-canal",
            1.6,
            "Placeholder canal water along the west edge of the synthetic block.",
            [[[0, 8], [34, 8], [34, 412], [0, 412]]],
        ),
        poly(
            "haz-flood-south-deep",
            0.9,
            "Deeper standing water in the southern lanes. The temple compound is the hole in this polygon.",
            [[[30, 328], [530, 328], [530, 412], [30, 412]], temple_hole],
        ),
        poly(
            "haz-flood-streets",
            0.45,
            "Shallow floodwater on the main road and the lanes south of it.",
            [[[30, 180], [530, 180], [530, 328], [30, 328]]],
        ),
        poly(
            "haz-flood-soi-khlong",
            0.35,
            "Water sitting in the northern section of Soi Chamlong Khlong.",
            [[[V_KHLONG - 4, 40], [V_KHLONG + 4, 40], [V_KHLONG + 4, 180], [V_KHLONG - 4, 180]]],
        ),
        poly(
            "haz-flood-soi-wat-fa",
            0.35,
            "Water sitting in the northern section of Soi Chamlong Wat Fa.",
            [[[V_WAT - 4.2, 36], [V_WAT + 4.2, 36], [V_WAT + 4.2, 180], [V_WAT - 4.2, 180]]],
        ),
        poly(
            "haz-flood-soi-talat",
            0.35,
            "Water sitting in the northern section of Soi Chamlong Talat.",
            [[[V_TALAT - 4.2, 40], [V_TALAT + 4.2, 40], [V_TALAT + 4.2, 180], [V_TALAT - 4.2, 180]]],
        ),
        poly(
            "haz-flood-soi-fai",
            0.35,
            "Water sitting in the northern section of Soi Chamlong Sai Fai.",
            [[[V_FAI - 4, 48], [V_FAI + 4, 48], [V_FAI + 4, 180], [V_FAI - 4, 180]]],
        ),
        poly(
            "haz-flood-soi-bon",
            0.3,
            "Shallow water on Soi Chamlong Bon.",
            [[[56, H_BON - 3.6], [470, H_BON - 3.6], [470, H_BON + 3.6], [56, H_BON + 3.6]]],
        ),
    ]
    return {
        "type": "FeatureCollection",
        "properties": {
            "crs_note": "Local metres. x east, y south toward the fixed camera. Not WGS84. Not a household address.",
            "placeholder": True,
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
            "location_label": "synthetic operator block",
            "depth_m": depth_m,
            "placeholder": True,
        },
        "geometry": {"type": "Polygon", "coordinates": rings},
    }


def hazards_from(flood: dict) -> list[dict]:
    return [
        {
            "hazard_id": feature["properties"]["hazard_id"],
            "kind": "flood",
            "summary": feature["properties"]["summary"],
            "location_label": "synthetic operator block",
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


def landmarks(resources: dict[str, dict], summaries: dict[str, dict]) -> list[dict]:
    def res(resource_id: str) -> str:
        if resource_id not in resources:
            raise SystemExit(f"missing mock resource {resource_id}")
        return resource_id

    return [
        base_building(
            id="bldg-school",
            kind="school",
            name_th="อาคารเรียนจำลอง",
            name_en="PLACEHOLDER long school block",
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
            name_th="อาคารขาวจำลอง",
            name_en="PLACEHOLDER white block",
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
            name_th="อาคารชมพูจำลอง",
            name_en="PLACEHOLDER pink block",
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
            name_th="หอเหนือจำลอง",
            name_en="Fictional North Canal hall",
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
            name_th="คลินิกจำลอง",
            name_en="Fictional clinic",
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
            name_th="จุดน้ำจำลอง",
            name_en="Fictional market-day water desk",
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
            name_th="ท่าเรือจำลอง",
            name_en="Fictional river boat A",
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
            name_th="วัดฟ้าจำลอง",
            name_en="PLACEHOLDER blue temple",
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
            name_th="ศาลาจำลอง",
            name_en="PLACEHOLDER sala",
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
            name_th="เจดีย์จำลอง",
            name_en="PLACEHOLDER stupa",
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
        fixture=summary,
        sim_status=status,
        water_m=water_m,
        landmark=True,
    )


def fill_houses(rng: random.Random, reserved: list[dict], flood: dict, trees: list[dict]) -> list[dict]:
    """Pack ordinary lots into the blocks between placeholder roads."""
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


def build_routes(graph: dict, buildings: dict[str, dict]) -> list[dict]:
    specs = [
        {
            "id": "route-f06-evac",
            "label": "F06 walk to the fictional north hall",
            "fixture_id": "F06",
            "contract_route": "shelter_placement",
            "needs": ["evacuation"],
            "mode": "foot",
            "from_building": "bldg-f06",
            "to_building": "bldg-shelter",
        },
        {
            "id": "route-f10-rescue",
            "label": "F10 boat from the fictional jetty",
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
                    "This path is the shortest allowed walk on the synthetic graph."
                ),
            }
        )
    return routes


def main() -> None:
    rng = random.Random(1370)
    summaries = {fixture_id: fixture_summary(fixture_id) for fixture_id in ("F01", "F04", "F06", "F08", "F10", "F12")}
    resources = {row["resource_id"]: row for row in load_resources()}
    streets = build_streets()
    flood = build_flood()
    special = landmarks(resources, summaries)
    for building in special:
        if building["id"] == "bldg-f08":
            building["also_fixture_ids"] = ["F09"]
    reserved = [dict(row) for row in special]
    reserved.append({"id": "temple-grounds", "x": 144, "y": 324, "w": 78, "d": 70})
    trees = hand_trees()
    houses = fill_houses(rng, reserved, flood, trees)
    buildings = houses + special
    gap_trees(rng, buildings, trees)
    graph = graph_from_streets(streets, flood)
    by_building = {row["id"]: row for row in buildings}
    routes = build_routes(graph, by_building)
    town = {
        "meta": {
            "id": "synthetic-operator-block",
            "title": "Synthetic operator block",
            "district_anchor": "Northern fixture districts (Lampang, Phrae, Nan, Phayao). data.demo_event is still TODO_HUMAN.",
            "disclaimer": (
                "Not a cadastral map and not one real town. Street names are placeholders in streets.json. "
                "Household location_label stays the fixture district. Plots are local metres, not home addresses. "
                "F12's blue temple and F06's north hall are the invented landmarks from the fixtures."
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


if __name__ == "__main__":
    main()
