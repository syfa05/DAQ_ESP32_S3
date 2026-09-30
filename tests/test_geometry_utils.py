import math

import pytest

from brikia.adapters.analyzers.geometry_utils import (
    CornerCandidate, convex_hull, corner_keys, dist, line_angle_deg, min_area_rect,
    point_segment_distance, unit_vector,
)


def test_basic_vectors_and_angles():
    assert dist((0, 0), (3, 4)) == 5
    assert unit_vector((0, 0), (0, 10)) == (0.0, 1.0)
    with pytest.raises(ValueError):
        unit_vector((1, 1), (1, 1))
    assert line_angle_deg((1, 0), (0, 1)) == pytest.approx(90)
    assert line_angle_deg((1, 0), (-1, 0)) == pytest.approx(0)  # orientation ignorée
    assert line_angle_deg((1, 0), (math.sqrt(.5), math.sqrt(.5))) == pytest.approx(45)


def test_point_segment_distance_clamps_to_ends():
    assert point_segment_distance((5, 3), (0, 0), (10, 0)) == (3.0, 5.0)
    d, s = point_segment_distance((-4, 3), (0, 0), (10, 0))
    assert d == 5.0 and s == 0.0
    d, s = point_segment_distance((14, 3), (0, 0), (10, 0))
    assert d == 5.0 and s == 10.0
    assert point_segment_distance((3, 4), (0, 0), (0, 0)) == (5.0, 0.0)


def test_convex_hull_drops_interior_and_collinear_points():
    sq = [(0, 0), (4, 0), (4, 4), (0, 4), (2, 2), (2, 0), (0, 2)]
    assert sorted(convex_hull(sq)) == [(0, 0), (0, 4), (4, 0), (4, 4)]
    assert convex_hull([(1, 1)]) == [(1, 1)]


def test_min_area_rect_axis_aligned_and_rotated():
    r = min_area_rect([(0, 0), (5000, 0), (5000, 200), (0, 200)])
    assert (round(r.length), round(r.width)) == (5000, 200) and r.direction == pytest.approx((1, 0))
    a = math.radians(30)
    pts = [(x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a))
           for x, y in [(0, 0), (4000, 0), (4000, 300), (0, 300)]]
    r = min_area_rect(pts)
    assert r.length == pytest.approx(4000, abs=1e-3) and r.width == pytest.approx(300, abs=1e-3)
    assert abs(r.direction[0]) == pytest.approx(math.cos(a), abs=1e-6)
    with pytest.raises(ValueError):
        min_area_rect([(1, 1)])


def C(key, a, b, t=200, level="RDC"):
    return CornerCandidate(key, level, a, b, t)


def test_l_junction_flags_both_walls():
    flagged = corner_keys([C(1, (0, 0), (5000, 0)), C(2, (5000, 0), (5000, 4000))])
    assert flagged == {1, 2}


def test_axes_stopping_at_the_face_of_the_neighbour_still_form_a_corner():
    # 150 mm d'écart <= épaisseur 200 + marge
    assert corner_keys([C(1, (0, 0), (4900, 0)), C(2, (5000, 100), (5000, 4000))]) == {1, 2}


def test_t_junction_collinear_and_far_segments_are_not_corners():
    # T : l'extrémité du 2e mur touche le MILIEU du 1er
    assert corner_keys([C(1, (0, 0), (10000, 0)), C(2, (5000, 0), (5000, 4000))]) == set()
    # alignés (prolongement) : pas d'angle
    assert corner_keys([C(1, (0, 0), (5000, 0)), C(2, (5000, 0), (9000, 0))]) == set()
    # perpendiculaires mais éloignés
    assert corner_keys([C(1, (0, 0), (5000, 0)), C(2, (6000, 0), (6000, 4000))]) == set()


def test_corners_do_not_cross_levels_and_obtuse_bends_are_ignored():
    assert corner_keys([C(1, (0, 0), (5000, 0), level="RDC"), C(2, (5000, 0), (5000, 4000), level="R+1")]) == set()
    a = math.radians(45)
    assert corner_keys([C(1, (0, 0), (5000, 0)), C(2, (5000, 0), (5000 + 4000 * math.cos(a), 4000 * math.sin(a)))]) == set()


def test_rectangle_of_four_walls_has_four_corner_walls():
    sq = [C(1, (0, 0), (8000, 0)), C(2, (8000, 0), (8000, 6000)),
          C(3, (8000, 6000), (0, 6000)), C(4, (0, 6000), (0, 0))]
    assert corner_keys(sq) == {1, 2, 3, 4}
