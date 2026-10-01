"""Analyse d'un plan DXF (2D) avec ezdxf — APPROXIMATION assumée.

Un DXF est un dessin : il ne contient ni hauteur de mur ni ouverture typée. BrikIA en
déduit une géométrie plausible, toujours signalée comme approximative :

- calques : les murs, portes et fenêtres sont reconnus par expression régulière sur le
  nom du calque (configurable : ``BRIKIA_DXF_WALL_LAYERS`` etc.) ;
- murs    : deux traits parallèles (les deux faces du mur) séparés de 40 à 700 mm forment un
  mur ; l'axe est la moyenne des deux faces, l'épaisseur leur écart. Les traits sans
  vis-à-vis (mur dessiné en un seul trait) deviennent des murs filaires de 200 mm ;
- hauteur : valeur par défaut configurable (le DXF n'en contient pas) ;
- ouvertures : repère (trait ou polyligne) des calques porte/fenêtre, parallèle et contigu à
  l'axe d'un mur ; largeur = longueur du repère, hauteur = valeur par défaut ;
- unité   : l'en-tête ``$INSUNITS`` est souvent faux (un plan en mètres annoncé en mm) ;
  l'unité est donc validée par la plausibilité de l'emprise du bâtiment ;
- niveaux : un DXF = un étage.

Limites : arcs et courbes ignorés ; ouvertures dessinées comme interruption du mur (et non
comme repère) non reconnues ; aucune hauteur d'allège.
"""

from __future__ import annotations

import logging
import math
import re
from bisect import bisect_left, bisect_right
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from ...domain.errors import AnalysisFailed
from ...domain.geometry import OpeningGeometry, ProjectGeometry, WallGeometry
from .base import AnalyzerUnavailable, PlanFile
from .geometry_utils import CornerCandidate, Point, corner_keys, dist

log = logging.getLogger("brikia.analyzers.dxf")

# $INSUNITS -> millimètres par unité
_INSUNITS = {1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0, 10: 914.4, 14: 100.0}
_INSUNITS_NAMES = {1: "pouces", 2: "pieds", 4: "mm", 5: "cm", 6: "m", 10: "yards", 14: "dm"}
_CANDIDATES = (("mm", 1.0), ("cm", 10.0), ("m", 1000.0))
_PLAUSIBLE_MM = (2_000.0, 400_000.0)        # emprise d'un bâtiment : 2 m à 400 m
_TYPICAL_MM = 20_000.0

# Les angles de droite sont définis modulo π ; la coupure est placée à -22,5° / 157,5°, loin des
# orientations usuelles (0° et 90°, même avec un léger bruit), pour que les murs quasi horizontaux
# ou verticaux ne basculent jamais de part et d'autre de la coupure.
_WRAP = math.radians(22.5)

_LABELS = {"EXTERNAL_WALL": "Mur extérieur", "PARTITION": "Cloison", "BASEMENT_WALL": "Mur de sous-sol"}


@dataclass(frozen=True)
class DxfOptions:
    wall_height_mm: int = 2700
    door_height_mm: int = 2100
    window_height_mm: int = 1200
    wall_layers: str = r"wall|mur|cloison|partition|paroi|refend|muro"
    door_layers: str = r"door|porte|puerta"
    window_layers: str = r"window|fen[eê]tre|vitr|ventana"
    min_thickness_mm: float = 40.0
    max_thickness_mm: float = 700.0
    min_wall_length_mm: float = 300.0
    single_line_thickness_mm: float = 200.0
    collinear_tol_mm: float = 10.0

    @classmethod
    def from_settings(cls, s) -> DxfOptions:  # noqa: ANN001
        return cls(wall_height_mm=s.dxf_wall_height_mm, door_height_mm=s.dxf_door_height_mm,
                   window_height_mm=s.dxf_window_height_mm, wall_layers=s.dxf_wall_layers,
                   door_layers=s.dxf_door_layers, window_layers=s.dxf_window_layers)


