"""Group flood polygons into Overpass-sized clusters."""

from __future__ import annotations

from dataclasses import dataclass

from config.settings import load_yaml
from ingest.db import connect
from ingest.geo import bounds_of, centroid_latlon, loads

LIVE_WINDOWS = {"1d", "3d", "7d", "30d", "1", "3", "7", "30", "1-day", "3-day", "7-day", "30-day"}


@dataclass
class Area:
    label: str
    priority: int
    shapes: list


def select_areas() -> tuple[list[Area], list[str]]:
    """Pick up to max_overpass_clusters boxes, each at most max_bbox_degrees wide."""
    cfg = load_yaml("ingest.yaml")
    limit = int(cfg.get("max_overpass_clusters", 4))
    span = float(cfg.get("max_bbox_degrees", 4))
    groups: dict[tuple[int, str], list] = {}
    with connect() as conn:
        rows = conn.execute(
            "SELECT geometry, duration_window, source FROM flood_extent"
        ).fetchall()
    for row in rows:
        try:
            geom = loads(row["geometry"])
        except Exception:
            continue
        if geom.is_empty or geom.geom_type not in {"Polygon", "MultiPolygon"}:
            continue
        priority, label = _kind(row["source"], row["duration_window"])
        groups.setdefault((priority, label), []).append(geom)
    notes: list[str] = []
    areas: list[Area] = []
    for (priority, label), geoms in groups.items():
        for index, cluster in enumerate(_cluster(geoms), start=1):
            if not _fits(cluster, span):
                notes.append(f"skipped {label} cluster {index}: bbox wider than {span:g} degrees")
                continue
            areas.append(Area(label=f"{label}-{index}", priority=priority, shapes=cluster))
    areas.sort(key=lambda area: (area.priority, -len(area.shapes)))
    kept = areas[:limit]
    if len(areas) > limit:
        notes.append(
            f"kept {limit} of {len(areas)} clusters "
            "(risk layer, then EOS-RS, GDACS, UNOSAT, live extents)"
        )
    return kept, notes


def _kind(source: str | None, window: str | None) -> tuple[int, str]:
    text = (source or "").lower()
    duration = (window or "").lower()
    if duration == "flood_risk_layer":
        return 0, "risk-layer"
    if "eos-rs" in text:
        return 1, "eos-rs"
    if "gdacs" in text:
        return 2, "gdacs"
    if "unosat" in text:
        return 3, "unosat"
    if duration in LIVE_WINDOWS:
        return 4, "live-extent"
    return 5, "other"


def _cluster(geoms: list, radius: float = 1.5) -> list[list]:
    clusters: list[list] = []
    centers: list[tuple[float, float]] = []
    for geom in geoms:
        lat, lon = centroid_latlon(geom)
        placed = False
        for index, (clat, clon) in enumerate(centers):
            if max(abs(lat - clat), abs(lon - clon)) <= radius:
                clusters[index].append(geom)
                count = len(clusters[index])
                centers[index] = (
                    (clat * (count - 1) + lat) / count,
                    (clon * (count - 1) + lon) / count,
                )
                placed = True
                break
        if not placed:
            clusters.append([geom])
            centers.append((lat, lon))
    return clusters


def _fits(geoms: list, span: float) -> bool:
    min_lat, min_lon, max_lat, max_lon = bounds_of(geoms)
    return (max_lat - min_lat) <= span and (max_lon - min_lon) <= span
