"""Plans 2D (dessus, face, côté) et vue 3D (projection oblique) d'un moule, PARAMÉTRIQUES.

Les formes sont déduites de la catégorie et des dimensions saisies dans la bibliothèque
(L × l × h en mm). Ce sont des représentations indicatives (tenons, alvéoles, pente, etc. suivent
des proportions types) : elles doivent être confirmées avec le fabricant avant usinage.

Le module produit une liste de primitives indépendantes du support ; ``to_svg`` les rend en
SVG (écran) et l'adaptateur PDF les rend avec reportlab.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from html import escape

Pt = tuple[float, float]


@dataclass(frozen=True)
class Prim:
    kind: str                 # poly | circle | line | text
    pts: tuple[Pt, ...] = ()  # poly / line
    cx: float = 0.0
    cy: float = 0.0
    r: float = 0.0
    text: str = ""
    style: str = "outline"    # outline | hidden | fill_top | fill_side | fill_front | dim | thin
    anchor: str = "start"
    size: float = 3.0


# --- Géométrie des vues ------------------------------------------------------------------
def _rect(x0: float, y0: float, x1: float, y1: float) -> list[Pt]:
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def _thick_chevron(length: float, width: float, angle_deg: float) -> list[Pt]:
    """Deux bras de longueur ``length/2`` formant un angle intérieur ``angle_deg`` (ex. 135°)."""
    a = length / 2
    turn = math.radians(180 - angle_deg)        # déviation de la direction
    d1, d2 = (1.0, 0.0), (math.cos(turn), math.sin(turn))
    p0, p1 = (0.0, 0.0), (a, 0.0)
    p2 = (p1[0] + a * d2[0], p1[1] + a * d2[1])
    n1, n2 = (-d1[1], d1[0]), (-d2[1], d2[0])    # normales (côté gauche)
    w = width / 2
    # jonction en onglet : décalage du point de coude le long de la bissectrice
    bis = (n1[0] + n2[0], n1[1] + n2[1])
    k = w / (1 + n1[0] * n2[0] + n1[1] * n2[1]) if (1 + n1[0] * n2[0] + n1[1] * n2[1]) else w
    left = [(p0[0] + n1[0] * w, p0[1] + n1[1] * w), (p1[0] + bis[0] * k, p1[1] + bis[1] * k),
            (p2[0] + n2[0] * w, p2[1] + n2[1] * w)]
    right = [(p2[0] - n2[0] * w, p2[1] - n2[1] * w), (p1[0] - bis[0] * k, p1[1] - bis[1] * k),
             (p0[0] - n1[0] * w, p0[1] - n1[1] * w)]
    pts = left + right
    miny = min(p[1] for p in pts)
    minx = min(p[0] for p in pts)
    return [(x - minx, y - miny) for x, y in pts]


def footprint(cat: str, L: float, l: float) -> list[Pt]:
    """Contour en vue de dessus (x le long du bloc, y en largeur)."""
    if cat == "angle":
        return [(0, 0), (L, 0), (L, l), (l, l), (l, L), (0, L)]
    if cat == "angle_135":
        return _thick_chevron(L, l, 135)
    if cat == "te":
        s = max(L - l, l)
        return [(0, 0), (L, 0), (L, l), (L / 2 + l / 2, l), (L / 2 + l / 2, l + s),
                (L / 2 - l / 2, l + s), (L / 2 - l / 2, l), (0, l)]
    return _rect(0, 0, L, l)


def _studs(cat: str, L: float) -> list[float]:
    if cat in ("demi",):
        return [L / 2]
    if cat in ("standard", "trois_quarts", "angle", "te", "pignon", "acrotere", "appui", "special"):
        return [L / 4, 3 * L / 4] if cat != "trois_quarts" else [L / 3, 2 * L / 3]
    return []


def top_features(cat: str, L: float, l: float, h: float) -> list[Prim]:
    out: list[Prim] = []
    r = max(min(l, h) * 0.16, 1.0)
    if cat in ("creux", "chainage"):
        hole_w = L * (0.28 if cat == "creux" else 0.30)
        hole_d = l * (0.5 if cat == "creux" else 0.55)
        centers = [L / 4, 3 * L / 4] if cat == "creux" else [L / 2]
        for cx in centers:
            out.append(Prim("poly", tuple(_rect(cx - hole_w / 2, l / 2 - hole_d / 2,
                                                cx + hole_w / 2, l / 2 + hole_d / 2))))
    elif cat == "chainage_h":
        t = l * 0.25
        out += [Prim("line", ((0, t), (L, t)), style="hidden"),
                Prim("line", ((0, l - t), (L, l - t)), style="hidden")]
    elif cat == "linteau":
        out += [Prim("line", ((0, l * 0.3), (L, l * 0.3))), Prim("line", ((0, l * 0.7), (L, l * 0.7))),
                Prim("line", ((0, l / 2), (L, l / 2)), style="hidden")]
    elif cat == "appui":
        out.append(Prim("line", ((0, l * 0.85), (L, l * 0.85)), style="hidden"))
    elif cat == "acrotere":
        out.append(Prim("poly", tuple(_rect(0, l * 0.15, L, l * 0.85)), style="hidden"))
    for sx in _studs(cat, L):
        out.append(Prim("circle", cx=sx, cy=l / 2, r=r))
    return out


def front_profile(cat: str, L: float, h: float) -> list[Pt]:
    if cat == "pignon":
        drop = min(h * 0.9, L * math.tan(math.radians(22)))
        return [(0, 0), (L, drop), (L, h), (0, h)]
    return _rect(0, 0, L, h)


def side_profile(cat: str, l: float, h: float) -> list[Pt]:
    if cat == "appui":
        return [(0, 0), (l, h * 0.35), (l, h), (0, h)]
    if cat == "acrotere":
        t = h * 0.3
        return [(0, 0), (l, 0), (l, t), (l * 0.85, t), (l * 0.85, h), (l * 0.15, h),
                (l * 0.15, t), (0, t)]
    return _rect(0, 0, l, h)


def _front_extras(cat: str, L: float, l: float, h: float) -> list[Prim]:
    out: list[Prim] = []
    ts = min(10.0, h * 0.1)
    r = max(min(l, h) * 0.16, 1.0)
    if cat in ("creux", "chainage"):
        hw = L * (0.28 if cat == "creux" else 0.30)
        for cx in ([L / 4, 3 * L / 4] if cat == "creux" else [L / 2]):
            for x in (cx - hw / 2, cx + hw / 2):
                out.append(Prim("line", ((x, 0), (x, h)), style="hidden"))
    for sx in _studs(cat, L):  # tenons au-dessus, alvéoles en dessous (pointillés)
        out.append(Prim("poly", tuple(_rect(sx - r, -ts, sx + r, 0))))
        out.append(Prim("poly", tuple(_rect(sx - r, h - ts, sx + r, h)), style="hidden"))
    return out


def _side_extras(cat: str, L: float, l: float, h: float) -> list[Prim]:
    out: list[Prim] = []
    if cat in ("creux", "chainage"):
        hd = l * (0.5 if cat == "creux" else 0.55)
        for y in (l / 2 - hd / 2, l / 2 + hd / 2):
            out.append(Prim("line", ((y, 0), (y, h)), style="hidden"))
    elif cat == "chainage_h":
        t = l * 0.25
        out.append(Prim("poly", tuple(_rect(t, 0, l - t, h * 0.6)), style="hidden"))
    elif cat == "linteau":
        out.append(Prim("poly", tuple(_rect(l * 0.3, 0, l * 0.7, h * 0.5)), style="hidden"))
        out.append(Prim("circle", cx=l / 2, cy=h * 0.38, r=max(h * 0.05, 1.0), style="hidden"))
    return out


# --- Projection oblique (vue 3D) ---------------------------------------------------------
_A, _B = 0.5 * math.cos(math.radians(30)), 0.5 * math.sin(math.radians(30))


def _proj(p: tuple[float, float, float]) -> Pt:
    x, y, z = p
    return (x + _A * y, -(z + _B * y))  # y SVG vers le bas


def _extrude(cat: str, L: float, l: float, h: float):
    """Solide en faces 3D (liste de (sommets 3D, normale)). Sommets CCW vus de l'extérieur."""
    if cat == "pignon":
        poly, mapper, length, axis = front_profile(cat, L, h), (lambda u, v, w: (u, w, h - v)), l, "y"
    elif cat in ("appui", "acrotere"):
        poly, mapper, length, axis = side_profile(cat, l, h), (lambda u, v, w: (w, u, h - v)), L, "x"
    else:
        poly, mapper, length, axis = footprint(cat, L, l), (lambda u, v, w: (u, v, w)), h, "z"
    # polygone 2D en orientation anti-horaire (repère mathématique)
    def area2(p):
        return sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1]
                   for i in range(len(p)))
    pts = list(poly)
    if area2(pts) < 0:
        pts.reverse()
    faces = []
    n = len(pts)
    for i in range(n):
        (u0, v0), (u1, v1) = pts[i], pts[(i + 1) % n]
        du, dv = u1 - u0, v1 - v0
        norm2 = (dv, -du)
        ln = math.hypot(*norm2) or 1.0
        nrm = tuple(c for c in (mapper(norm2[0] / ln, norm2[1] / ln, 0.0)))
        o = mapper(0, 0, 0)
        nrm = tuple(nrm[k] - o[k] for k in range(3))
        quad = [mapper(u0, v0, 0), mapper(u1, v1, 0), mapper(u1, v1, length), mapper(u0, v0, length)]
        faces.append((quad, nrm))
    for w, sign in ((0.0, -1), (length, 1)):
        o = mapper(0, 0, 0)
        e = mapper(0, 0, 1)
        nrm = tuple(sign * (e[k] - o[k]) for k in range(3))
        faces.append(([mapper(u, v, w) for u, v in pts], nrm))
    return faces


