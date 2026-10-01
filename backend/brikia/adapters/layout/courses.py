"""Moteur de calepinage ASSISE PAR ASSISE (rang par rang), déterministe.

Pour chaque mur on pose réellement les blocs, rang après rang, du bas vers le haut :

* assises = round(hauteur / hauteur du bloc) ; les dimensions viennent des moules (bibliothèque) ;
* **ouvertures** : vides sur les assises concernées (position et allège réelles du plan quand elles
  existent, sinon l'ouverture est placée automatiquement et la note le dit), **linteau** sur
  l'assise au-dessus (appui de chaque côté), **appui** de fenêtre sur l'assise sous le vide ;
* **angle** : pile de blocs d'angle au début d'un mur « d'angle » ;
* **chaînages verticaux** : aux extrémités libres, de chaque côté des ouvertures et au plus tous les
  ``chain_spacing_max_mm`` ; **ceinture** (chaînage horizontal) sur la dernière assise ;
* **appareillage à joints décalés** : une assise sur deux commence par un demi-bloc à partir de chaque
  élément fixe ; la fin de chaque tronçon est fermée par un demi, un ¾ ou une pièce **coupée**.
  Une coupe consomme un bloc entier du moule d'origine.

Chaque assise est un pavage exact de la longueur du mur (vérifié avant de rendre le résultat).
Les quantités à produire = pièces posées + marge de casse (``breakage_margin``, 2 % par défaut).
"""

from __future__ import annotations

import logging
from collections import Counter
from decimal import ROUND_CEILING, Decimal
from math import ceil
from typing import Sequence

from ...domain.enums import ShapeCategory as Cat
from ...domain.errors import ValidationFailed
from ...domain.layout import (
    BrickShapeInput, LayoutImpossible, LayoutResult, WallInput, WallLayout,
)
from .rule_based import DefaultRuleBasedLayoutEngine
from .rules_config import LayoutRules

log = logging.getLogger("brikia.layout")

VOID = 0  # « forme » des vides d'ouverture dans le détail


