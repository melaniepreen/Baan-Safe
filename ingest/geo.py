"""Small geometry helpers. Distances are approximate and fine for district matching."""

from __future__ import annotations

import json
import math
from typing import Iterable

from shapely.geometry import shape
from shapely.geometry.base import BaseGeometry


def loads(geojson_text: str) -> BaseGeometry:
    return shape(json.loads(geojson_text))


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def centroid_latlon(geom: BaseGeometry) -> tuple[float, float]:
    point = geom.centroid
    return float(point.y), float(point.x)


def bounds_of(geoms: Iterable[BaseGeometry]) -> tuple[float, float, float, float]:
    min_lat, min_lon = 90.0, 180.0
    max_lat, max_lon = -90.0, -180.0
    any_geom = False
    for geom in geoms:
        minx, miny, maxx, maxy = geom.bounds
        min_lon = min(min_lon, minx)
        min_lat = min(min_lat, miny)
        max_lon = max(max_lon, maxx)
        max_lat = max(max_lat, maxy)
        any_geom = True
    if not any_geom:
        raise ValueError("no geometries")
    return min_lat, min_lon, max_lat, max_lon