def iso_prims(cat: str, L: float, l: float, h: float) -> list[Prim]:
    toward = (_A, -1.0, _B)  # vecteur vers l'observateur
    depth_dir = (-_A, 1.0, -_B)
    visible = []
    for quad, nrm in _extrude(cat, L, l, h):
        if sum(nrm[k] * toward[k] for k in range(3)) > 1e-9:
            center = tuple(sum(v[k] for v in quad) / len(quad) for k in range(3))
            visible.append((sum(center[k] * depth_dir[k] for k in range(3)), quad, nrm))
    visible.sort(key=lambda t: -t[0])  # du plus loin au plus proche
    out: list[Prim] = []
    for _, quad, nrm in visible:
        style = "fill_top" if nrm[2] > 0.5 else ("fill_front" if nrm[1] < -0.5 else "fill_side")
        out.append(Prim("poly", tuple(_proj(v) for v in quad), style=style))
    if cat not in ("pignon", "appui", "acrotere"):  # détails sur la face supérieure
        for f in top_features(cat, L, l, h):
            if f.kind == "poly":
                out.append(Prim("poly", tuple(_proj((x, y, h)) for x, y in f.pts), style=f.style))
            elif f.kind == "circle":
                ring = tuple(_proj((f.cx + f.r * math.cos(t), f.cy + f.r * math.sin(t), h))
                             for t in [i * math.pi / 12 for i in range(24)])
                out.append(Prim("poly", ring))
            elif f.kind == "line":
                out.append(Prim("line", tuple(_proj((x, y, h)) for x, y in f.pts), style=f.style))
    return out


