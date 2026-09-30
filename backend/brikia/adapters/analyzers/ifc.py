"""Analyse réelle d'un plan IFC (IFC2X3, IFC4, IFC4X3) avec IfcOpenShell.

Principe : un mur IFC peut avoir un axe en polyligne (contour fermé, angles) ;
BrikIA raisonne en murs droits. Chaque ``IfcWall`` est donc découpé en un mur
BrikIA par segment de son axe.

- longueur      : longueur du segment d'axe ;
- hauteur       : ``GrossSideArea`` (quantités du fichier) / longueur totale de l'axe, ce qui
                  restitue la hauteur moyenne d'un mur recoupé par un toit ; à défaut,
                  hauteur de la géométrie (Z max - Z min) ;
- ouvertures    : ``IfcOpeningElement`` du mur (géométrie réelle du trou), type déduit de la
                  porte/fenêtre qui le remplit, rattachées au segment le plus proche ;
- angles        : jonctions en L entre murs d'un même étage (voir ``corner_keys``) ;
- niveau        : ``IfcBuildingStorey`` (inclus dans le nom du mur).

Seuls les murs comptent : poteaux, dalles, toitures... sont ignorés. Unités :
lues dans le fichier (mètres, millimètres, ...), tout est converti en mm entiers.
"""

from __future__ import annotations

import logging
import time
from collections import Counter
from dataclasses import dataclass, field

from ...domain.errors import AnalysisFailed
from ...domain.geometry import OpeningGeometry, ProjectGeometry, WallGeometry
from .base import AnalyzerUnavailable, PlanFile
from ._native import silence_native_stdout
from .geometry_utils import (
    CornerCandidate, Point, corner_keys, dist, min_area_rect, point_segment_distance, unit_vector,
)

log = logging.getLogger("brikia.analyzers.ifc")

DEFAULT_THICKNESS_MM = 250.0
MAX_NAME = 120


@dataclass
class _Segment:
    a: Point
    b: Point
    openings: list[OpeningGeometry] = field(default_factory=list)

    @property
    def length(self) -> float:
        return dist(self.a, self.b)


@dataclass
class _WallInfo:
    step_id: int
    level: str
    elevation: float
    base_name: str
    height_mm: int
    thickness_mm: float
    segments: list[_Segment]


