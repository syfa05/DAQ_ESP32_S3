"""Moteur de calepinage à règles déterministes (phase 1, TEMPORAIRE).

Ce n'est pas une IA : mêmes entrées => mêmes sorties. Par mur :

  surface_nette = longueur × hauteur − Σ ouvertures
  blocs         = ceil(ceil(surface_nette / face_bloc) × (1 + marge))
  angle         = nb_assises × piles d'angle          (mur d'angle seulement)
  linteau       = Σ ceil((largeur_ouverture + 2 × appui) / longueur_moule_linteau)
  appui         = Σ ceil(largeur / longueur_moule_appui)   (fenêtres/vitrines ; si moule appui)
  corps         = blocs − angle − linteau − appui
  chaînage      = ceil(corps × ratio_chaînage)
  demi          = ceil(corps × ratio_demi)            (si moule demi ; sinon simple indicateur)
  standard      = corps − chaînage − demi

La face du bloc, le nombre d'assises et les longueurs viennent des DIMENSIONS DES MOULES de la
bibliothèque (moule standard disponible, linteau, appui) ; à défaut, des règles par défaut.
Angle, linteau, appui, demi et chaînage sont prélevés sur le total : la somme des blocs d'un mur
reste égale au nombre de blocs calculé. Les types sans quantité automatique (creux, ¾, angle 135°,
T, chaînage horizontal, pignon, acrotère) sont en bibliothèque pour la saisie manuelle.
"""

from __future__ import annotations

import logging
from decimal import ROUND_CEILING, Decimal
from math import ceil
from typing import Sequence

from ...domain.enums import ShapeCategory as Cat
from ...domain.layout import (
    BrickShapeInput, LayoutImpossible, LayoutResult, WallInput, WallLayout,
)
from .rules_config import LayoutRules

log = logging.getLogger("brikia.layout")


def _ceil(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_CEILING))


