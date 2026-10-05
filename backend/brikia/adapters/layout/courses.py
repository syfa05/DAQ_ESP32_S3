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
    # -- gammes de moules (produit + largeur = épaisseur de mur) -----------------------------
    @staticmethod
    def family_key(produit: str, largeur: int | None) -> str:
        return f"{produit}|{largeur if largeur is not None else ''}"

    @staticmethod
    def family_label(key: str) -> str:
        produit, _, largeur = key.partition("|")
        return f"{produit} {largeur} mm" if largeur else produit

    def _families(self, shapes: Sequence[BrickShapeInput]) -> dict[str, list[BrickShapeInput]]:
        fam: dict[str, list[BrickShapeInput]] = {}
        for s in shapes:
            if s.disponible:
                fam.setdefault(self.family_key(s.produit, s.largeur_mm), []).append(s)
        return fam

    def _pick(self, members: Sequence[BrickShapeInput], cat: Cat) -> BrickShapeInput | None:
        return next(iter(sorted((s for s in members if s.categorie == cat), key=lambda s: s.code)), None)

    def _family_molds(self, key: str, members: Sequence[BrickShapeInput], warnings: list[str]) -> dict:
        std = self._pick(members, Cat.STANDARD)
        r = self.rules
        ls = std.longueur_mm or r.block_length_mm
        molds: dict = {"key": key, "label": self.family_label(key), "std": std, "L_std": ls,
                       "H": std.hauteur_mm or r.block_height_mm}
        label = molds["label"]

        def required(cat: Cat, name: str):
            s = self._pick(members, cat)
            if s is None:
                warnings.append(f"Gamme « {label} » : aucun moule « {name} » disponible, "
                                f"« {std.nom} » est utilisé à la place.")
                return std
            return s

        molds["demi"] = self._pick(members, Cat.DEMI)
        molds["tq"] = self._pick(members, Cat.TROIS_QUARTS)
        molds["angle"] = required(Cat.ANGLE, "angle")
        molds["chain"] = self._pick(members, Cat.CHAINAGE)
        molds["chain_h"] = self._pick(members, Cat.CHAINAGE_H)
        molds["linteau"] = required(Cat.LINTEAU, "linteau")
        molds["appui"] = self._pick(members, Cat.APPUI)
        for k in ("demi", "tq", "angle", "chain", "chain_h", "linteau", "appui"):
            m = molds[k]
            default = {"demi": ls // 2, "tq": ls * 3 // 4}.get(k, ls)
            molds["L_" + k] = m.longueur_mm if m is not None and m.longueur_mm else default
        return molds

    def _select_family(self, g, std_keys: list[str], default_key: str, warnings: list[str]
                       ) -> tuple[str, str]:
        """Gamme d'un mur : imposée, sinon la plus proche de son épaisseur. -> (clé, origine)."""
        if g.gamme:
            if g.gamme in std_keys:
                return g.gamme, "manuelle"
            warnings.append(f"Mur « {g.nom} » : gamme imposée « {self.family_label(g.gamme)} » indisponible "
                            "(moule standard absent ou désactivé) : choix automatique.")
        widths = [(k, int(k.partition("|")[2])) for k in std_keys if k.partition("|")[2]]
        if g.thickness_mm is None or not widths:
            return default_key, "defaut"
        pref = self.rules.product_preference

        def rank(item: tuple[str, int]) -> tuple[int, int, str]:
            produit = item[0].partition("|")[0]
            return (abs(item[1] - g.thickness_mm), pref.index(produit) if produit in pref else len(pref), item[0])

        key, width = min(widths, key=rank)
        if abs(width - g.thickness_mm) > self.rules.thickness_tolerance_mm:
            warnings.append(f"Mur « {g.nom} » : épaisseur {g.thickness_mm} mm, aucune gamme de moules à "
                            f"moins de {self.rules.thickness_tolerance_mm} mm ; « {self.family_label(key)} » "
                            f"est utilisée (écart {abs(width - g.thickness_mm)} mm).")
        return key, "epaisseur"

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
    def _openings(self, wall: WallInput, m: dict, lo: int, hi: int, n: int, notes: list[str]) -> list[dict]:
        r, g = self.rules, wall.geometry
        hc, bearing = m["H"], r.lintel_bearing_mm
        raw = []
        for o in g.openings:
            w = min(o.largeur_mm, max(0, hi - lo))
            if w < 100:
                notes.append(f"Ouverture {o.type} de {o.largeur_mm} mm ignorée : mur trop court.")
                continue
            raw.append({"type": o.type, "w": w, "h": o.hauteur_mm, "x": o.x_mm, "sill": o.sill_mm})
        # placement automatique des ouvertures sans position
        unknown = [o for o in raw if o["x"] is None]
        if unknown:
            span = hi - lo
            for i, o in enumerate(unknown):
                o["x"] = int(lo + (i + 1) * span / (len(unknown) + 1) - o["w"] / 2)
                o["estimated"] = True
            notes.append(f"Position de {len(unknown)} ouverture(s) inconnue (plan non lu en détail) : "
                         "placée(s) automatiquement, à vérifier.")
        for o in raw:
            o.setdefault("estimated", False)
            o["x"] = max(lo, min(int(o["x"]), hi - o["w"]))
            if o["sill"] is None:
                o["sill"] = 0 if o["type"] in ("porte", "portail") else r.default_window_sill_mm
                o["sill_estimated"] = True
        raw.sort(key=lambda o: o["x"])
        placed: list[dict] = []
        gap_min = m["L_chain"] if m["chain"] is not None else 0
        for o in raw:  # évite les chevauchements : décale à droite, sinon abandonne
            prev_end = placed[-1]["x"] + placed[-1]["w"] + gap_min if placed else lo
            if o["x"] < prev_end:
                o["x"] = prev_end
            if o["x"] + o["w"] > hi:
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
        # nature des extrémités : angle (pile d'angle), butée / suite (pas de chaînage d'extrémité),
        # libre / te (chaînage vertical d'extrémité) ; inconnue (mur ancien) : « d'angle » = pile au début
        sk, ek = g.start_kind, g.end_kind
        if sk is None and ek is None:
            sk, ek = ("angle" if g.is_corner else "libre"), "libre"
        sk, ek = sk or "libre", ek or "libre"
        la = min(m["L_angle"], length)
        lo = la if sk == "angle" else 0
        hi = length - la if ek == "angle" else length
        if hi - lo < m["L_std"]:                       # mur trop court pour des piles aux deux bouts
            lo, hi = (la if sk == "angle" else 0), length
            if hi - lo < m["L_std"]:
                lo, hi = 0, length
            if lo == 0 and sk == "angle":
                notes.append("Mur trop court : pile d'angle de début non posée.")
        end_pile = length - hi
        ops = self._openings(wall, m, lo, hi, n, notes)

        # colonnes de chaînage vertical (positions fixes sur toute la hauteur)
        columns: list[tuple[int, int]] = []
        if m["chain"] is not None:
            lc = m["L_chain"]
            spans, cur = [], lo
            for o in ops:
                spans.append((cur, o["x"]))
                cur = o["x"] + o["w"]
            spans.append((cur, hi))
            for i, (a, b) in enumerate(spans):
                if b - a < lc:
                    continue
                first, last = i == 0, i == len(spans) - 1
                if (not first) or sk in ("libre", "te"):          # jambage ou bord libre
                    columns.append((a, a + lc))
                if ((not last) or ek in ("libre", "te")) and b - lc >= a + lc:
                    columns.append((b - lc, b))
                inner = ceil((b - a) / r.chain_spacing_max_mm) - 1
                for k in range(inner):
                    cx = int(a + (k + 1) * (b - a) / (inner + 1) - lc / 2)
                    columns.append((cx, cx + lc))
            skipped = 0
            for xj in g.junctions_mm:                           # refends appuyés sur ce mur
                ca = int(xj - lc / 2)
                ca = max(lo, min(ca, hi - lc))
                if any(o["x"] < ca + lc and ca < o["x"] + o["w"] for o in ops):
                    skipped += 1
                    continue
                columns.append((ca, ca + lc))
            if g.junctions_mm:
                notes.append(f"{len(g.junctions_mm) - skipped} jonction(s) en T : chaînage vertical posé à "
                             "l'appui de chaque refend." + (f" {skipped} dans une ouverture : ignorée(s)." if skipped else ""))
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
            if lo and sk == "angle":                         # 2. piles d'angle
                pieces.append(_Piece(0, lo, m["angle"].id))
                occupied.append((0, lo))
            if end_pile:
                pieces.append(_Piece(hi, end_pile, m["angle"].id))
                occupied.append((hi, length))
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
            "ecart_hauteur_mm": residual, "coins": bool(lo or end_pile),
            "extremites": {"debut": sk, "fin": ek}, "jonctions": list(g.junctions_mm),
            "ouvertures": [{"type": o["type"], "x": o["x"], "largeur": o["w"], "hauteur": o["h"],
                            "allege": o["sill"], "c0": o["c0"], "c1": o["c1"],
                            "position_estimee": bool(o["estimated"])} for o in ops],
            "courses": [_encode(pieces) for pieces in courses],
            "pose": {str(k): v for k, v in sorted(exact.items())},
            "coupes": cuts, "reemploi": reused, "chutes_mm": waste, "notes": notes,
            "gamme": m["label"], "gamme_cle": m["key"], "gamme_origine": m.get("origine", "defaut"),
            "epaisseur_mm": g.thickness_mm,
        }
        return exact, detail

    # -- point d'entrée -----------------------------------------------------------------------
    def calculate(self, walls: Sequence[WallInput],
                  brick_shapes: Sequence[BrickShapeInput]) -> LayoutResult:
        warnings: list[str] = []
        families = self._families(brick_shapes)
        std_keys = [k for k, members in families.items()
                    if any(s.categorie == Cat.STANDARD for s in members)]
        default = next(iter(self._candidates(brick_shapes, Cat.STANDARD)), None)
        if default is None:
            raise LayoutImpossible(
                "Calepinage impossible : aucun moule standard n'est disponible. "
                "Activez un moule standard dans la bibliothèque.")
        default_key = self.family_key(default.produit, default.largeur_mm)
        by_id = {s.id: s for s in brick_shapes}
        cache: dict[str, dict] = {}

        def molds_for(key: str) -> dict:
            if key not in cache:
                cache[key] = self._family_molds(key, families[key], warnings)
                cache[key]["by_id"] = by_id
            return cache[key]

        results: list[WallLayout] = []
        totals: dict[int, int] = {}
        cuts = waste = 0
        for wall in walls:
            key, origin = self._select_family(wall.geometry, std_keys, default_key, warnings)
            m = dict(molds_for(key))
            m["origine"] = origin
            exact, detail = self._lay_wall(wall, m, warnings)
            if origin == "epaisseur" and key != default_key:
                detail["notes"].append(f"Gamme « {m['label']} » choisie d'après l'épaisseur du mur "
                                       f"({wall.geometry.thickness_mm} mm).")
            quantities = {sid: _ceil(Decimal(q) * (1 + self.rules.breakage_margin))
                          for sid, q in exact.items() if q > 0}
            detail["a_produire"] = {str(k): v for k, v in sorted(quantities.items())}
            for sid, q in quantities.items():
                totals[sid] = totals.get(sid, 0) + q
            cuts += detail["coupes"]
            waste += detail["chutes_mm"]
            results.append(WallLayout(wall.id, quantities, detail))
        dm = molds_for(default_key)
        params = self._parameters({"length": dm["L_std"], "height": dm["H"],
                                   "lintel_length": dm["L_linteau"]})
        params["moteur"] = "assises"
        params["dimensions_depuis_les_moules"] = True
        used = sorted({r.detail["gamme"] for r in results})
        params["gammes_utilisees"] = used
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
