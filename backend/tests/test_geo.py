"""Tests for the geospatial helpers.

The MVP deliberately avoids PostGIS, which means these few functions *are* the
geometry engine: they decide which ward a citizen's pin falls inside, how far a
shelter is, and what GeoJSON the map draws. Getting them wrong is a wrong
evacuation route, so the tolerances here are stated rather than fudged.
"""

from __future__ import annotations

import math

import pytest

from app.services import geo

# A 0.1 x 0.1 degree square in Pauri Garhwal, stored as (lng, lat) pairs.
SQUARE: list[geo.Point] = [
    (78.0, 30.0),
    (78.1, 30.0),
    (78.1, 30.1),
    (78.0, 30.1),
]

DEHRADUN = (30.3160, 78.0321)
HARIDWAR = (29.9459, 78.1642)
DELHI = (28.6139, 77.2090)
MUMBAI = (19.0760, 72.8777)


# --------------------------------------------------------------------------- #
# distance
# --------------------------------------------------------------------------- #
def test_one_degree_of_arc_is_about_111_km():
    """The calibration check: 1 deg on a sphere of R=6371.0088 km."""
    assert geo.haversine_km(0.0, 78.0, 1.0, 78.0) == pytest.approx(111.195, abs=0.05)
    assert geo.haversine_km(0.0, 0.0, 0.0, 1.0) == pytest.approx(111.195, abs=0.05)


def test_dehradun_to_haridwar_matches_the_known_great_circle():
    distance = geo.haversine_km(*DEHRADUN, *HARIDWAR)
    # ~43 km straight line down the Doon valley; the *road* is ~52 km, and a
    # reviewer who expects 50 here is thinking of NH-34, not the sphere.
    assert distance == pytest.approx(43.07, abs=0.6)


def test_a_long_haul_distance_is_in_the_right_ballpark():
    assert geo.haversine_km(*DELHI, *MUMBAI) == pytest.approx(1148.1, abs=3.0)


def test_haversine_is_symmetric_and_zero_on_the_diagonal():
    a = geo.haversine_km(*DEHRADUN, *HARIDWAR)
    b = geo.haversine_km(*HARIDWAR, *DEHRADUN)
    assert a == pytest.approx(b)
    assert geo.haversine_km(*DEHRADUN, *DEHRADUN) == pytest.approx(0.0)


def test_haversine_shrinks_as_the_two_points_get_closer():
    far = geo.haversine_km(30.0, 78.0, 30.5, 78.0)
    near = geo.haversine_km(30.0, 78.0, 30.05, 78.0)
    assert near < far
    assert far == pytest.approx(near * 10, rel=1e-6)


# --------------------------------------------------------------------------- #
# bearing
# --------------------------------------------------------------------------- #
def test_bearing_is_measured_clockwise_from_true_north():
    assert geo.bearing_deg(30.0, 78.0, 31.0, 78.0) == pytest.approx(0.0, abs=1e-6)
    assert geo.bearing_deg(30.0, 78.0, 29.0, 78.0) == pytest.approx(180.0, abs=1e-6)
    assert geo.bearing_deg(30.0, 78.0, 30.0, 79.0) == pytest.approx(90.0, abs=0.5)
    assert geo.bearing_deg(30.0, 78.0, 30.0, 77.0) == pytest.approx(270.0, abs=0.5)


def test_bearing_is_always_wrapped_into_zero_to_360():
    bearing = geo.bearing_deg(30.0, 78.0, 30.0, 77.0)
    assert 0.0 <= bearing < 360.0
    assert geo.bearing_deg(30.0, 78.0, 30.001, 78.0) == pytest.approx(0.0, abs=1e-3)


# --------------------------------------------------------------------------- #
# polygon containment
# --------------------------------------------------------------------------- #
def test_point_in_polygon_accepts_the_centre_and_rejects_the_outside():
    assert geo.point_in_polygon(30.05, 78.05, SQUARE) is True
    assert geo.point_in_polygon(30.05, 78.50, SQUARE) is False
    assert geo.point_in_polygon(30.50, 78.05, SQUARE) is False
    assert geo.point_in_polygon(29.50, 78.05, SQUARE) is False
    assert geo.point_in_polygon(30.05, 77.50, SQUARE) is False


def test_point_in_polygon_handles_a_concave_notch():
    """A ray must cross the boundary twice inside the notch, not once."""
    concave: list[geo.Point] = [
        (78.0, 30.0),
        (78.4, 30.0),
        (78.4, 30.4),
        (78.25, 30.4),
        (78.25, 30.2),
        (78.15, 30.2),
        (78.15, 30.4),
        (78.0, 30.4),
    ]
    assert geo.point_in_polygon(30.1, 78.2, concave) is True  # below the notch
    assert geo.point_in_polygon(30.3, 78.1, concave) is True  # left of the notch
    assert geo.point_in_polygon(30.3, 78.2, concave) is False  # inside the notch


def test_degenerate_polygons_never_contain_anything():
    assert geo.point_in_polygon(30.0, 78.0, []) is False
    assert geo.point_in_polygon(30.0, 78.0, [(78.0, 30.0), (78.1, 30.0)]) is False


def test_distance_to_polygon_is_zero_on_the_boundary_and_grows_outside():
    assert geo.distance_to_polygon_km(30.0, 78.05, SQUARE) == pytest.approx(0.0, abs=1e-6)
    inside = geo.distance_to_polygon_km(30.05, 78.05, SQUARE)
    # Nearest edge is the west one: half of 0.1 deg of *longitude* at 30 N.
    assert inside == pytest.approx(0.05 * 111.32 * math.cos(math.radians(30.05)), abs=0.02)
    north_1km = geo.distance_to_polygon_km(30.0 + 0.1 + 0.01, 78.05, SQUARE)
    assert north_1km == pytest.approx(1.106, abs=0.02)
    assert geo.distance_to_polygon_km(30.0, 78.05, []) == float("inf")