# --- Mise en page de la fiche -----------------------------------------------------------
SHEET_W, SHEET_H = 297.0, 210.0


def _bounds(prims: list[Prim]) -> tuple[float, float, float, float]:
    xs, ys = [], []
    for p in prims:
        if p.kind in ("poly", "line"):
            xs += [q[0] for q in p.pts]
            ys += [q[1] for q in p.pts]
        elif p.kind == "circle":
            xs += [p.cx - p.r, p.cx + p.r]
            ys += [p.cy - p.r, p.cy + p.r]
    return min(xs), min(ys), max(xs), max(ys)


def _place(prims: list[Prim], box: tuple[float, float, float, float], scale: float,
           label: str) -> tuple[list[Prim], tuple[float, float, float, float]]:
    """Centre les primitives dans ``box`` (x, y, w, h en mm de fiche) à l'échelle donnée."""
    x0, y0, x1, y1 = _bounds(prims)
    bx, by, bw, bh = box
    ox = bx + (bw - (x1 - x0) * scale) / 2 - x0 * scale
    oy = by + 5 + (bh - 5 - (y1 - y0) * scale) / 2 - y0 * scale
    out: list[Prim] = []
    for p in prims:
        if p.kind in ("poly", "line"):
            out.append(Prim(p.kind, tuple((ox + x * scale, oy + y * scale) for x, y in p.pts), style=p.style))
        elif p.kind == "circle":
            out.append(Prim("circle", cx=ox + p.cx * scale, cy=oy + p.cy * scale, r=p.r * scale,
                            style=p.style))
    out.append(Prim("text", cx=bx + 2, cy=by + 4, text=label, size=3.4, style="thin"))
    return out, (ox + x0 * scale, oy + y0 * scale, ox + x1 * scale, oy + y1 * scale)


