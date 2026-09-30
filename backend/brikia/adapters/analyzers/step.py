"""Analyse d'un plan STEP (ISO 10303, solides 3D) avec Open CASCADE (paquet pip « cadquery-ocp »).

Un STEP de CAO ne dit pas ce qu'est un mur : BrikIA le déduit de la FORME. C'est donc
une heuristique, toujours signalée comme telle dans l'analyse.

Un solide est un mur si :
- son axe vertical (celui de la boîte orientée le plus proche de l'axe Z) est sa plus grande
  dimension utile : hauteur >= 800 mm ;
- son épaisseur (plus petite dimension horizontale) est comprise entre 40 et 600 mm ;
- sa longueur (plus grande dimension horizontale) vaut au moins 3 épaisseurs et 500 mm.

Les poteaux (trop courts), dalles (trop basses) et volumes massifs sont ignorés. Un mur en L
ou un contour fermé modélisé en UN seul solide est « trop épais » et n'est pas reconnu :
les murs doivent être des solides distincts.

Ouvertures : lues sur la plus grande face latérale du mur : trous internes (fenêtres) et
encoches ouvertes en pied (portes). Niveaux : altitude du pied du mur (regroupée à 100 mm).
Unités : converties en mm à la lecture (l'en-tête du fichier est respecté). Axe vertical : Z par
défaut. Certaines CAO exportent en Y vertical : en mode « auto », Y n'est retenu que si l'évidence
est forte (au moins 3 murs, et au moins 2 fois plus de murs qu'en Z) ; sinon l'axe se fixe
explicitement (``BRIKIA_STEP_UP_AXIS``). Une dalle vue de chant ressemble à un grand mur : sans
cette prudence, une dalle serait prise pour un mur.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from dataclasses import dataclass

from ...domain.errors import AnalysisFailed
from ...domain.geometry import OpeningGeometry, ProjectGeometry, WallGeometry
from ._native import silence_native_stdout
from .base import AnalyzerUnavailable, PlanFile
from .geometry_utils import CornerCandidate, Point, corner_keys, dist

log = logging.getLogger("brikia.analyzers.step")


@dataclass(frozen=True)
class StepOptions:
    min_height_mm: float = 800.0
    min_thickness_mm: float = 40.0
    max_thickness_mm: float = 600.0
    min_length_mm: float = 500.0
    min_aspect: float = 3.0               # longueur / épaisseur
    level_tolerance_mm: float = 100.0
    min_notch_mm: float = 300.0           # largeur minimale d'une encoche de porte
    door_height_mm: float = 2100.0        # hauteur de repli d'une encoche
    max_solids: int = 20000
    up_axis: str = "auto"                 # auto | z | y
    y_min_walls: int = 3                  # évidence exigée pour préférer Y à Z en mode auto
    y_min_ratio: float = 2.0

    @classmethod
    def from_settings(cls, s) -> StepOptions:  # noqa: ANN001
        return cls(up_axis=s.step_up_axis)


@dataclass
class _Wall:
    a: Point
    b: Point
    thickness: float
    height: float
    z_bottom: float
    openings: list[OpeningGeometry]
    solid: object = None
    thickness_axis: tuple = (0.0, 0.0, 0.0)

    @property
    def length(self) -> float:
        return dist(self.a, self.b)


_UP = {"z": (0.0, 0.0, 1.0), "y": (0.0, 1.0, 0.0)}


class StepPlanAnalyzer:
    name = "step"

    def __init__(self, options: StepOptions | None = None) -> None:
        try:
            import OCP  # noqa: F401
        except ImportError as exc:
            raise AnalyzerUnavailable("STEP", "cadquery-ocp") from exc
        self.options = options or StepOptions()

    # ------------------------------------------------------------------ lecture
    def analyse(self, file: PlanFile) -> ProjectGeometry:
        with silence_native_stdout():   # Open CASCADE écrit ses statistiques sur la sortie standard
            solids = self._read_solids(file)
            mode = self.options.up_axis.lower()
            by_up = {}
            for name in (("z", "y") if mode == "auto" else (mode,)):
                by_up[name] = self._classify(solids, _UP[name])
            chosen = "z"
            if mode == "y":
                chosen = "y"
            elif mode == "auto":
                n_z, n_y = len(by_up["z"][0]), len(by_up["y"][0])
                if n_y >= self.options.y_min_walls and n_y >= self.options.y_min_ratio * n_z:
                    chosen = "y"
            walls, rejected = by_up[chosen]
            if walls:
                self._attach_openings(walls, _UP[chosen])
        if not walls:
            raise AnalysisFailed(
                f"Aucun mur reconnu parmi les {len(solids)} solide(s) de ce fichier STEP. "
                "BrikIA reconnaît un mur à sa forme : un solide vertical de 800 mm de haut au moins, épais de "
                "40 à 600 mm et au moins 3 fois plus long qu'épais, distinct des autres murs "
                f"({_describe(rejected)}). Exportez les murs comme des solides séparés, axe Z vers le haut "
                "(sinon réglez BRIKIA_STEP_UP_AXIS)."
            )
        return self._assemble(walls, len(solids), rejected, chosen.upper(), automatic=mode == "auto")

    def _read_solids(self, file: PlanFile) -> list:
        from OCP.IFSelect import IFSelect_RetDone
        from OCP.Interface import Interface_Static
        from OCP.STEPControl import STEPControl_Reader
        from OCP.TopAbs import TopAbs_SOLID
        from OCP.TopExp import TopExp_Explorer

        try:
            Interface_Static.SetCVal_s("xstep.cascade.unit", "MM")   # tout en millimètres
            reader = STEPControl_Reader()
            if reader.ReadFile(str(file.path)) != IFSelect_RetDone:
                raise ValueError("lecture refusée")
            reader.TransferRoots()
            shape = reader.OneShape()
            if shape.IsNull():
                raise ValueError("aucune forme")
            solids = []
            explorer = TopExp_Explorer(shape, TopAbs_SOLID)
            while explorer.More():
                solids.append(_cast("Solid", explorer.Current()))
                if len(solids) > self.options.max_solids:
                    raise AnalysisFailed(
                        f"Ce fichier STEP contient plus de {self.options.max_solids} solides : "
                        "trop volumineux pour une analyse automatique. Exportez uniquement les murs."
                    )
                explorer.Next()
        except AnalysisFailed:
            raise
        except Exception as exc:   # erreurs OCC (Standard_Failure) ou fichier non STEP
            log.warning("STEP illisible (%s) : %s", file.original_name, exc)
            raise AnalysisFailed(
                "Ce fichier STEP est illisible ou n'est pas un fichier STEP valide "
                "(fichier corrompu, tronqué ou d'un autre format)."
            ) from exc
        if not solids:
            raise AnalysisFailed(
                "Ce fichier STEP ne contient aucun solide 3D (seulement des surfaces ou des courbes). "
                "Exportez le modèle avec des volumes."
            )
        return solids

    # ------------------------------------------------------------------ classification
    def _classify(self, solids: list, up: tuple[float, float, float]) -> tuple[list[_Wall], Counter]:
        from OCP.Bnd import Bnd_OBB
        from OCP.BRepBndLib import BRepBndLib

        opt = self.options
        e1, e2 = _horizontal_basis(up)
        walls: list[_Wall] = []
        rejected: Counter[str] = Counter()
        for solid in solids:
            obb = Bnd_OBB()
            BRepBndLib.AddOBB_s(solid, obb, True, True, False)
            axes = [(d.X(), d.Y(), d.Z()) for d in (obb.XDirection(), obb.YDirection(), obb.ZDirection())]
            sizes = [2 * obb.XHSize(), 2 * obb.YHSize(), 2 * obb.ZHSize()]
            vertical = max(range(3), key=lambda i: abs(_dot3(axes[i], up)))
            if abs(_dot3(axes[vertical], up)) < 0.9:
                rejected["inclinés"] += 1
                continue
            height = sizes[vertical]
            h_idx = [i for i in range(3) if i != vertical]
            length_i, thick_i = sorted(h_idx, key=lambda i: -sizes[i])
            length, thickness = sizes[length_i], sizes[thick_i]
            if height < opt.min_height_mm:
                rejected["dalles ou éléments bas"] += 1
            elif thickness < opt.min_thickness_mm:
                rejected["éléments trop minces"] += 1
            elif thickness > opt.max_thickness_mm:
                rejected["volumes trop épais (murs en L ou fusionnés ?)"] += 1
            elif length < opt.min_length_mm or length < opt.min_aspect * thickness:
                rejected["poteaux ou petits éléments"] += 1
            else:
                c = obb.Center()
                centre = (c.X(), c.Y(), c.Z())
                u = axes[length_i]
                ux, uy = _dot3(u, e1), _dot3(u, e2)
                norm = math.hypot(ux, uy)
                ux, uy = ux / norm, uy / norm
                cx, cy = _dot3(centre, e1), _dot3(centre, e2)
                a = (cx - ux * length / 2, cy - uy * length / 2)
                b = (cx + ux * length / 2, cy + uy * length / 2)
                z_bottom = _dot3(centre, up) - height / 2
                walls.append(_Wall(a, b, thickness, height, z_bottom, [], solid, axes[thick_i]))
        return walls, rejected

    def _attach_openings(self, walls: list[_Wall], up: tuple[float, float, float]) -> None:
        e1, e2 = _horizontal_basis(up)
        for wall in walls:
            wall.openings = self._openings(wall.solid, wall, wall.thickness_axis, e1, e2, up)

    # ------------------------------------------------------------------ ouvertures
    def _openings(self, solid, wall: _Wall, thickness_axis, e1, e2, up) -> list[OpeningGeometry]:  # noqa: ANN001
        from OCP.BRepAdaptor import BRepAdaptor_Surface
        from OCP.BRepGProp import BRepGProp
        from OCP.BRepTools import BRepTools
        from OCP.GeomAbs import GeomAbs_Plane
        from OCP.GProp import GProp_GProps
        from OCP.TopAbs import TopAbs_FACE, TopAbs_WIRE
        from OCP.TopExp import TopExp_Explorer

        opt = self.options
        normal_ref = thickness_axis
        best_face, best_area = None, 0.0
        faces = TopExp_Explorer(solid, TopAbs_FACE)
        while faces.More():
            face = _cast("Face", faces.Current())
            surf = BRepAdaptor_Surface(face)
            if surf.GetType() == GeomAbs_Plane:
                d = surf.Plane().Axis().Direction()
                if abs(_dot3((d.X(), d.Y(), d.Z()), normal_ref)) > 0.98:
                    props = GProp_GProps()
                    BRepGProp.SurfaceProperties_s(face, props)
                    if props.Mass() > best_area:
                        best_face, best_area = face, props.Mass()
            faces.Next()
        if best_face is None:
            return []

        ux, uy = (wall.b[0] - wall.a[0]) / wall.length, (wall.b[1] - wall.a[1]) / wall.length

        def local(vertex) -> tuple[float, float]:  # noqa: ANN001
            p = _point(vertex)
            x, y, z = _dot3(p, e1), _dot3(p, e2), _dot3(p, up)
            return (x - wall.a[0]) * ux + (y - wall.a[1]) * uy, z - wall.z_bottom

        outer = BRepTools.OuterWire_s(best_face)
        openings: list[OpeningGeometry] = []
        wires = TopExp_Explorer(best_face, TopAbs_WIRE)
        while wires.More():
            wire = _cast("Wire", wires.Current())
            if not wire.IsSame(outer):   # trou traversant : fenêtre (ou porte surélevée)
                pts = [local(v) for v in _vertices(wire)]
                w = max(p[0] for p in pts) - min(p[0] for p in pts)
                h = max(p[1] for p in pts) - min(p[1] for p in pts)
                sill = min(p[1] for p in pts)
                if w >= 100 and h >= 100:
                    openings.append(OpeningGeometry("porte" if sill < 150 else "fenetre", int(round(w)), int(round(h))))
            wires.Next()

        # Encoches ouvertes en pied (portes) : lacunes entre les arêtes de base du contour extérieur.
        base_intervals: list[tuple[float, float]] = []
        for edge in _edges(outer):
            (s1, z1), (s2, z2) = _edge_ends(edge, local)
            if z1 <= 5 and z2 <= 5:
                base_intervals.append((min(s1, s2), max(s1, s2)))
        outer_pts = [local(v) for v in _vertices(outer)]
        s_min, s_max = min(p[0] for p in outer_pts), max(p[0] for p in outer_pts)
        for gap_lo, gap_hi in _gaps(base_intervals, s_min, s_max):
            if gap_hi - gap_lo >= opt.min_notch_mm:
                near = [p[1] for p in outer_pts if gap_lo - 5 <= p[0] <= gap_hi + 5 and 5 < p[1] < wall.height - 5]
                openings.append(OpeningGeometry("porte", int(round(gap_hi - gap_lo)),
                                                int(round(max(near) if near else min(opt.door_height_mm, wall.height)))))
        return openings

    # ------------------------------------------------------------------ assemblage
    def _assemble(self, walls: list[_Wall], n_solids: int, rejected: Counter, up_name: str,
                  automatic: bool = True) -> ProjectGeometry:
        opt = self.options
        walls.sort(key=lambda w: (w.z_bottom, round(w.a[1] / 10), round(w.a[0] / 10)))
        levels: list[tuple[float, str]] = []
        names: list[str] = []
        for w in walls:
            for z, name in levels:
                if abs(w.z_bottom - z) <= opt.level_tolerance_mm:
                    names.append(name)
                    break
            else:
                name = f"Niveau {w.z_bottom / 1000:+.2f} m".replace(".", ",")
                levels.append((w.z_bottom, name))
                names.append(name)
        corners = corner_keys([CornerCandidate(i, names[i], w.a, w.b, w.thickness) for i, w in enumerate(walls)])
        counters: Counter[str] = Counter()
        out: list[WallGeometry] = []
        for i, w in enumerate(walls):
            counters[names[i]] += 1
            length, height = int(round(w.length)), int(round(w.height))
            openings = _cap(w.openings, length, height)
            out.append(WallGeometry(nom=f"{names[i]} · Mur n°{counters[names[i]]}"[:120], longueur_mm=length,
                                    hauteur_mm=height, is_corner=i in corners, openings=tuple(openings)))
        notes = [
            "APPROXIMATION : un fichier STEP ne désigne pas les murs ; ils sont reconnus par leur forme "
            "(solide vertical, épaisseur 40 à 600 mm, longueur ≥ 3 épaisseurs).",
            f"{len(out)} mur(s) reconnu(s) sur {n_solids} solide(s), {sum(len(w.openings) for w in out)} ouverture(s), "
            f"{len(levels)} niveau(x) (altitude du pied des murs). Unités converties en millimètres.",
            "La hauteur retenue est la hauteur maximale de chaque solide (murs à sommet incliné : surestimée).",
            "Les angles sont déduits des jonctions entre murs d'un même niveau.",
        ]
        if up_name == "Y":
            notes.append("Axe vertical du fichier : Y" + (" (détecté automatiquement)." if automatic else " (configuration)."))
        if rejected:
            notes.append("Solides ignorés : " + _describe(rejected) + ".")
        return ProjectGeometry(walls=tuple(out), source="step", notes=tuple(notes))


# ---------------------------------------------------------------------- helpers
def _cast(kind: str, shape):  # noqa: ANN001, ANN202
    """TopoDS.Solid / Face / Wire / Vertex / Edge (nom des fonctions statiques variable selon la version d'OCP)."""
    from OCP.TopoDS import TopoDS

    fn = getattr(TopoDS, kind + "_s", None) or getattr(TopoDS, kind)
    return fn(shape)


def _dot3(a, b) -> float:  # noqa: ANN001
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _horizontal_basis(up: tuple[float, float, float]):
    return ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0)) if up[2] else ((1.0, 0.0, 0.0), (0.0, 0.0, 1.0))