# ----------------------------------------------------------------- structures internes
@dataclass
class Seg:
    a: Point
    b: Point
    layer: str


@dataclass
class Face:
    """Trait (ou suite de traits colinéaires fusionnés) : repère (s, d) d'une droite."""

    theta: float          # direction dans [0, π)
    d: float              # décalage perpendiculaire
    s0: float
    s1: float
    layer: str
    side: int = 0         # côté du partenaire déjà apparié (-1/+1), 0 = aucun
    covered: list[tuple[float, float]] = field(default_factory=list)

    @property
    def length(self) -> float:
        return self.s1 - self.s0


@dataclass
class Piece:
    """Mur détecté : axe (a, b) en mm, épaisseur, calque, filaire ou non."""

    a: Point
    b: Point
    thickness: float
    layer: str
    theta: float
    d_axis: float
    s0: float
    s1: float
    single_line: bool = False
    openings: list[OpeningGeometry] = field(default_factory=list)

    @property
    def length(self) -> float:
        return self.s1 - self.s0


class DxfPlanAnalyzer:
    name = "dxf"

    def __init__(self, options: DxfOptions | None = None) -> None:
        try:
            import ezdxf  # noqa: F401
        except ImportError as exc:
            raise AnalyzerUnavailable("DXF", "ezdxf") from exc
        self.options = options or DxfOptions()
        self._wall_re = re.compile(self.options.wall_layers, re.IGNORECASE)
        self._door_re = re.compile(self.options.door_layers, re.IGNORECASE)
        self._window_re = re.compile(self.options.window_layers, re.IGNORECASE)

    # ------------------------------------------------------------------ lecture
    def analyse(self, file: PlanFile) -> ProjectGeometry:
        doc = self._read(file)
        layers_count: Counter[str] = Counter()
        walls_raw: list[Seg] = []
        doors_raw: list[Seg] = []
        windows_raw: list[Seg] = []
        skipped_curves = 0
        for entity, layer in _iter_entities(doc.modelspace()):
            layers_count[layer] += 1
            kind = self._classify(layer)
            if kind is None:
                continue
            segs, curves = _entity_segments(entity, layer)
            skipped_curves += curves
            {"wall": walls_raw, "door": doors_raw, "window": windows_raw}[kind].extend(segs)

        if not layers_count:
            raise AnalysisFailed(
                "Ce fichier DXF est vide ou illisible : il ne contient aucune entité dessinée. "
                "Les DWG (binaires AutoCAD) doivent d'abord être enregistrés au format DXF."
            )
        if not walls_raw:
            found = ", ".join(sorted(layers_count)[:12]) or "aucun"
            raise AnalysisFailed(
                "Aucun mur détecté dans ce plan DXF : aucun calque de murs reconnu ou calques vides "
                f"(calques présents : {found}). Les calques de murs doivent contenir « wall », « mur », "
                "« cloison », « partition »… ; sinon adaptez BRIKIA_DXF_WALL_LAYERS."
            )

        factor, unit_note = _detect_unit(doc.header.get("$INSUNITS"), walls_raw)
        for seg in (*walls_raw, *doors_raw, *windows_raw):
            seg.a = (seg.a[0] * factor, seg.a[1] * factor)
            seg.b = (seg.b[0] * factor, seg.b[1] * factor)

        opt = self.options
        pieces, unpaired = _wall_pieces(walls_raw, opt)
        if not pieces:
            raise AnalysisFailed(
                "Aucun mur exploitable n'a pu être reconstitué à partir des traits du plan DXF "
                "(traits trop courts ou sans vis-à-vis). Vérifiez l'échelle et les calques."
            )
        opened = _attach_openings(pieces, doors_raw, windows_raw, opt)

        pieces.sort(key=lambda p: (p.layer, round(p.a[1] / 10), round(p.a[0] / 10)))
        corners = corner_keys([CornerCandidate(i, "", p.a, p.b, p.thickness) for i, p in enumerate(pieces)])
        counters: Counter[str] = Counter()
        walls: list[WallGeometry] = []
        for i, p in enumerate(pieces):
            label = _layer_label(p.layer)
            counters[label] += 1
            length = int(round(p.length))
            openings = _cap(p.openings, length * opt.wall_height_mm)
            walls.append(WallGeometry(
                nom=f"{label} n°{counters[label]}"[:120], longueur_mm=length, hauteur_mm=opt.wall_height_mm,
                is_corner=i in corners, openings=tuple(openings)))

        notes = [
            "APPROXIMATION : plan DXF 2D. Les hauteurs ne figurent pas dans le fichier : "
            f"{opt.wall_height_mm} mm par défaut pour tous les murs ; ouvertures : "
            f"portes {opt.door_height_mm} mm, fenêtres {opt.window_height_mm} mm de haut par défaut.",
            unit_note,
            f"{len(walls)} mur(s) reconstitué(s) à partir des traits des calques de murs, "
            f"{sum(len(w.openings) for w in walls)} ouverture(s) issue(s) des calques portes/fenêtres.",
            "Un DXF correspond à un seul niveau ; importez un projet par étage.",
        ]
        if unpaired:
            notes.append(f"{unpaired} mur(s) dessiné(s) par un seul trait : épaisseur supposée "
                         f"{int(opt.single_line_thickness_mm)} mm.")
        if opened["orphans"]:
            notes.append(f"{opened['orphans']} repère(s) de porte/fenêtre sans mur correspondant ignoré(s).")
        if skipped_curves:
            notes.append(f"{skipped_curves} arc(s)/courbe(s) sur les calques de murs ignoré(s).")
        ignored = [f"{name} ({n})" for name, n in layers_count.most_common() if self._classify(name) is None][:6]
        if ignored:
            notes.append("Calques non pris en compte : " + ", ".join(ignored) + ".")
        return ProjectGeometry(walls=tuple(walls), source="dxf", notes=tuple(notes))

    # ------------------------------------------------------------------ helpers
    def _read(self, file: PlanFile):  # noqa: ANN202
        import ezdxf
        from ezdxf import recover

        try:
            return ezdxf.readfile(str(file.path))
        except (ezdxf.DXFError, OSError, UnicodeDecodeError, ValueError):
            try:  # fichier légèrement abîmé : réparation automatique
                doc, auditor = recover.readfile(str(file.path))
                if auditor.has_fixes or auditor.has_errors:
                    log.info("DXF %s réparé (%d correctifs)", file.original_name, len(auditor.fixes))
                return doc
            except Exception as exc:
                log.warning("DXF illisible (%s) : %s", file.original_name, exc)
                raise AnalysisFailed(
                    "Ce fichier DXF est illisible ou n'est pas un fichier DXF valide. "
                    "Les DWG (binaires AutoCAD) doivent d'abord être enregistrés au format DXF."
                ) from exc

    def _classify(self, layer: str) -> str | None:
        if self._door_re.search(layer):
            return "door"
        if self._window_re.search(layer):
            return "window"
        if self._wall_re.search(layer):
            return "wall"
        return None