class IfcPlanAnalyzer:
    name = "ifc"

    def __init__(self, min_segment_mm: float = 150.0) -> None:
        try:
            import ifcopenshell  # noqa: F401
            import ifcopenshell.geom  # noqa: F401
            import ifcopenshell.util.element  # noqa: F401
            import ifcopenshell.util.placement  # noqa: F401
            import ifcopenshell.util.unit  # noqa: F401
            import numpy  # noqa: F401
        except ImportError as exc:
            raise AnalyzerUnavailable("IFC", "ifcopenshell") from exc
        self.min_segment_mm = min_segment_mm

    # ------------------------------------------------------------------ lecture
    def analyse(self, file: PlanFile) -> ProjectGeometry:
        import ifcopenshell
        import ifcopenshell.geom
        import ifcopenshell.util.unit as U

        started = time.perf_counter()
        try:
            model = ifcopenshell.open(str(file.path))
        except Exception as exc:
            log.warning("IFC illisible (%s) : %s", file.original_name, exc)
            raise AnalysisFailed(
                "Ce fichier IFC est illisible ou n'est pas un fichier IFC valide "
                "(fichier corrompu, tronqué ou d'un autre format)."
            ) from exc

        walls = sorted(model.by_type("IfcWall"), key=lambda w: w.id())
        if not walls:
            raise AnalysisFailed(
                "Aucun mur n'a été trouvé dans ce fichier IFC (aucune entité « IfcWall »). "
                "Vérifiez que le modèle contient bien des murs et exportez-le de nouveau."
            )

        try:
            mm = U.calculate_unit_scale(model) * 1000.0           # unité du fichier -> mm
            area_m2 = U.calculate_unit_scale(model, "AREAUNIT")   # unité de surface -> m²
        except Exception:
            mm, area_m2 = 1000.0, 1.0
            log.warning("Unités IFC non lisibles : mètres supposés")

        settings = ifcopenshell.geom.settings()
        _set(settings, "use-world-coords", True)
        _set(settings, "disable-opening-subtractions", True)  # volume plein : hauteur fiable

        stats: Counter[str] = Counter()
        infos: list[_WallInfo] = []
        with silence_native_stdout():  # IfcOpenShell imprime des milliers de lignes de débogage
            for wall in walls:
                info = self._read_wall(model, settings, wall, mm, area_m2, stats)
                if info is not None:
                    infos.append(info)
            if infos:
                by_id = {w.id(): w for w in walls}
                for info in infos:
                    self._read_openings(model, settings, walls_by_id=by_id, info=info, stats=stats)
        if not infos:
            raise AnalysisFailed(
                f"Les {len(walls)} mur(s) de ce fichier IFC n'ont pas de géométrie exploitable "
                "(pas de volume 3D ni d'axe). Réexportez le modèle avec la géométrie des murs."
            )

        geometry = self._assemble(model, infos, stats, len(walls), time.perf_counter() - started)
        log.info("IFC %s : %d murs lus -> %d murs BrikIA en %.1fs",
                 file.original_name, len(walls), len(geometry.walls), time.perf_counter() - started)
        return geometry

    # ------------------------------------------------------------------ murs
    def _read_wall(self, model, settings, wall, mm: float, area_m2: float,
                   stats: Counter) -> _WallInfo | None:  # noqa: ANN001
        import numpy as np
        import ifcopenshell.util.element as E
        import ifcopenshell.util.placement as P

        body = _representation(wall, "Body")
        if body is None:
            stats["sans_geometrie"] += 1
            return None
        try:
            verts = _mesh(settings, wall, body)   # en mètres
        except Exception as exc:
            log.debug("Géométrie du mur %s illisible : %s", wall.id(), exc)
            stats["sans_geometrie"] += 1
            return None
        if len(verts) == 0:
            stats["sans_geometrie"] += 1
            return None
        z_min, z_max = float(verts[:, 2].min()) * 1000.0, float(verts[:, 2].max()) * 1000.0
        height_geom = z_max - z_min
        if height_geom < 300:
            stats["sans_geometrie"] += 1   # mur plat / dégénéré
            return None

        psets = E.get_psets(wall, qtos_only=True).get("Qto_WallBaseQuantities", {})
        width_q = psets.get("Width")
        thickness = float(width_q) * mm if width_q else None

        # -- axe : polyligne de l'IfcWall, sinon reconstruit depuis le volume
        axis_pts = _axis_points(wall, P.get_local_placement(wall.ObjectPlacement), mm)
        reconstructed = False
        if axis_pts is None or len(axis_pts) < 2:
            rect = min_area_rect([(x * 1000.0, y * 1000.0) for x, y, _ in verts])
            half = rect.length / 2
            axis_pts = [(rect.center[0] - rect.direction[0] * half, rect.center[1] - rect.direction[1] * half),
                        (rect.center[0] + rect.direction[0] * half, rect.center[1] + rect.direction[1] * half)]
            thickness = thickness or rect.width
            reconstructed = True
            stats["axe_reconstruit"] += 1
        thickness = thickness or DEFAULT_THICKNESS_MM

        segments = _segments(axis_pts, self.min_segment_mm)
        stats["segments_trop_courts"] += max(0, len(axis_pts) - 1 - len(segments))
        if not segments:
            stats["sans_geometrie"] += 1
            return None
        if len(segments) > 1:
            stats["murs_decoupes"] += 1

        # -- hauteur : surface brute du fichier / longueur d'axe, sinon géométrie
        total_length = sum(s.length for s in segments)
        height = height_geom
        gross = psets.get("GrossSideArea")
        if gross and total_length > 0:
            equivalent = float(gross) * area_m2 * 1e6 / total_length
            if 0.3 * height_geom <= equivalent <= 1.05 * height_geom:
                height = equivalent
                stats["hauteur_quantites"] += 1
            else:
                stats["hauteur_geometrie"] += 1
        else:
            stats["hauteur_geometrie"] += 1

        level, elevation = _storey(wall, mm)
        base = (wall.Name or wall.ObjectType or "Mur").strip() or "Mur"
        return _WallInfo(wall.id(), level, elevation, base, int(round(height)), thickness, segments)

    # ------------------------------------------------------------------ ouvertures
    def _read_openings(self, model, settings, walls_by_id, info: _WallInfo, stats: Counter) -> None:  # noqa: ANN001
        wall = walls_by_id[info.step_id]
        for rel in wall.HasOpenings or []:
            opening = rel.RelatedOpeningElement
            body = _representation(opening, "Body")
            if body is None:
                stats["ouvertures_ignorees"] += 1
                continue
            try:
                verts = _mesh(settings, opening, body)
            except Exception:
                stats["ouvertures_ignorees"] += 1
                continue
            if len(verts) == 0:
                stats["ouvertures_ignorees"] += 1
                continue
            mm_pts = [(x * 1000.0, y * 1000.0) for x, y, _ in verts]
            centre = ((min(p[0] for p in mm_pts) + max(p[0] for p in mm_pts)) / 2,
                      (min(p[1] for p in mm_pts) + max(p[1] for p in mm_pts)) / 2)
            height = (float(verts[:, 2].max()) - float(verts[:, 2].min())) * 1000.0

            segment = min(info.segments, key=lambda s: point_segment_distance(centre, s.a, s.b)[0])
            ux, uy = unit_vector(segment.a, segment.b)
            along = [p[0] * ux + p[1] * uy for p in mm_pts]
            width = max(along) - min(along)   # largeur du trou le long du mur

            width, height, clamped = _clamp(width, height, segment.length, info.height_mm)
            if width < 100 or height < 100:
                stats["ouvertures_ignorees"] += 1
                continue
            if clamped:
                stats["ouvertures_ajustees"] += 1
            segment.openings.append(OpeningGeometry(_opening_type(opening), int(round(width)),
                                                    int(round(height))))
            stats["ouvertures"] += 1

    # ------------------------------------------------------------------ assemblage
    def _assemble(self, model, infos: list[_WallInfo], stats: Counter, n_ifc_walls: int,
                  seconds: float) -> ProjectGeometry:  # noqa: ANN001
        import ifcopenshell

        infos = sorted(infos, key=lambda i: (i.elevation, i.step_id))
        candidates = [
            CornerCandidate(key, i.level, s.a, s.b, i.thickness_mm)
            for key, (i, s) in enumerate(_iter_segments(infos))
        ]
        corners = corner_keys(candidates)

        counters: Counter[tuple[str, str]] = Counter()
        walls: list[WallGeometry] = []
        key = 0
        for info in infos:
            counters[(info.level, info.base_name)] += 1
            n = counters[(info.level, info.base_name)]
            for idx, seg in enumerate(info.segments, start=1):
                suffix = f"{n}" if len(info.segments) == 1 else f"{n}.{idx}"
                name = f"{info.level} · {info.base_name} n°{suffix}"[:MAX_NAME]
                openings = _cap_openings(seg.openings, int(round(seg.length)) * info.height_mm, stats)
                walls.append(WallGeometry(
                    nom=name, longueur_mm=int(round(seg.length)), hauteur_mm=info.height_mm,
                    is_corner=key in corners, openings=tuple(openings)))
                key += 1

        notes = [
            f"Lecture IFC réelle ({model.schema}, IfcOpenShell {ifcopenshell.version}) en {seconds:.1f} s : "
            f"{n_ifc_walls} mur(s) IFC → {len(walls)} mur(s) droit(s), {stats['ouvertures']} ouverture(s).",
            "Seuls les murs sont pris en compte (poteaux, dalles, toitures… ignorés).",
        ]
        if stats["murs_decoupes"]:
            notes.append(f"{stats['murs_decoupes']} mur(s) à axe polygonal découpé(s) en segments droits.")
        if stats["hauteur_geometrie"]:
            notes.append(f"Hauteur issue de la géométrie (et non des quantités du fichier) pour "
                         f"{stats['hauteur_geometrie']} mur(s).")
        if stats["sans_geometrie"]:
            notes.append(f"{stats['sans_geometrie']} mur(s) ignoré(s) : pas de géométrie 3D exploitable.")
        if stats["segments_trop_courts"]:
            notes.append(f"{stats['segments_trop_courts']} segment(s) de moins de "
                         f"{int(self.min_segment_mm)} mm ignoré(s).")
        if stats["axe_reconstruit"]:
            notes.append(f"{stats['axe_reconstruit']} mur(s) sans axe exploitable : longueur déduite du volume.")
        if stats["ouvertures_ignorees"]:
            notes.append(f"{stats['ouvertures_ignorees']} ouverture(s) ignorée(s) (géométrie absente ou trop petite).")
        if stats["ouvertures_ajustees"]:
            notes.append(f"{stats['ouvertures_ajustees']} ouverture(s) ramenée(s) aux dimensions de leur mur.")
        if stats["ouvertures_limitees"]:
            notes.append(f"{stats['ouvertures_limitees']} ouverture(s) retirée(s) : elles occupaient presque tout le mur.")
        notes.append("Les angles sont déduits des jonctions entre murs d'un même niveau.")
        return ProjectGeometry(walls=tuple(walls), source="ifc", notes=tuple(notes))


