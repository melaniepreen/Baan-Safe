"""Read a zipped shapefile and dissolve it into one geographic polygon."""

from __future__ import annotations

import io
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from shapely.geometry import mapping, shape
from shapely.ops import unary_union


def dissolved_polygon(blob: bytes, simplify_deg: float = 0.001) -> tuple[dict | None, int, str]:
    """Return (geojson geometry, source polygon count, note).

    The flood layer wins over an analysis frame. A dense single polygon
    beats a one-feature map frame.
    Projected coordinates (values outside longitude/latitude) are refused.
    """
    name, geoms = _busiest_layer(blob)
    if not geoms:
        return None, 0, "no polygon layer in the zip"
    geographic = []
    for geom in geoms:
        try:
            parsed = shape(geom)
        except Exception:
            continue
        if parsed.is_empty:
            continue
        minx, miny, maxx, maxy = parsed.bounds
        if max(abs(minx), abs(maxx)) > 180 or max(abs(miny), abs(maxy)) > 90:
            return None, len(geoms), f"{name} is not in longitude/latitude; not stored"
        geographic.append(parsed)
    if not geographic:
        return None, 0, "no usable polygons"
    merged = _union(geographic, simplify_deg)
    if merged is None or merged.is_empty:
        return None, len(geographic), "dissolve failed"
    text = mapping(merged)
    # A second pass if the dissolved ring is still huge.
    if len(str(text)) > 1_500_000:
        merged = _union(geographic, max(simplify_deg, 0.003))
        text = mapping(merged) if merged is not None else None
    if text is None:
        return None, len(geographic), "dissolve failed"
    return text, len(geographic), f"dissolved {len(geographic)} polygons from layer {name}"


def span_degrees(geometry: dict) -> float:
    geom = shape(geometry)
    minx, miny, maxx, maxy = geom.bounds
    return max(maxx - minx, maxy - miny)


def _busiest_layer(blob: bytes) -> tuple[str, list[dict]]:
    import shapefile

    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        _extract_shapefiles(blob, root, depth=0)
        layers: list[tuple[str, list[dict]]] = []
        for shp in root.rglob("*.shp"):
            # Pass the .shp path. Stripping the suffix first makes pyshp
            # treat ".9_shp" in names like "v0.9_shp" as the extension.
            reader = shapefile.Reader(str(shp))
            geoms = []
            for item in reader.iterShapes():
                geo = item.__geo_interface__
                if geo.get("type") in {"Polygon", "MultiPolygon"}:
                    geoms.append(geo)
            layers.append((shp.stem, geoms))
    if not layers:
        return "", []
    # Feature count is the wrong tie-break: UNOSAT often ships one dense
    # flood polygon beside a one-feature analysis frame.
    layers.sort(key=lambda pair: _layer_rank(pair[0], pair[1]), reverse=True)
    return layers[0]


def _layer_rank(name: str, geoms: list[dict]) -> int:
    text = name.lower()
    score = sum(_coord_count(geom) for geom in geoms)
    if "flood" in text or "water" in text:
        score += 1_000_000_000
    if "analysis" in text or "frame" in text:
        score -= 1_000_000_000
    return score


def _coord_count(geom: dict) -> int:
    count = 0
    coords = geom.get("coordinates") or []
    stack = [coords]
    while stack:
        item = stack.pop()
        if isinstance(item, (list, tuple)):
            if item and isinstance(item[0], (int, float)):
                count += 1
            else:
                stack.extend(item)
    return count


def _extract_shapefiles(blob: bytes, root: Path, depth: int) -> None:
    """Unpack shapefile parts, including one nested zip.

    GeoTIFF bundles such as the EOS-RS Hat Yai map keep the polygons in an
    inner zip and a large raster beside it. The raster is not extracted.
    """
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            name = info.filename
            if name.startswith("/") or ".." in Path(name).parts:
                continue
            lower = name.lower()
            if lower.endswith(".zip") and depth < 1 and info.file_size <= 40_000_000:
                dest = root / f"nested-{Path(name).stem}"
                dest.mkdir(parents=True, exist_ok=True)
                _extract_shapefiles(archive.read(info), dest, depth + 1)
                continue
            if not lower.endswith((".shp", ".dbf", ".shx", ".prj", ".cpg")):
                continue
            target = (root / name).resolve()
            if not str(target).startswith(str(root.resolve())):
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(archive.read(info))


def _union(geoms: list, simplify_deg: float):
    acc = None
    batch: list = []
    for geom in geoms:
        simple = geom.simplify(simplify_deg, preserve_topology=True)
        if simple.is_empty:
            continue
        batch.append(simple)
        if len(batch) >= 200:
            acc = _merge(acc, batch)
            batch = []
    if batch:
        acc = _merge(acc, batch)
    if acc is None:
        return None
    if not acc.is_valid:
        acc = acc.buffer(0)
    return acc


def _merge(acc, batch: list):
    pieces = batch if acc is None else [acc, *batch]
    return unary_union(pieces)