def _point(vertex) -> tuple[float, float, float]:  # noqa: ANN001
    from OCP.BRep import BRep_Tool

    p = BRep_Tool.Pnt_s(_cast("Vertex", vertex))
    return p.X(), p.Y(), p.Z()


def _vertices(shape) -> list:  # noqa: ANN001
    from OCP.TopAbs import TopAbs_VERTEX
    from OCP.TopExp import TopExp_Explorer

    out, it = [], TopExp_Explorer(shape, TopAbs_VERTEX)
    while it.More():
        out.append(it.Current())
        it.Next()
    return out


def _edges(wire) -> list:  # noqa: ANN001
    from OCP.TopAbs import TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer

    out, it = [], TopExp_Explorer(wire, TopAbs_EDGE)
    while it.More():
        out.append(_cast("Edge", it.Current()))
        it.Next()
    return out


def _edge_ends(edge, local):  # noqa: ANN001
    v = _vertices(edge)
    return local(v[0]), local(v[-1])


def _gaps(intervals: list[tuple[float, float]], lo: float, hi: float) -> list[tuple[float, float]]:
    """Lacunes de [lo, hi] non couvertes par les intervalles."""
    gaps, cursor = [], lo
    for a, b in sorted(intervals):
        if a > cursor + 1e-6:
            gaps.append((cursor, a))
        cursor = max(cursor, b)
    if hi > cursor + 1e-6:
        gaps.append((cursor, hi))
    return gaps


def _cap(openings: list[OpeningGeometry], length: int, height: int) -> list[OpeningGeometry]:
    """Borne les ouvertures au mur et garde un mur exploitable (net > 0)."""
    fitted = [OpeningGeometry(o.type, min(o.largeur_mm, length), min(o.hauteur_mm, height)) for o in openings]
    kept = sorted(fitted, key=lambda o: -o.area_mm2)
    while kept and sum(o.area_mm2 for o in kept) > 0.95 * length * height:
        kept.pop(0)
    return kept


def _describe(rejected: Counter) -> str:
    return ", ".join(f"{n} {label}" for label, n in rejected.most_common()) or "aucun autre élément"
