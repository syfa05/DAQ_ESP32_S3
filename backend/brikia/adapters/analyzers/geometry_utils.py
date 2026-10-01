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


# --------------------------------------------------------------------------- extrémités
@dataclass(frozen=True)
class WallEnds:
    """Nature des deux extrémités d'un mur et jonctions en T sur son corps.

    Nature d'une extrémité :
    * ``angle``  : angle en L dont CE mur est propriétaire (il pose le bloc d'angle) ;
    * ``butee``  : angle en L dont l'autre mur est propriétaire (ce mur vient en butée) ;
    * ``te``     : l'extrémité s'appuie contre le corps d'un autre mur ;
    * ``suite``  : prolongement d'un mur aligné (segment d'un même mur polygonal) ;
    * ``libre``  : bout de mur libre.
    ``junctions`` : abscisses (mm depuis le début du mur) où un autre mur s'appuie sur celui-ci.
    """

    start: str = "libre"
    end: str = "libre"
    junctions: tuple[int, ...] = ()


class _BoxGrid:
    """Grille de boîtes englobantes : retrouve les segments proches d'un point sans test en O(n²)."""

    def __init__(self, cell: float) -> None:
        self.cell = cell
        self.cells: dict[tuple[int, int], list[int]] = {}

    def insert(self, idx: int, a: Point, b: Point, pad: float) -> None:
        c = self.cell
        x0, x1 = sorted((a[0], b[0]))
        y0, y1 = sorted((a[1], b[1]))
        for gx in range(math.floor((x0 - pad) / c), math.floor((x1 + pad) / c) + 1):
            for gy in range(math.floor((y0 - pad) / c), math.floor((y1 + pad) / c) + 1):
                self.cells.setdefault((gx, gy), []).append(idx)

    def near(self, p: Point) -> list[int]:
        return self.cells.get((math.floor(p[0] / self.cell), math.floor(p[1] / self.cell)), [])


def classify_ends(segments: Sequence[CornerCandidate], *, min_angle_deg: float = 60.0,
                  max_continuation_deg: float = 20.0, slack_mm: float = 50.0) -> dict[int, WallEnds]:
    """Classe les extrémités de chaque mur (même niveau uniquement) et repère les jonctions en T.

    * deux extrémités qui se rejoignent (tolérance = plus grande épaisseur + marge) : angle en L si les
      directions font ≥ ``min_angle_deg`` ; prolongement si elles sont presque alignées ;
    * une extrémité qui touche le CORPS d'un autre mur (pas ses bouts) : jonction en T ;
    * **un seul propriétaire par angle** : le mur d'indice le plus bas pose le bloc d'angle, les autres
      viennent en butée (un angle de 4 murs n'est donc jamais compté 4 fois).
    """
    result: dict[int, WallEnds] = {}
    by_level: dict[str, list[CornerCandidate]] = {}
    for s in segments:
        by_level.setdefault(s.level, []).append(s)
    for group in by_level.values():
        n = len(group)
        tol_max = max(s.thickness for s in group) + slack_mm
        dirs = [unit_vector(s.a, s.b) for s in group]
        lengths = [dist(s.a, s.b) for s in group]
        grid = _BoxGrid(max(tol_max, 1.0))
        for i, s in enumerate(group):
            grid.insert(i, s.a, s.b, tol_max)
        kinds: list[list[str]] = [["libre", "libre"] for _ in range(n)]
        junctions: list[list[int]] = [[] for _ in range(n)]
        for i, s in enumerate(group):
            for e, p in enumerate((s.a, s.b)):
                decided = None
                owner_below = False
                tee: tuple[int, float] | None = None
                for j in set(grid.near(p)):
                    if j == i:
                        continue
                    o = group[j]
                    tol = max(s.thickness, o.thickness) + slack_mm
                    angle = line_angle_deg(dirs[i], dirs[j])
                    ends = [q for q in (o.a, o.b) if dist(p, q) <= tol]
                    if ends:                                   # extrémité contre extrémité
                        if angle >= min_angle_deg:
                            decided = "corner"
                            owner_below = owner_below or j < i
                        elif angle <= max_continuation_deg and decided is None:
                            decided = "suite"
                    elif angle >= min_angle_deg:               # extrémité contre le corps de j ?
                        d, along = point_segment_distance(p, o.a, o.b)   # along : mm depuis o.a
                        if d <= o.thickness / 2 + slack_mm and o.thickness / 2 <= along <= lengths[j] - o.thickness / 2:
                            tee = (j, along)
                if decided == "corner":
                    kinds[i][e] = "butee" if owner_below else "angle"
                elif decided == "suite":
                    kinds[i][e] = "suite"
                elif tee is not None:
                    kinds[i][e] = "te"
                    junctions[tee[0]].append(int(round(tee[1])))
        for i, s in enumerate(group):
            js = tuple(sorted(set(junctions[i])))
            result[s.key] = WallEnds(kinds[i][0], kinds[i][1], js)
    return result