def _ceil(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


class _Piece:
    __slots__ = ("x", "length", "shape", "cut")

    def __init__(self, x: int, length: int, shape: int, cut: bool = False) -> None:
        self.x, self.length, self.shape, self.cut = x, length, shape, cut


class CourseLayoutEngine(DefaultRuleBasedLayoutEngine):
    name = "assises (calepinage rang par rang)"

    def __init__(self, rules: LayoutRules | None = None) -> None:
        super().__init__(rules)

    # -- moules ---------------------------------------------------------------------------------
    def _pick(self, shapes: Sequence[BrickShapeInput], cat: Cat, product: str | None
              ) -> BrickShapeInput | None:
        cands = self._candidates(shapes, cat)
        same = [s for s in cands if s.produit == product]
        return (same or cands or [None])[0] if product else (cands or [None])[0]

    def _molds(self, shapes: Sequence[BrickShapeInput], warnings: list[str]) -> dict:
        std = self._pick(shapes, Cat.STANDARD, None)
        if std is None:
            raise LayoutImpossible(
                "Calepinage impossible : aucun moule standard n'est disponible. "
                "Activez un moule standard dans la bibliothèque.")
        r = self.rules
        ls = std.longueur_mm or r.block_length_mm
        molds: dict = {"std": std, "L_std": ls, "H": std.hauteur_mm or r.block_height_mm}

        def opt(cat: Cat, label: str, required: bool = False):
            s = self._pick(shapes, cat, std.produit)
            if s is not None and s.produit != std.produit:
                warnings.append(f"Moule « {label} » : aucun moule {std.produit} disponible, "
                                f"« {s.nom} » ({s.produit}) est utilisé à la place.")
            if s is None and required:
                warnings.append(f"Aucun moule « {label} » disponible : « {std.nom} » est utilisé à la place.")
                return std
            return s

        molds["demi"] = self._pick(shapes, Cat.DEMI, std.produit)
        molds["tq"] = self._pick(shapes, Cat.TROIS_QUARTS, std.produit)
        molds["angle"] = opt(Cat.ANGLE, "angle", required=True)
        molds["chain"] = self._pick(shapes, Cat.CHAINAGE, std.produit)
        molds["chain_h"] = self._pick(shapes, Cat.CHAINAGE_H, std.produit)
        molds["linteau"] = opt(Cat.LINTEAU, "linteau", required=True)
        molds["appui"] = self._pick(shapes, Cat.APPUI, std.produit)
        for key in ("demi", "tq", "angle", "chain", "chain_h", "linteau", "appui"):
            m = molds[key]
            default = {"demi": ls // 2, "tq": ls * 3 // 4}.get(key, ls)
            molds["L_" + key] = (m.longueur_mm if m is not None and m.longueur_mm else default)
        return molds

    # -- remplissage d'un tronçon libre -------------------------------------------------------
    def _fill(self, a: int, b: int, course: int, m: dict, mold_key: str = "std") -> list[_Piece]:
        """Pose des blocs dans [a, b] avec joints décalés (assise impaire : demi en tête)."""
        r = self.rules
        full = m["std"] if mold_key == "std" else m[mold_key]
        lf = m["L_std"] if mold_key == "std" else m["L_" + mold_key]
        demi, ld = m["demi"], m["L_demi"]
        tq, ltq = m["tq"], m["L_tq"]
        out: list[_Piece] = []
        pos, end = a, b
        if end - pos <= 0:
            return out
        if course % 2 == 1 and mold_key == "std" and end - pos > ld:
            if demi is not None:
                out.append(_Piece(pos, ld, demi.id))
            else:
                out.append(_Piece(pos, ld, full.id, cut=True))
            pos += ld
        while end - pos >= lf:
            out.append(_Piece(pos, lf, full.id))
            pos += lf
        rest = end - pos
        if rest <= 0:
            return out
        if 0 < rest < r.min_piece_mm and out and not out[-1].cut and out[-1].shape == full.id:
            last = out.pop()  # évite une miette : on répartit sur deux blocs coupés
            total = last.length + rest
            h1 = total // 2
            out.append(_Piece(last.x, h1, full.id, cut=True))
            out.append(_Piece(last.x + h1, total - h1, full.id, cut=True))
            return out
        if mold_key == "std":
            if rest == ld and demi is not None:
                out.append(_Piece(pos, rest, demi.id))
            elif rest == ltq and tq is not None:
                out.append(_Piece(pos, rest, tq.id))
            elif rest <= ld and demi is not None:
                out.append(_Piece(pos, rest, demi.id, cut=True))
            elif rest <= ltq and tq is not None:
                out.append(_Piece(pos, rest, tq.id, cut=True))
            else:
                out.append(_Piece(pos, rest, full.id, cut=True))
        else:
            out.append(_Piece(pos, rest, full.id, cut=rest != lf))
        return out

    # -- ouvertures --------------------------------------------------------------------------
    def _openings(self, wall: WallInput, m: dict, corner_len: int, n: int, notes: list[str]) -> list[dict]:
        r, g = self.rules, wall.geometry
        hc, bearing = m["H"], r.lintel_bearing_mm
        length = g.longueur_mm
        raw = []
        for o in g.openings:
            w = min(o.largeur_mm, max(0, length - corner_len))
            if w < 100:
                notes.append(f"Ouverture {o.type} de {o.largeur_mm} mm ignorée : mur trop court.")
                continue
            raw.append({"type": o.type, "w": w, "h": o.hauteur_mm, "x": o.x_mm, "sill": o.sill_mm})
        # placement automatique des ouvertures sans position
        unknown = [o for o in raw if o["x"] is None]
        if unknown:
            span = length - corner_len
            for i, o in enumerate(unknown):
                o["x"] = int(corner_len + (i + 1) * span / (len(unknown) + 1) - o["w"] / 2)
                o["estimated"] = True
            notes.append(f"Position de {len(unknown)} ouverture(s) inconnue (plan non lu en détail) : "
                         "placée(s) automatiquement, à vérifier.")
        for o in raw:
            o.setdefault("estimated", False)
            o["x"] = max(corner_len, min(int(o["x"]), length - o["w"]))
            if o["sill"] is None:
                o["sill"] = 0 if o["type"] in ("porte", "portail") else r.default_window_sill_mm
                o["sill_estimated"] = True
        raw.sort(key=lambda o: o["x"])
        placed: list[dict] = []
        gap_min = m["L_chain"] if m["chain"] is not None else 0
        for o in raw:  # évite les chevauchements : décale à droite, sinon abandonne
            prev_end = placed[-1]["x"] + placed[-1]["w"] + gap_min if placed else corner_len
            if o["x"] < prev_end:
                o["x"] = prev_end
            if o["x"] + o["w"] > length:
                notes.append(f"Ouverture {o['type']} de {o['w']} mm non posable (chevauchement) : ignorée.")
                continue
            placed.append(o)
        out = []
        for o in placed:
            c0 = max(0, o["sill"] // hc)
            c1 = max(c0 + 1, ceil((o["sill"] + o["h"]) / hc))
            if c1 > n - 1:
                c1 = n - 1
                if c1 <= c0:
                    notes.append(f"Ouverture {o['type']} : mur trop bas pour poser un linteau : ignorée.")
                    continue
                notes.append(f"Ouverture {o['type']} : hauteur réduite pour garder une assise de linteau.")
            if o["sill"] % hc or o["h"] % hc:
                o["module"] = True
            o["c0"], o["c1"] = c0, c1
            out.append(o)
        if any(o.get("module") for o in out):
            notes.append(f"Hauteurs d'ouverture ajustées au module de {hc} mm (assise entière).")
        return out

    # -- un mur -----------------------------------------------------------------------------------
    def _lay_wall(self, wall: WallInput, m: dict, notes_global: list[str]) -> tuple[Counter, dict]:
        r, g = self.rules, wall.geometry
        length, height, hc = g.longueur_mm, g.hauteur_mm, m["H"]
        notes: list[str] = []
        n = max(1, round(height / hc))
        residual = height - n * hc
        if residual:
            notes.append(f"Hauteur {height} mm : {n} assises de {hc} mm = {n * hc} mm "
                         f"(écart {residual:+d} mm à rattraper à la pose).")
        corner_len = min(m["L_angle"], length) if g.is_corner else 0
        ops = self._openings(wall, m, corner_len, n, notes)

        # colonnes de chaînage vertical (positions fixes sur toute la hauteur)
        columns: list[tuple[int, int]] = []
        if m["chain"] is not None:
            lc = m["L_chain"]
            spans, cur = [], corner_len
            for o in ops:
                spans.append((cur, o["x"]))
                cur = o["x"] + o["w"]
            spans.append((cur, length))
            for i, (a, b) in enumerate(spans):
                if b - a < lc:
                    continue
                if a > corner_len or i > 0 or not g.is_corner:   # bord libre ou jambage
                    columns.append((a, a + lc))
                if b - lc >= a + lc:
                    columns.append((b - lc, b))
                inner = ceil((b - a) / r.chain_spacing_max_mm) - 1
                for k in range(inner):
                    cx = int(a + (k + 1) * (b - a) / (inner + 1) - lc / 2)
                    columns.append((cx, cx + lc))
        elif ops or length > r.chain_spacing_max_mm:
            notes.append("Aucun moule de chaînage vertical disponible : murs non chaînés.")

        courses: list[list[_Piece]] = []
        for c in range(n):
            occupied: list[tuple[int, int]] = []
            pieces: list[_Piece] = []

            def free(a: int, b: int) -> list[tuple[int, int]]:
                parts, cur = [], a
                for oa, ob in sorted(occupied):
                    if ob <= cur or oa >= b:
                        continue
                    if oa > cur:
                        parts.append((cur, oa))
                    cur = max(cur, ob)
                if cur < b:
                    parts.append((cur, b))
                return parts

            def take(a: int, b: int, kind: str, mold_key: str | None) -> None:
                a, b = max(0, a), min(length, b)
                for fa, fb in free(a, b):
                    if kind == "void":
                        pieces.append(_Piece(fa, fb - fa, VOID))
                    else:
                        pieces.extend(self._fill(fa, fb, c, m, mold_key or "std"))
                    occupied.append((fa, fb))

            for o in ops:                                   # 1. vides
                if o["c0"] <= c < o["c1"]:
                    take(o["x"], o["x"] + o["w"], "void", None)
            if corner_len:                                   # 2. pile d'angle
                a = _Piece(0, corner_len, m["angle"].id)
                if not any(p.x < corner_len and p.shape == VOID for p in pieces):
                    pieces.append(a)
                    occupied.append((0, corner_len))
            belt = c == n - 1 and m["chain_h"] is not None   # ceinture : couvre tout le rang
            for ca, cb in ([] if belt else columns):         # 3. chaînage vertical
                take(ca, cb, "chain", "chain")
            for o in ops:                                    # 4. linteaux (sur les jambages chaînés)
                if c == o["c1"]:
                    take(o["x"] - r.lintel_bearing_mm, o["x"] + o["w"] + r.lintel_bearing_mm,
                         "lintel", "linteau")
            if m["appui"] is not None:                       # 5. appuis de fenêtre
                for o in ops:
                    if o["type"] in ("fenetre", "vitrine") and o["c0"] >= 1 and c == o["c0"] - 1:
                        take(o["x"], o["x"] + o["w"], "appui", "appui")
            top_key = "chain_h" if belt else None
            for fa, fb in free(0, length):                   # 6. appareillage
                pieces.extend(self._fill(fa, fb, c, m, top_key or "std"))
            pieces.sort(key=lambda p: p.x)
            cur = 0
            for p in pieces:                                 # contrôle : pavage exact de la longueur
                if p.x != cur or p.length <= 0:
                    raise ValidationFailed(f"Calepinage incohérent (mur « {g.nom} », assise {c + 1}).")
                cur += p.length
            if cur != length:
                raise ValidationFailed(f"Calepinage incohérent (mur « {g.nom} », assise {c + 1}).")
            courses.append(pieces)

        exact: Counter = Counter()
        cuts = reused = waste = 0
        by_id = m["by_id"]
        offcuts: dict[int, list[int]] = {}      # chutes disponibles par moule (longueurs en mm)
        for pieces in courses:                   # du bas vers le haut, de gauche à droite
            for p in pieces:
                if p.shape == VOID:
                    continue
                if not p.cut:
                    exact[p.shape] += 1
                    continue
                cuts += 1
                pool = offcuts.setdefault(p.shape, [])
                fit = min((o for o in pool if o >= p.length), default=None) if r.reuse_offcuts else None
                if fit is not None:              # réemploi d'une chute
                    pool.remove(fit)
                    reused += 1
                    left = fit - p.length
                else:                            # nouveau bloc consommé
                    exact[p.shape] += 1
                    left = (by_id[p.shape].longueur_mm or m["L_std"]) - p.length
                if left >= r.min_piece_mm:
                    pool.append(left)
                else:
                    waste += max(0, left)
        waste += sum(sum(v) for v in offcuts.values())   # chutes finales non réemployées
        detail = {
            "longueur_mm": length, "hauteur_mm": height, "assises": n, "hauteur_assise_mm": hc,
            "ecart_hauteur_mm": residual, "coins": bool(corner_len),
            "ouvertures": [{"type": o["type"], "x": o["x"], "largeur": o["w"], "hauteur": o["h"],
                            "allege": o["sill"], "c0": o["c0"], "c1": o["c1"],
                            "position_estimee": bool(o["estimated"])} for o in ops],
            "courses": [_encode(pieces) for pieces in courses],
            "pose": {str(k): v for k, v in sorted(exact.items())},
            "coupes": cuts, "reemploi": reused, "chutes_mm": waste, "notes": notes,
        }
        return exact, detail

    # -- point d'entrée -----------------------------------------------------------------------
    def calculate(self, walls: Sequence[WallInput],
                  brick_shapes: Sequence[BrickShapeInput]) -> LayoutResult:
        warnings: list[str] = []
        m = self._molds(brick_shapes, warnings)
        m["by_id"] = {s.id: s for s in brick_shapes}
        results: list[WallLayout] = []
        totals: dict[int, int] = {}
        cuts = waste = 0
        for wall in walls:
            exact, detail = self._lay_wall(wall, m, warnings)
            quantities = {sid: _ceil(Decimal(q) * (1 + self.rules.breakage_margin))
                          for sid, q in exact.items() if q > 0}
            detail["a_produire"] = {str(k): v for k, v in sorted(quantities.items())}
            for sid, q in quantities.items():
                totals[sid] = totals.get(sid, 0) + q
            cuts += detail["coupes"]
            waste += detail["chutes_mm"]
            results.append(WallLayout(wall.id, quantities, detail))
        ctx = {"length": m["L_std"], "height": m["H"], "lintel_length": m["L_linteau"]}
        params = self._parameters(ctx)
        params["moteur"] = "assises"
        params["dimensions_depuis_les_moules"] = True
        indicators = {"pieces_coupees": cuts, "chutes_totales_m": round(waste / 1000)}
        return LayoutResult(
            engine=self.name, walls=tuple(results), warnings=tuple(dict.fromkeys(warnings)),
            estimated_duration_min=self._duration_min(totals, brick_shapes),
            parameters=params, indicators=indicators,
        )


def _encode(pieces: list[_Piece]) -> list[list[int]]:
    """Run-length : [x, forme (0 = vide), longueur d'une pièce, nombre, coupée]."""
    runs: list[list[int]] = []
    for p in pieces:
        if runs and runs[-1][1] == p.shape and runs[-1][2] == p.length and runs[-1][4] == int(p.cut) \
                and runs[-1][0] + runs[-1][2] * runs[-1][3] == p.x and p.shape != VOID:
            runs[-1][3] += 1
        else:
            runs.append([p.x, p.shape, p.length, 1, int(p.cut)])
    return runs
