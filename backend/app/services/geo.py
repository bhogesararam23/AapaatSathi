"""Geospatial helpers.

The MVP deliberately avoids a PostGIS dependency so that it runs on plain
SQLite on a laptop and on managed Postgres in production without changing
code. Hill-district wards are small enough that spherical approximations are
accurwell within the precision the product needs (a ward is ~1-2 km across).
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

EARTH_RADIUS_KM = 6371.0088


Point = tuple[float, float]  # (lng, lat)


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in kilometres."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def bearing_deg(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Initial bearing from point 1 to point 2, degrees clockwise from north."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dlmb = math.radians(lng2 - lng1)
    y = math.sin(dlmb) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlmb)
    return (math.degrees(math.atan2(y, x)) + 360) % 360


def centroid(points: Sequence[Point]) -> Point:
    if not points:
        raise ValueError("centroid() needs at least one point")
    lng = sum(p[0] for p in points) / len(points)
    lat = sum(p[1] for p in points) / len(points)
    return (lng, lat)


def bbox(points: Sequence[Point]) -> tuple[float, float, float, float]:
    """(min_lng, min_lat, max_lng, max_lat)."""
    lngs = [p[0] for p in points]
    lats = [p[1] for p in points]
    return (min(lngs), min(lats), max(lngs), max(lats))


def pad_bbox(
    box: tuple[float, float, float, float], pad_km: float = 15.0
) -> tuple[float, float, float, float]:
    """Expand a bbox by a rough number of kilometres on each side."""
    min_lng, min_lat, max_lng, max_lat = box
    dlat = pad_km / 111.32
    mid_lat = (min_lat + max_lat) / 2
    dlng = pad_km / (111.32 * max(0.2, math.cos(math.radians(mid_lat))))
    return (min_lng - dlng, min_lat - dlat, max_lng + dlng, max_lat + dlat)


def polygon_area_km2(ring: Sequence[Point]) -> float:
    """Geodesic-ish planar area of a lng/lat ring using an equirectangular projection."""
    if len(ring) < 3:
        return 0.0
    mid_lat = sum(p[1] for p in ring) / len(ring)
    kx = 111.32 * math.cos(math.radians(mid_lat))  # km per degree lng
    ky = 110.574                                   # km per degree lat
    area = 0.0
    n = len(ring)
    for i in range(n):
        x1, y1 = ring[i][0] * kx, ring[i][1] * ky
        x2, y2 = ring[(i + 1) % n][0] * kx, ring[(i + 1) % n][1] * ky
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


def point_in_polygon(lat: float, lng: float, ring: Iterable[Point]) -> bool:
    """Ray-casting containment test (boundary treated as inside)."""
    poly = list(ring)
    if len(poly) < 3:
        return False
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > lat) != (yj > lat)) and (
            lng < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-12) + xi
        ):
            inside = not inside
        j = i
    return inside


def distance_to_polygon_km(lat: float, lng: float, ring: Sequence[Point]) -> float:
    """Minimum distance from a point to any edge of a polygon (km)."""
    if not ring:
        return float("inf")
    best = float("inf")
    n = len(ring)
    for i in range(n):
        a = ring[i]
        b = ring[(i + 1) % n]
        best = min(best, _distance_to_segment_km(lat, lng, a, b))
    return best


def _distance_to_segment_km(
    lat: float, lng: float, a: Point, b: Point
) -> float:
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    dx, dy = bx - ax, by - ay
    if dx == dy == 0:
        return haversine_km(lat, lng, ay, ax)
    t = ((lng - ax) * dx + (lat - ay) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    px, py = ax + t * dx, ay + t * dy
    return haversine_km(lat, lng, py, px)


def nearest_point_km(
    lat: float, lng: float, candidates: Sequence[tuple[float, float, float]]
) -> tuple[float, float] | None:
    """Return (distance_km, value) of the closest (lat, lng, value) candidate."""
    best: tuple[float, float] | None = None
    for clat, clng, value in candidates:
        d = haversine_km(lat, lng, clat, clng)
        if best is None or d < best[0]:
            best = (d, value)
    return best


def simplify_ring(ring: Sequence[Point], tolerance_deg: float = 0.002) -> list[Point]:
    """Cheap Douglas-Peucker so seeded ward outlines stay small in the payload."""
    if len(ring) < 4:
        return list(ring)
    keep = [ring[0]]
    for p in ring[1:-1]:
        if distance_to_segment_km_pt(p, keep[-1], tolerance_deg):
            keep.append(p)
    keep.append(ring[-1])
    return keep


def distance_to_segment_km_pt(pt: Point, anchor: Point, tol: float) -> bool:
    """Helper for simplify_ring: deviation above tolerance."""
    return abs(pt[0] - anchor[0]) > tol or abs(pt[1] - anchor[1]) > tol


def ring_to_geojson(ring: Sequence[Point]) -> dict:
    closed = list(ring)
    if closed and closed[0] != closed[-1]:
        closed.append(closed[0])
    return {"type": "Polygon", "coordinates": [closed]}


def feature_collection_to_geojson(features: Sequence[dict]) -> dict:
    return {"type": "FeatureCollection", "features": list(features)}