# ---------------------------------------------------------------------- entités -> traits
def _iter_entities(layout, _depth: int = 0):  # noqa: ANN001
    for e in layout:
        t = e.dxftype()
        if t == "INSERT" and _depth < 3:
            try:
                for v in e.virtual_entities():
                    layer = v.dxf.layer if v.dxf.layer != "0" else e.dxf.layer
                    yield v, layer
            except Exception:  # bloc défectueux : ignoré
                continue
        else:
            yield e, e.dxf.layer


def _entity_segments(e, layer: str) -> tuple[list[Seg], int]:  # noqa: ANN001
    """Traits d'une entité et nombre de courbes ignorées."""
    t = e.dxftype()
    if t == "LINE":
        a, b = e.dxf.start, e.dxf.end
        return ([Seg((a[0], a[1]), (b[0], b[1]), layer)] if (a[0], a[1]) != (b[0], b[1]) else []), 0
    if t == "LWPOLYLINE":
        pts = [(p[0], p[1], p[4]) for p in e.get_points("xyseb")]   # x, y, bulge en dernière position
        closed = e.closed
    elif t == "POLYLINE":
        if not (e.is_2d_polyline or e.is_3d_polyline):
            return [], 0
        pts = [(v.dxf.location[0], v.dxf.location[1], getattr(v.dxf, "bulge", 0.0) or 0.0) for v in e.vertices]
        closed = e.is_closed
    elif t in ("ARC", "CIRCLE", "ELLIPSE", "SPLINE"):
        return [], 1
    else:
        return [], 0
    segs, curves = [], 0
    n = len(pts)
    for i in range(n if closed else n - 1):
        (x0, y0, bulge), (x1, y1, _) = pts[i], pts[(i + 1) % n]
        if bulge:
            curves += 1
        elif (x0, y0) != (x1, y1):
            segs.append(Seg((x0, y0), (x1, y1), layer))
    return segs, curves