def _dim(x0: float, y0: float, x1: float, y1: float, text: str, side: int = 1) -> list[Prim]:
    """Cote linéaire horizontale ou verticale, décalée de 6 mm."""
    off = 6.0 * side
    if abs(y1 - y0) < 1e-9:   # horizontale
        ya = y0 + off
        return [Prim("line", ((x0, y0), (x0, ya + 1.5 * side)), style="dim"),
                Prim("line", ((x1, y1), (x1, ya + 1.5 * side)), style="dim"),
                Prim("line", ((x0, ya), (x1, ya)), style="dim"),
                Prim("text", cx=(x0 + x1) / 2, cy=ya + (3.2 if side > 0 else -1.2), text=text,
                     anchor="middle", size=3.0, style="dim")]
    xa = x0 + off
    return [Prim("line", ((x0, y0), (xa + 1.5 * side, y0)), style="dim"),
            Prim("line", ((x1, y1), (xa + 1.5 * side, y1)), style="dim"),
            Prim("line", ((xa, y0), (xa, y1)), style="dim"),
            Prim("text", cx=xa + (1.2 if side > 0 else -1.2), cy=(y0 + y1) / 2, text=text,
                 anchor="start" if side > 0 else "end", size=3.0, style="dim")]


def mold_sheet(code: str, nom: str, produit: str, cat: str, forme: str | None,
               L: int, l: int, h: int, poids_g: int | None) -> list[Prim]:
    """Fiche A4 paysage : en-tête, vues de dessus / face / côté (même échelle) et vue 3D."""
    L_, l_, h_ = float(L), float(l), float(h)
    top = [Prim("poly", tuple(footprint(cat, L_, l_)))] + top_features(cat, L_, l_, h_)
    front = [Prim("poly", tuple(front_profile(cat, L_, h_)))] + _front_extras(cat, L_, l_, h_)
    side = [Prim("poly", tuple(side_profile(cat, l_, h_)))] + _side_extras(cat, L_, l_, h_)
    fx0, fy0, fx1, fy1 = _bounds(top)
    tw, th = fx1 - fx0, fy1 - fy0
    boxes = {"top": (10, 28, 135, 82), "front": (152, 28, 135, 82),
             "side": (10, 116, 135, 82), "iso": (152, 116, 135, 82)}
    # échelle commune aux trois vues orthogonales (marge pour les cotes et tenons)
    need = [(tw, th + 0), (L_, h_ + 12), (l_, h_ + 12)]
    scale = min(min((boxes["top"][2] - 22) / tw, (boxes["top"][3] - 24) / th),
                min((boxes["front"][2] - 22) / L_, (boxes["front"][3] - 30) / (h_ + 12)),
                min((boxes["side"][2] - 22) / l_, (boxes["side"][3] - 30) / (h_ + 12)))
    del need
    prims: list[Prim] = [Prim("poly", tuple(_rect(5, 5, SHEET_W - 5, SHEET_H - 5)), style="thin"),
                         Prim("text", cx=10, cy=14, text=f"{code} — {nom}", size=6.0, style="title"),
                         Prim("text", cx=10, cy=21, size=3.4, style="thin",
                              text=f"{produit} · {forme or cat} · {L} × {l} × {h} mm"
                                   + (f" · {poids_g / 1000:.2f} kg" if poids_g else ""))]
    placed, bb = _place(top, boxes["top"], scale, "DESSUS")
    prims += placed + _dim(bb[0], bb[3], bb[2], bb[3], f"{int(round(tw))}") \
        + _dim(bb[2], bb[1], bb[2], bb[3], f"{int(round(th))}")
    placed, bb = _place(front, boxes["front"], scale, "FACE")
    prims += placed + _dim(bb[0], bb[3], bb[2], bb[3], f"{L}") + _dim(bb[2], bb[1], bb[2], bb[3], f"{h}")
    placed, bb = _place(side, boxes["side"], scale, "CÔTÉ")
    prims += placed + _dim(bb[0], bb[3], bb[2], bb[3], f"{l}") + _dim(bb[2], bb[1], bb[2], bb[3], f"{h}")
    iso = iso_prims(cat, L_, l_, h_)
    ix0, iy0, ix1, iy1 = _bounds(iso)
    iscale = min((boxes["iso"][2] - 12) / (ix1 - ix0), (boxes["iso"][3] - 20) / (iy1 - iy0))
    placed, _ = _place(iso, boxes["iso"], iscale, "VUE 3D (projection oblique)")
    prims += placed
    prims.append(Prim("text", cx=10, cy=SHEET_H - 9, size=2.8, style="thin",
                      text=f"Échelle des vues 2D ≈ 1:{max(1, round(1 / scale))} — cotes en mm — "
                           "représentation paramétrique INDICATIVE, à valider avec le fabricant du moule."))
    return prims


