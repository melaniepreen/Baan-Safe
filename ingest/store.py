"""Runtime reads of committed JSON/GeoJSON in data/processed.

Callers must not mutate the returned lists: they are cached and shared.
SQLite is only the build cache for `make ingest`; runtime code reads here.
"""

from __future__ import annotations

import json
from pathlib import Path

from shapely.geometry.base import BaseGeometry

from paths import ROOT

DATA_DIR = ROOT / "data" / "processed"

TABLES = (
    "districts",
    "admin_districts",
    "weather_observation",
    "disaster_report",
    "source_status",
)

_cache: dict[tuple[str, str], tuple[int, object]] = {}


def _cached(kind: str, path: Path, load):
    try:
        mtime = path.stat().st_mtime_ns
    except FileNotFoundError:
        _cache.pop((kind, str(path)), None)
        return []
    key = (kind, str(path))
    hit = _cache.get(key)
    if hit is not None and hit[0] == mtime:
        return hit[1]
    value = load(path)
    _cache[key] = (mtime, value)
    return value


def available() -> bool:
    return (DATA_DIR / "districts.json").exists()


def rows(table: str) -> list[dict]:
    if table not in TABLES:
        raise ValueError(f"unknown data table: {table}")
    return _cached(
        "table", DATA_DIR / f"{table}.json", lambda p: json.loads(p.read_text(encoding="utf-8"))
    )


def flood_shapes() -> list[tuple[dict, BaseGeometry]]:
    from ingest.geo import loads as _loads

    def load(path: Path):
        out = []
        for feature in json.loads(path.read_text(encoding="utf-8")).get("features") or []:
            try:
                out.append((feature.get("properties") or {}, _loads(json.dumps(feature["geometry"]))))
            except Exception:
                continue
        return out

    return _cached("flood", DATA_DIR / "flood.geojson", load)


def facilities() -> list[dict]:
    def load(path: Path):
        out = []
        for feature in json.loads(path.read_text(encoding="utf-8")).get("features") or []:
            props = dict(feature.get("properties") or {})
            coords = (feature.get("geometry") or {}).get("coordinates") or [None, None]
            props["lat"] = float(coords[1]) if coords[1] is not None else None
            props["lon"] = float(coords[0]) if coords[0] is not None else None
            out.append(props)
        return out

    return _cached("facilities", DATA_DIR / "facilities.geojson", load)


def write_rows(table: str, row_list: list[dict], data_dir: Path) -> None:
    if table not in TABLES:
        raise ValueError(f"unknown data table: {table}")
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / f"{table}.json"
    if not row_list:
        path.write_text("[]\n", encoding="utf-8")
        return
    path.write_text(
        "[\n" + ",\n".join(json.dumps(row, ensure_ascii=False) for row in row_list) + "\n]\n",
        encoding="utf-8",
    )


def write_features(path: Path, features: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '{"type": "FeatureCollection", "features": [\n'
        + ",\n".join(json.dumps(f, ensure_ascii=False) for f in features)
        + "\n]}\n",
        encoding="utf-8",
    )