# ---------------------------------------------------------------------- unité
def _detect_unit(header_units, segs: list[Seg]) -> tuple[float, str]:  # noqa: ANN001
    xs = [p[0] for s in segs for p in (s.a, s.b)]
    ys = [p[1] for s in segs for p in (s.a, s.b)]
    extent = max(max(xs) - min(xs), max(ys) - min(ys))

    def plausible(f: float) -> bool:
        return _PLAUSIBLE_MM[0] <= extent * f <= _PLAUSIBLE_MM[1]

    declared = _INSUNITS.get(header_units)
    if declared is not None and plausible(declared):
        return declared, f"Unité du plan : {_INSUNITS_NAMES[header_units]} (en-tête du fichier)."
    options = [(n, f) for n, f in _CANDIDATES if plausible(f)]
    if not options:
        raise AnalysisFailed(
            f"Les dimensions de ce plan DXF (emprise {extent:g} unités) sont incompatibles avec un bâtiment, "
            "quelle que soit l'unité. Vérifiez l'échelle du dessin."
        )
    name, factor = min(options, key=lambda o: abs(math.log(extent * o[1] / _TYPICAL_MM)))
    full = {"mm": "millimètres", "cm": "centimètres", "m": "mètres"}[name]
    if declared is None:
        why = "l'en-tête ne précise pas l'unité"
    else:
        why = f"l'en-tête annonce « {_INSUNITS_NAMES[header_units]} » mais l'emprise du plan est incompatible"
    return factor, f"Unité déduite des dimensions du plan : {full} ({why})."


# ---------------------------------------------------------------------- murs
def _to_face(seg: Seg) -> Face:
    dx, dy = seg.b[0] - seg.a[0], seg.b[1] - seg.a[1]
    theta = math.atan2(dy, dx) % math.pi
    if theta >= math.pi - _WRAP:
        theta -= math.pi
    if abs(theta) < 1e-9:   # horizontal exact
        theta = 0.0
    ux, uy = math.cos(theta), math.sin(theta)
    s_a, s_b = seg.a[0] * ux + seg.a[1] * uy, seg.b[0] * ux + seg.b[1] * uy
    d = -seg.a[0] * uy + seg.a[1] * ux
    return Face(theta, d, min(s_a, s_b), max(s_a, s_b), seg.layer)


def _merge_collinear(segs: list[Seg], tol: float) -> list[Face]:
    """Fusionne les traits alignés (même droite, à la tolérance près) qui se touchent ou se chevauchent."""
    faces = [_to_face(s) for s in segs]
    faces.sort(key=lambda f: (round(f.theta, 2), round(f.d / max(tol, 1e-6)), f.s0))
    groups: list[list[Face]] = []
    for f in faces:
        placed = False
        for g in reversed(groups[-6:]):   # les groupes voisins suffisent grâce au tri
            ref = g[0]
            dtheta = min(abs(f.theta - ref.theta), math.pi - abs(f.theta - ref.theta))
            if dtheta < math.radians(0.5) and abs(f.d - ref.d) <= tol and f.layer == ref.layer:
                g.append(f)
                placed = True
                break
        if not placed:
            groups.append([f])
    merged: list[Face] = []
    for g in groups:
        g.sort(key=lambda f: f.s0)
        cur = Face(g[0].theta, sum(f.d for f in g) / len(g), g[0].s0, g[0].s1, g[0].layer)
        for f in g[1:]:
            if f.s0 <= cur.s1 + tol:
                cur.s1 = max(cur.s1, f.s1)
            else:
                merged.append(cur)
                cur = Face(g[0].theta, cur.d, f.s0, f.s1, g[0].layer)
        merged.append(cur)
    return merged