# --- Rendu SVG ---------------------------------------------------------------------------
_SVG_STYLE = {
    "outline": 'fill="none" stroke="#1d1a14" stroke-width="0.5"',
    "hidden": 'fill="none" stroke="#6b645a" stroke-width="0.3" stroke-dasharray="1.6 1.2"',
    "fill_top": 'fill="#efe3c8" stroke="#1d1a14" stroke-width="0.3"',
    "fill_side": 'fill="#c9b48a" stroke="#1d1a14" stroke-width="0.3"',
    "fill_front": 'fill="#dcc9a0" stroke="#1d1a14" stroke-width="0.3"',
    "dim": 'fill="none" stroke="#b0541f" stroke-width="0.25"',
    "thin": 'fill="none" stroke="#1d1a14" stroke-width="0.2"',
}


def to_svg(prims: list[Prim]) -> str:
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SHEET_W:g} {SHEET_H:g}" '
             f'width="{SHEET_W:g}mm" height="{SHEET_H:g}mm" font-family="Helvetica, Arial, sans-serif">',
             f'<rect x="0" y="0" width="{SHEET_W:g}" height="{SHEET_H:g}" fill="#ffffff"/>']
    for p in prims:
        st = _SVG_STYLE.get(p.style, _SVG_STYLE["outline"])
        if p.kind == "poly":
            pts = " ".join(f"{x:.2f},{y:.2f}" for x, y in p.pts)
            parts.append(f'<polygon points="{pts}" {st}/>')
        elif p.kind == "line":
            (x0, y0), (x1, y1) = p.pts[0], p.pts[-1]
            parts.append(f'<line x1="{x0:.2f}" y1="{y0:.2f}" x2="{x1:.2f}" y2="{y1:.2f}" {st}/>')
        elif p.kind == "circle":
            parts.append(f'<circle cx="{p.cx:.2f}" cy="{p.cy:.2f}" r="{p.r:.2f}" {st}/>')
        elif p.kind == "text":
            color = "#b0541f" if p.style == "dim" else "#1d1a14"
            weight = "700" if p.style == "title" else "400"
            parts.append(f'<text x="{p.cx:.2f}" y="{p.cy:.2f}" font-size="{p.size:g}" '
                         f'text-anchor="{p.anchor}" fill="{color}" font-weight="{weight}">'
                         f'{escape(p.text)}</text>')
    parts.append("</svg>")
    return "".join(parts)