# ---------------------------------------------------------------------- helpers
def _iter_segments(infos: list[_WallInfo]):
    for info in infos:
        for seg in info.segments:
            yield info, seg


def _set(settings, name: str, value) -> None:  # noqa: ANN001
    """Réglage de géométrie ; tolère un réglage absent (noms variables selon la version)."""
    try:
        settings.set(name, value)
    except RuntimeError:
        log.warning("Réglage IfcOpenShell « %s » indisponible dans cette version", name)


def _representation(element, identifier: str):  # noqa: ANN001
    if not getattr(element, "Representation", None):
        return None
    for rep in element.Representation.Representations:
        if rep.RepresentationIdentifier == identifier:
            return rep
    return None


def _mesh(settings, element, representation):  # noqa: ANN001
    import ifcopenshell.geom
    import numpy as np

    shape = ifcopenshell.geom.create_shape(settings, element, representation)
    return np.array(shape.geometry.verts).reshape(-1, 3)


def _axis_points(wall, matrix, mm: float) -> list[Point] | None:  # noqa: ANN001
    """Points de l'axe (IfcPolyline) en coordonnées monde, en mm ; None si indisponible."""
    import numpy as np

    axis = _representation(wall, "Axis")
    if axis is None or not axis.Items or not axis.Items[0].is_a("IfcPolyline"):
        return None
    pts: list[Point] = []
    for p in axis.Items[0].Points:
        c = list(p.Coordinates) + [0.0] * (3 - len(p.Coordinates))
        x, y, _ = (matrix @ np.array([c[0], c[1], c[2], 1.0]))[:3]
        pt = (float(x) * mm, float(y) * mm)
        if not pts or dist(pts[-1], pt) > 1e-6:
            pts.append(pt)
    return pts