def _wall_pieces(segs: list[Seg], opt: DxfOptions) -> tuple[list[Piece], int]:
    faces = [f for f in _merge_collinear(segs, opt.collinear_tol_mm) if f.length >= 100]
    candidates: list[tuple[float, int, int, float, float]] = []
    # Index : faces regroupées par direction (bacs de 1°) et triées par écart perpendiculaire,
    # pour ne comparer que des voisines plausibles (le coût devient quasi linéaire).
    bins: dict[int, list[int]] = defaultdict(list)
    for idx, f in enumerate(faces):
        bins[round(math.degrees(f.theta))].append(idx)
    sorted_bins = {b: sorted(v, key=lambda k: faces[k].d) for b, v in bins.items()}
    d_values = {b: [faces[k].d for k in v] for b, v in sorted_bins.items()}
    for i, a in enumerate(faces):
        base = round(math.degrees(a.theta))
        for b in (base - 1, base, base + 1):
            if b not in sorted_bins:
                continue
            lo_k = bisect_left(d_values[b], a.d - opt.max_thickness_mm)
            hi_k = bisect_right(d_values[b], a.d + opt.max_thickness_mm)
            for k in sorted_bins[b][lo_k:hi_k]:
                if k <= i:
                    continue
                c = faces[k]
                if a.layer != c.layer or abs(a.theta - c.theta) > math.radians(1.0):
                    continue
                gap = abs(a.d - c.d)
                if not (opt.min_thickness_mm <= gap <= opt.max_thickness_mm):
                    continue
                lo, hi = max(a.s0, c.s0), min(a.s1, c.s1)
                if hi - lo >= max(100.0, 0.2 * min(a.length, c.length)):
                    candidates.append((gap, i, k, lo, hi))
    candidates.sort()   # (écart, i, j) : déterministe ; les vis-à-vis les plus proches d'abord : évite d'apparier deux murs voisins
    pieces: list[Piece] = []
    for gap, i, j, lo, hi in candidates:
        a, b = faces[i], faces[j]
        side_a, side_b = (1 if b.d > a.d else -1), (1 if a.d > b.d else -1)
        if (a.side not in (0, side_a)) or (b.side not in (0, side_b)):
            continue
        if _overlaps(a.covered, lo, hi) or _overlaps(b.covered, lo, hi):
            continue
        a.side, b.side = side_a, side_b
        a.covered.append((lo, hi))
        b.covered.append((lo, hi))
        t_end = gap * 1.2
        s0 = (a.s0 + b.s0) / 2 if abs(a.s0 - b.s0) <= t_end else lo
        s1 = (a.s1 + b.s1) / 2 if abs(a.s1 - b.s1) <= t_end else hi
        if s1 - s0 >= opt.min_wall_length_mm:
            pieces.append(_piece(a.theta, (a.d + b.d) / 2, s0, s1, gap, a.layer, False))

    unpaired = 0
    for f in faces:   # traits sans vis-à-vis : murs filaires
        if not f.covered and f.length >= max(opt.min_wall_length_mm, 1000.0):
            pieces.append(_piece(f.theta, f.d, f.s0, f.s1, opt.single_line_thickness_mm, f.layer, True))
            unpaired += 1
    return pieces, unpaired


def _overlaps(covered: list[tuple[float, float]], lo: float, hi: float) -> bool:
    return any(min(hi, h) - max(lo, l) > 50.0 for l, h in covered)