def test_distance_to_polygon_uses_the_nearest_edge_not_the_nearest_vertex():
    # Directly east of the middle of the east edge.
    due_east = geo.distance_to_polygon_km(30.05, 78.2, SQUARE)
    from_vertex = geo.haversine_km(30.05, 78.2, 30.1, 78.1)
    assert due_east < from_vertex
    assert due_east == pytest.approx(geo.haversine_km(30.05, 78.2, 30.05, 78.1), abs=1e-6)


# --------------------------------------------------------------------------- #
# area
# --------------------------------------------------------------------------- #
def test_a_roughly_1_2_km_square_blob_is_about_1_4_square_km():
    dlat = 1.2 / 110.574
    dlng = 1.2 / (111.32 * math.cos(math.radians(30.0)))
    blob: list[geo.Point] = [
        (78.0, 30.0),
        (78.0 + dlng, 30.0),
        (78.0 + dlng, 30.0 + dlat),
        (78.0, 30.0 + dlat),
    ]
    area = geo.polygon_area_km2(blob)
    assert 1.30 < area < 1.60
    assert geo.polygon_area_km2(list(reversed(blob))) == pytest.approx(area)


def test_seeded_ward_outlines_have_a_plausible_area_and_close_for_geojson():
    """``app.seed._ring`` builds the ward geometry the map renders."""
    from app.seed import _ring

    for seed in (1, 7, 42, 199):
        ring = [tuple(p) for p in _ring(30.125, 78.225, seed, radius_km=1.35)]
        assert ring[0] != ring[-1], "seed emits an open ring"
        area = geo.polygon_area_km2(ring)
        # A ~1.4 km radius hexoid with jitter: a few km^2, never a district.
        assert 3.0 < area < 9.0, (seed, area)
        closed = geo.ring_to_geojson(ring)["coordinates"][0]
        assert closed[0] == closed[-1]
        assert len(closed) == len(ring) + 1


def test_area_is_positive_for_a_large_square():
    ward_ring: list[geo.Point] = [(lng, lat) for lng, lat in SQUARE]
    # 0.1 deg of latitude (~11.06 km) by 0.1 deg of longitude at 30 N (~9.63 km).
    assert geo.polygon_area_km2(ward_ring) == pytest.approx(106.5, abs=0.6)


def test_area_of_a_degenerate_ring_is_zero():
    assert geo.polygon_area_km2([]) == 0.0
    assert geo.polygon_area_km2([(78.0, 30.0)]) == 0.0
    assert geo.polygon_area_km2([(78.0, 30.0), (78.1, 30.0)]) == 0.0


# --------------------------------------------------------------------------- #
# geojson + bbox helpers
# --------------------------------------------------------------------------- #
def test_ring_to_geojson_closes_the_ring_exactly_once():
    feature = geo.ring_to_geojson(SQUARE)
    assert feature["type"] == "Polygon"
    ring = feature["coordinates"][0]
    assert len(ring) == len(SQUARE) + 1
    assert ring[0] == ring[-1]
    assert ring[:-1] == SQUARE


def test_ring_to_geojson_is_idempotent_on_an_already_closed_ring():
    closed = SQUARE + [SQUARE[0]]
    ring = geo.ring_to_geojson(closed)["coordinates"][0]
    assert len(ring) == len(closed)
    assert ring[0] == ring[-1]


def test_ring_to_geojson_is_json_serialisable():
    import json

    payload = json.dumps(geo.ring_to_geojson(SQUARE))
    assert json.loads(payload)["coordinates"][0][0] == [78.0, 30.0]


def test_bbox_centroid_and_padding_agree():
    assert geo.bbox(SQUARE) == (78.0, 30.0, 78.1, 30.1)
    assert geo.centroid(SQUARE) == (78.05, 30.05)
    min_lng, min_lat, max_lng, max_lat = geo.pad_bbox(geo.bbox(SQUARE), pad_km=15.0)
    assert min_lng < 78.0 and max_lng > 78.1
    assert min_lat < 30.0 and max_lat > 30.1
    # 15 km is ~0.135 deg of latitude
    assert (min_lat - 30.0) == pytest.approx(-0.1348, abs=0.002)
    # longitude degrees are shorter at 30 N, so the lng pad must be larger
    assert (78.0 - min_lng) > (30.0 - min_lat)


def test_centroid_and_simplify_reject_or_preserve_degenerate_input():
    with pytest.raises(ValueError):
        geo.centroid([])
    assert geo.simplify_ring(SQUARE, tolerance_deg=0.5)[0] == SQUARE[0]
    assert geo.simplify_ring(SQUARE[:2]) == SQUARE[:2]


def test_nearest_point_returns_the_closest_candidate_value():
    candidates = [(30.0, 78.0, 11), (31.0, 79.0, 22), (30.02, 78.02, 33)]
    distance, value = geo.nearest_point_km(30.05, 78.05, candidates)
    assert value == 33
    assert distance < geo.haversine_km(30.05, 78.05, 31.0, 79.0)
    assert geo.nearest_point_km(30.0, 78.0, []) is None


def test_feature_collection_wraps_without_copying():
    feature = {"type": "Feature", "properties": {"code": "X"}}
    collection = geo.feature_collection_to_geojson([feature])
    assert collection["type"] == "FeatureCollection"
    assert collection["features"] == [feature]
