"""Moteur de calepinage à règles déterministes (phase 1, TEMPORAIRE).

Ce n'est pas une IA : mêmes entrées => mêmes sorties. Par mur :

  surface_nette = longueur × hauteur − Σ ouvertures
  blocs         = ceil(ceil(surface_nette / face_bloc) × (1 + marge))
  angle         = nb_assises × piles d'angle          (mur d'angle seulement)
  linteau       = Σ ceil((largeur_ouverture + 2 × appui) / longueur_bloc)
  corps         = blocs − angle − linteau
  chaînage      = ceil(corps × ratio_chaînage) ; standard = corps − chaînage

Angle, linteau et chaînage sont prélevés sur le total : la somme des blocs
d'un mur reste égale au nombre de blocs calculé.
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

    # -- quantités par catégorie pour un mur ------------------------------
    def _wall_categories(self, wall: WallInput) -> dict[Cat, int]:
        r, g = self.rules, wall.geometry
        face = r.block_length_mm * r.block_height_mm
        raw = ceil(g.net_area_mm2 / face)
        total = _ceil(Decimal(raw) * (1 + r.waste_margin))

        courses = ceil(g.hauteur_mm / r.block_height_mm)
        corner = courses * r.corner_stacks_per_corner_wall if g.is_corner else 0
        lintel = sum(ceil((o.largeur_mm + 2 * r.lintel_bearing_mm) / r.block_length_mm)
                     for o in g.openings)
        body = max(0, total - corner - lintel)
        chainage = _ceil(Decimal(body) * r.chainage_ratio)
        return {
            Cat.ANGLE: corner, Cat.LINTEAU: lintel, Cat.CHAINAGE: chainage,
            Cat.STANDARD: body - chainage,
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

        for wall in walls:
            per_cat = self._wall_categories(wall)
            body_total += per_cat[Cat.STANDARD] + per_cat[Cat.CHAINAGE]
            quantities: dict[int, int] = {}
            for cat, qty in per_cat.items():
                if qty <= 0:
                    continue
                if cat not in resolved:  # avertissement émis une seule fois
                    resolved[cat] = self._resolve(brick_shapes, cat, warnings)
                shape = resolved[cat]
                quantities[shape.id] = quantities.get(shape.id, 0) + qty
            for sid, q in quantities.items():
                totals_by_shape[sid] = totals_by_shape.get(sid, 0) + q
            results.append(WallLayout(wall.id, quantities))

        indicators = {}
        if body_total:
            indicators["demi_blocs_estimes"] = _ceil(Decimal(body_total) * self.rules.half_block_ratio)

        return LayoutResult(
            engine=self.name, walls=tuple(results), warnings=tuple(warnings),
            estimated_duration_min=self._duration_min(totals_by_shape, brick_shapes),
            parameters=self.rules.to_dict(), indicators=indicators,
        )

    def _duration_min(self, totals: dict[int, int],
                      brick_shapes: Sequence[BrickShapeInput]) -> int:
        """Durée de DÉMONSTRATION : Σ quantité / cadence + changements de moule."""
        if not totals:
            return 0
        rates = self.rules.production_rate_per_hour
        category = {s.id: s.categorie.value for s in brick_shapes}
        minutes = Decimal(0)
        for sid, qty in totals.items():
            rate = rates.get(category[sid], rates[Cat.STANDARD.value])
            minutes += Decimal(qty) / rate * 60
        minutes += self.rules.mold_changeover_min * len(totals)
        return _ceil(minutes)