def _piece(theta: float, d: float, s0: float, s1: float, thickness: float, layer: str, single: bool) -> Piece:
    ux, uy = math.cos(theta), math.sin(theta)
    nx, ny = -uy, ux
    return Piece((s0 * ux + d * nx, s0 * uy + d * ny), (s1 * ux + d * nx, s1 * uy + d * ny),
                 thickness, layer, theta, d, s0, s1, single)


# ---------------------------------------------------------------------- ouvertures
def _attach_openings(pieces: list[Piece], doors: list[Seg], windows: list[Seg], opt: DxfOptions) -> dict[str, int]:
    orphans = 0
    for kind, raw, height in (("porte", doors, opt.door_height_mm), ("fenetre", windows, opt.window_height_mm)):
        markers = [m for m in _merge_collinear(raw, opt.collinear_tol_mm) if m.length >= 300]
        used: list[tuple[int, float, float]] = []   # (pièce, s0, s1) déjà ouverts : dédoublonnage
        for m in sorted(markers, key=lambda m: -m.length):
            best: tuple[float, int] | None = None
            for idx, p in enumerate(pieces):
                dtheta = min(abs(m.theta - p.theta), math.pi - abs(m.theta - p.theta))
                if dtheta > math.radians(3.0) or abs(m.d - p.d_axis) > p.thickness / 2 + 30:
                    continue
                inside = min(m.s1, p.s1 + 30) - max(m.s0, p.s0 - 30)
                if inside >= 0.7 * m.length:
                    score = inside - abs(m.d - p.d_axis)
                    if best is None or score > best[0]:
                        best = (score, idx)
            if best is None:
                if not _is_jamb(m, pieces):
                    orphans += 1
                continue
            idx = best[1]
            if any(u[0] == idx and min(u[2], m.s1) - max(u[1], m.s0) >= 0.7 * min(u[2] - u[1], m.length) for u in used):
                continue   # même ouverture dessinée par plusieurs traits
            used.append((idx, m.s0, m.s1))
            p = pieces[idx]
            width = min(m.length, p.length)
            x_start = max(0.0, min(m.s0 - p.s0, p.length - width))
            # Un DXF 2D ne contient pas l'allège : portes au sol, fenêtres à 900 mm (valeur par défaut).
            sill = 0 if kind == "porte" else min(900, max(0, opt.wall_height_mm - height))
            pieces[idx].openings.append(OpeningGeometry(
                kind, int(round(width)), min(height, opt.wall_height_mm), int(round(x_start)), sill))
    return {"orphans": orphans}


def _is_jamb(marker: Face, pieces: list[Piece]) -> bool:
    """Jambage : petit trait PERPENDICULAIRE qui traverse l'épaisseur d'un mur (ferme l'ouverture)."""
    s_mid = (marker.s0 + marker.s1) / 2
    mx = s_mid * math.cos(marker.theta) - marker.d * math.sin(marker.theta)
    my = s_mid * math.sin(marker.theta) + marker.d * math.cos(marker.theta)
    for p in pieces:
        dtheta = min(abs(marker.theta - p.theta), math.pi - abs(marker.theta - p.theta))
        if dtheta < math.radians(80) or marker.length > 1.3 * p.thickness + 60:
            continue
        s_p = mx * math.cos(p.theta) + my * math.sin(p.theta)
        d_p = -mx * math.sin(p.theta) + my * math.cos(p.theta)
        if p.s0 - 60 <= s_p <= p.s1 + 60 and abs(d_p - p.d_axis) <= p.thickness / 2 + 60:
            return True
    return False


def _cap(openings: list[OpeningGeometry], gross_mm2: int) -> list[OpeningGeometry]:
    kept = sorted(openings, key=lambda o: -o.area_mm2)
    while kept and sum(o.area_mm2 for o in kept) > 0.95 * gross_mm2:
        kept.pop(0)
    return kept


def _layer_label(layer: str) -> str:
    return _LABELS.get(layer.upper()) or layer.replace("_", " ").strip().capitalize() or "Mur"