def _segments(points: list[Point], min_length: float) -> list[_Segment]:
    return [_Segment(a, b) for a, b in zip(points, points[1:]) if dist(a, b) >= min_length]


def _storey(wall, mm: float) -> tuple[str, float]:  # noqa: ANN001
    import ifcopenshell.util.element as E

    container = E.get_container(wall)
    while container is not None and not container.is_a("IfcBuildingStorey"):
        container = E.get_container(container) or E.get_aggregate(container)
    if container is None:
        return "Niveau ?", 0.0
    name = (container.Name or container.LongName or f"Niveau {container.id()}").strip()
    return name, float(container.Elevation or 0.0) * mm


def _opening_type(opening) -> str:  # noqa: ANN001
    for fill in opening.HasFillings or []:
        element = fill.RelatedBuildingElement
        if element.is_a("IfcDoor"):
            return "porte"
        if element.is_a("IfcWindow"):
            return "fenetre"
    return "ouverture"


def _clamp(width: float, height: float, max_width: float, max_height: float) -> tuple[float, float, bool]:
    w, h = min(width, max_width), min(height, max_height)
    return w, h, (w != width or h != height)


def _cap_openings(openings: list[OpeningGeometry], gross_mm2: int, stats: Counter) -> list[OpeningGeometry]:
    """Garde le mur exploitable : les ouvertures ne doivent pas occuper ~tout son aire."""
    kept = sorted(openings, key=lambda o: -o.area_mm2)
    while kept and sum(o.area_mm2 for o in kept) > 0.95 * gross_mm2:
        kept.pop(0)
        stats["ouvertures_limitees"] += 1
    return kept