class DefaultRuleBasedLayoutEngine:
    name = "default-rule-based (règles temporaires)"

    def __init__(self, rules: LayoutRules | None = None) -> None:
        self.rules = rules or LayoutRules()

    # -- dimensions utiles (issues des moules, sinon règles par défaut) -----
    def _context(self, shapes: Sequence[BrickShapeInput]) -> dict:
        r = self.rules
        std = next(iter(self._candidates(shapes, Cat.STANDARD)), None)

        def same_product(cat: Cat) -> BrickShapeInput | None:
            if std is None:
                return None
            return next((s for s in self._candidates(shapes, cat) if s.produit == std.produit), None)

        lintel = same_product(Cat.LINTEAU) or next(iter(self._candidates(shapes, Cat.LINTEAU)), None)
        return {
            "length": (std.longueur_mm if std and std.longueur_mm else r.block_length_mm),
            "height": (std.hauteur_mm if std and std.hauteur_mm else r.block_height_mm),
            "lintel_length": (lintel.longueur_mm if lintel and lintel.longueur_mm else
                              (std.longueur_mm if std and std.longueur_mm else r.block_length_mm)),
            "demi": same_product(Cat.DEMI),
            "appui": same_product(Cat.APPUI),
        }

    # -- quantités par catégorie pour un mur ------------------------------
    def _wall_categories(self, wall: WallInput, ctx: dict) -> dict[Cat, int]:
        r, g = self.rules, wall.geometry
        face = ctx["length"] * ctx["height"]
        raw = ceil(g.net_area_mm2 / face)
        total = _ceil(Decimal(raw) * (1 + r.waste_margin))

        courses = ceil(g.hauteur_mm / ctx["height"])
        corner = courses * r.corner_stacks_per_corner_wall if g.is_corner else 0
        lintel = sum(ceil((o.largeur_mm + 2 * r.lintel_bearing_mm) / ctx["lintel_length"])
                     for o in g.openings)
        sill = 0
        if ctx["appui"] is not None and ctx["appui"].longueur_mm:
            sill = sum(ceil(o.largeur_mm / ctx["appui"].longueur_mm)
                       for o in g.openings if o.type in ("fenetre", "vitrine"))
        body = max(0, total - corner - lintel - sill)
        chainage = _ceil(Decimal(body) * r.chainage_ratio)
        demi = _ceil(Decimal(body) * r.half_block_ratio) if ctx["demi"] is not None else 0
        standard = max(0, body - chainage - demi)
        return {
            Cat.ANGLE: corner, Cat.LINTEAU: lintel, Cat.CHAINAGE: chainage,
            Cat.DEMI: demi, Cat.APPUI: sill, Cat.STANDARD: standard,
        }

    # -- choix du moule pour une catégorie --------------------------------
    def _candidates(self, shapes: Sequence[BrickShapeInput], cat: Cat) -> list[BrickShapeInput]:
        pref = self.rules.product_preference

        def key(s: BrickShapeInput) -> tuple[int, str]:
            return (pref.index(s.produit) if s.produit in pref else len(pref), s.code)

        return sorted((s for s in shapes if s.disponible and s.categorie == cat), key=key)

    def _resolve(self, shapes: Sequence[BrickShapeInput], cat: Cat,
                 warnings: list[str]) -> BrickShapeInput:
        preferred = self.rules.product_preference[0] if self.rules.product_preference else None
        chosen = next(iter(self._candidates(shapes, cat)), None)
        if chosen is not None:
            if preferred and chosen.produit != preferred:
                warnings.append(
                    f"Aucun moule « {preferred} » disponible pour la catégorie « {cat.value} » : "
                    f"« {chosen.nom} » ({chosen.produit}) est utilisé à la place."
                )
            return chosen
        fallback = next(iter(self._candidates(shapes, Cat.STANDARD)), None)
        if fallback is None:
            raise LayoutImpossible(
                "Calepinage impossible : aucun moule standard n'est disponible. "
                "Activez un moule standard dans la bibliothèque."
            )
        warnings.append(
            f"Aucun moule disponible pour la catégorie « {cat.value} » : "
            f"« {fallback.nom} » est utilisé à la place."
        )
        return fallback

    # -- point d'entrée ----------------------------------------------------
    def calculate(self, walls: Sequence[WallInput],
                  brick_shapes: Sequence[BrickShapeInput]) -> LayoutResult:
        warnings: list[str] = []
        resolved: dict[Cat, BrickShapeInput] = {}
        results: list[WallLayout] = []
        totals_by_shape: dict[int, int] = {}
        body_total = 0
        ctx = self._context(brick_shapes)

        for wall in walls:
            per_cat = self._wall_categories(wall, ctx)
            body_total += per_cat[Cat.STANDARD] + per_cat[Cat.CHAINAGE] + per_cat[Cat.DEMI]
            quantities: dict[int, int] = {}
            for cat, qty in per_cat.items():
                if qty <= 0:
                    continue
                if cat not in resolved:  # avertissement émis une seule fois
                    if cat in (Cat.DEMI, Cat.APPUI):  # moule choisi pour la cohérence du système
                        resolved[cat] = ctx["demi" if cat == Cat.DEMI else "appui"]
                    else:
                        resolved[cat] = self._resolve(brick_shapes, cat, warnings)
                shape = resolved[cat]
                quantities[shape.id] = quantities.get(shape.id, 0) + qty
            for sid, q in quantities.items():
                totals_by_shape[sid] = totals_by_shape.get(sid, 0) + q
            results.append(WallLayout(wall.id, quantities))

        indicators = {}
        if body_total and ctx["demi"] is None:
            indicators["demi_blocs_estimes"] = _ceil(Decimal(body_total) * self.rules.half_block_ratio)

        return LayoutResult(
            engine=self.name, walls=tuple(results), warnings=tuple(warnings),
            estimated_duration_min=self._duration_min(totals_by_shape, brick_shapes),
            parameters=self._parameters(ctx), indicators=indicators,
        )

    def _parameters(self, ctx: dict) -> dict:
        """Règles utilisées + dimensions EFFECTIVES (issues des moules) pour l'audit et l'affichage."""
        params = self.rules.to_dict()
        params["block_length_mm"], params["block_height_mm"] = ctx["length"], ctx["height"]
        params["lintel_length_mm"] = ctx["lintel_length"]
        params["dimensions_depuis_les_moules"] = (
            ctx["length"] != self.rules.block_length_mm or ctx["height"] != self.rules.block_height_mm)
        return params

    def _duration_min(self, totals: dict[int, int],
                      brick_shapes: Sequence[BrickShapeInput]) -> int:
        """Durée de DÉMONSTRATION : Σ quantité / cadence + changements de moule."""
        if not totals:
            return 0
        rates = self.rules.production_rate_per_hour
        category = {s.id: s.categorie.value for s in brick_shapes}
        own_rate = {s.id: s.cadence_par_heure for s in brick_shapes if s.cadence_par_heure}
        minutes = Decimal(0)
        for sid, qty in totals.items():
            rate = (Decimal(own_rate[sid]) if sid in own_rate
                    else rates.get(category[sid], rates[Cat.STANDARD.value]))
            minutes += Decimal(qty) / rate * 60
        minutes += self.rules.mold_changeover_min * len(totals)
        return _ceil(minutes)
