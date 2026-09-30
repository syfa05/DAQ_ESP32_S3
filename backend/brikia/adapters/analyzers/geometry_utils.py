"""Géométrie 2D pure (aucune dépendance) partagée par les analyseurs IFC, DXF et STEP.

Unité : millimètres, sauf mention contraire. Tout est déterministe.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass

Point = tuple[float, float]


def dist(a: Point, b: Point) -> float:
    return math.hypot(b[0] - a[0], b[1] - a[1])


def unit_vector(a: Point, b: Point) -> Point:
    d = dist(a, b)
    if d == 0:
        raise ValueError("Segment de longueur nulle")
    return ((b[0] - a[0]) / d, (b[1] - a[1]) / d)


def line_angle_deg(u: Point, v: Point) -> float:
    """Angle entre deux DROITES (orientation ignorée), dans [0, 90]."""
    c = abs(u[0] * v[0] + u[1] * v[1])
    return math.degrees(math.acos(min(1.0, c)))


def point_segment_distance(p: Point, a: Point, b: Point) -> tuple[float, float]:
    """(distance de p au segment [a, b], abscisse curviligne projetée bornée à [0, L])."""
    length = dist(a, b)
    if length == 0:
        return dist(p, a), 0.0
    ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
    s = (p[0] - a[0]) * ux + (p[1] - a[1]) * uy
    s = max(0.0, min(length, s))
    return dist(p, (a[0] + ux * s, a[1] + uy * s)), s


def convex_hull(points: Iterable[Point]) -> list[Point]:
    """Enveloppe convexe (chaîne monotone d'Andrew), sens antihoraire, sans doublon."""
    pts = sorted(set((round(x, 6), round(y, 6)) for x, y in points))
    if len(pts) <= 2:
        return pts

    def cross(o: Point, a: Point, b: Point) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    lower: list[Point] = []
    for p in pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0:
            lower.pop()
        lower.append(p)
    upper: list[Point] = []
    for p in reversed(pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0:
            upper.pop()
        upper.append(p)
    return lower[:-1] + upper[:-1]


@dataclass(frozen=True)
class OrientedRect:
    center: Point
    length: float       # grand côté
    width: float        # petit côté
    direction: Point    # vecteur unitaire du grand côté


def min_area_rect(points: Sequence[Point]) -> OrientedRect:
    """Rectangle orienté d'aire minimale (un côté est colinéaire à une arête de l'enveloppe)."""
    hull = convex_hull(points)
    if len(hull) < 2:
        raise ValueError("Pas assez de points")
    if len(hull) == 2:
        a, b = hull
        return OrientedRect(((a[0] + b[0]) / 2, (a[1] + b[1]) / 2), dist(a, b), 0.0, unit_vector(a, b))
    best: tuple[float, OrientedRect] | None = None
    for i in range(len(hull)):
        a, b = hull[i], hull[(i + 1) % len(hull)]
        if dist(a, b) == 0:
            continue
        ux, uy = unit_vector(a, b)
        vx, vy = -uy, ux
        us = [(p[0] - a[0]) * ux + (p[1] - a[1]) * uy for p in hull]
        vs = [(p[0] - a[0]) * vx + (p[1] - a[1]) * vy for p in hull]
        u0, u1, v0, v1 = min(us), max(us), min(vs), max(vs)
        area = (u1 - u0) * (v1 - v0)
        if best is None or area < best[0] - 1e-9:
            cu, cv = (u0 + u1) / 2, (v0 + v1) / 2
            center = (a[0] + ux * cu + vx * cv, a[1] + uy * cu + vy * cv)
            L, W = u1 - u0, v1 - v0
            direction = (ux, uy) if L >= W else (vx, vy)
            best = (area, OrientedRect(center, max(L, W), min(L, W), direction))
    assert best is not None
    return best[1]


# --------------------------------------------------------------------------- angles
@dataclass(frozen=True)
class CornerCandidate:
    """Segment d'axe d'un mur, pour la détection des jonctions en L."""

    key: int
    level: str
    a: Point
    b: Point
    thickness: float


def corner_keys(segments: Sequence[CornerCandidate], *, min_angle_deg: float = 60.0,
                slack_mm: float = 50.0) -> set[int]:
    """Clés des murs ayant au moins une extrémité en jonction « en L ».

    Jonction en L = deux segments du MÊME niveau, dont deux extrémités se
    rejoignent (à la tolérance près) et dont les directions font un angle
    d'au moins ``min_angle_deg`` (≈ perpendiculaires). Les jonctions en T
    (extrémité contre le milieu d'un autre mur) et les prolongements
    (segments alignés) ne sont pas des angles.

    La tolérance vaut la plus grande épaisseur des deux murs (leurs axes
    s'arrêtent souvent à la face du mur voisin) plus ``slack_mm``.

    Complexité quasi linéaire : les extrémités sont rangées dans une grille
    dont la maille vaut la tolérance maximale, et seules les mailles voisines
    sont comparées.
    """
    flagged: set[int] = set()
    by_level: dict[str, list[CornerCandidate]] = {}
    for s in segments:
        by_level.setdefault(s.level, []).append(s)
    for group in by_level.values():
        cell = max(s.thickness for s in group) + slack_mm
        dirs = [unit_vector(s.a, s.b) for s in group]
        grid: dict[tuple[int, int], list[tuple[int, Point]]] = {}
        for i, s in enumerate(group):
            for p in (s.a, s.b):
                grid.setdefault((math.floor(p[0] / cell), math.floor(p[1] / cell)), []).append((i, p))
        for i, s in enumerate(group):
            for p in (s.a, s.b):
                cx, cy = math.floor(p[0] / cell), math.floor(p[1] / cell)
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for j, q in grid.get((cx + dx, cy + dy), ()):
                            if j <= i or (s.key in flagged and group[j].key in flagged):
                                continue
                            if dist(p, q) > max(s.thickness, group[j].thickness) + slack_mm:
                                continue
                            if line_angle_deg(dirs[i], dirs[j]) >= min_angle_deg:
                                flagged.update((s.key, group[j].key))
    return flagged
