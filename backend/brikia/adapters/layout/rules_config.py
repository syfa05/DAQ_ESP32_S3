"""Règles de calepinage et de cadence — TEMPORAIRES.

/!\\ Ces valeurs viennent du prototype (brique pleine 240×115×90 mm jointée au
mortier) et NE correspondent PAS au système autobloquant mâle-femelle
définitif, à valider avec le fournisseur des moules. Les cadences de
production sont des valeurs de DÉMONSTRATION, pas des mesures.

Tout est regroupé ici et surchargeable (``LayoutRules.from_overrides`` ou le
fichier JSON pointé par ``BRIKIA_LAYOUT_RULES_FILE``). Les ratios sont des
``Decimal`` pour éviter les erreurs d'arrondi flottant (ex. 100 × 1,05).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, fields, replace
from decimal import Decimal
from pathlib import Path

from ...domain.enums import ShapeCategory

# Cadences de démonstration (blocs / heure), par catégorie.
DEMO_RATES_PER_HOUR = {
    ShapeCategory.STANDARD.value: Decimal(240),
    ShapeCategory.ANGLE.value: Decimal(120),
    ShapeCategory.CHAINAGE.value: Decimal(120),
    ShapeCategory.LINTEAU.value: Decimal(120),
}


@dataclass(frozen=True)
class LayoutRules:
    # Dimensions de référence du bloc (mm). La largeur est informative.
    block_length_mm: int = 240
    block_width_mm: int = 115
    block_height_mm: int = 90
    # Marge joints / chutes appliquée au nombre de blocs (5 %).
    waste_margin: Decimal = Decimal("0.05")
    # Part de demi-blocs (6 %) : simple indicateur, aucun moule dédié.
    half_block_ratio: Decimal = Decimal("0.06")
    # Part de blocs creux / de chaînage dans le corps de mur (10 %).
    chainage_ratio: Decimal = Decimal("0.10")
    # Appui du linteau de chaque côté de l'ouverture (mm).
    lintel_bearing_mm: int = 200
    # Piles verticales de blocs d'angle par mur marqué « d'angle ».
    corner_stacks_per_corner_wall: int = 1
    # Produit préféré (ordre) ; un autre produit n'est utilisé qu'avec avertissement.
    product_preference: tuple[str, ...] = ("BTC autobloquante", "Parpaing autobloquant")
    # Cadences DÉMO et temps de changement de moule (min) pour la durée estimée.
    production_rate_per_hour: dict[str, Decimal] = field(
        default_factory=lambda: dict(DEMO_RATES_PER_HOUR))
    mold_changeover_min: int = 30
    # --- Moteur « assises » (calepinage rang par rang) ---
    # Casse / pertes de manutention ajoutées aux quantités posées (les chutes de coupe sont déjà
    # comptées : une coupe consomme un bloc entier).
    breakage_margin: Decimal = Decimal("0.02")
    # Écartement maximal entre deux chaînages verticaux le long d'un mur (mm).
    chain_spacing_max_mm: int = 4000
    # Allège par défaut d'une fenêtre dont la hauteur n'est pas connue (mm).
    default_window_sill_mm: int = 900
    # Longueur minimale d'une pièce coupée (mm, ~1/3 de bloc) : en dessous, on répartit sur deux blocs.
    min_piece_mm: int = 120
    # Réemploi des chutes : le reste d'un bloc coupé sert à la coupe suivante du même mur
    # (si assez long) au lieu de consommer un nouveau bloc.
    reuse_offcuts: bool = True

    def to_dict(self) -> dict:
        """Représentation JSON pour l'audit (stockée avec chaque calepinage)."""
        out: dict = {}
        for f in fields(self):
            v = getattr(self, f.name)
            if isinstance(v, Decimal):
                v = str(v)
            elif isinstance(v, dict):
                v = {k: str(x) for k, x in v.items()}
            elif isinstance(v, tuple):
                v = list(v)
            out[f.name] = v
        out["temporaire"] = True
        return out

    @classmethod
    def from_overrides(cls, overrides: dict) -> LayoutRules:
        base = cls()
        kwargs: dict = {}
        known = {f.name: f for f in fields(cls)}
        for key, value in overrides.items():
            if key not in known:
                raise ValueError(f"Règle de calepinage inconnue : {key}")
            current = getattr(base, key)
            if isinstance(current, Decimal):
                value = Decimal(str(value))
            elif isinstance(current, dict):
                value = {**current, **{k: Decimal(str(v)) for k, v in value.items()}}
            elif isinstance(current, tuple):
                value = tuple(value)
            kwargs[key] = value
        return replace(base, **kwargs)

    @classmethod
    def from_file(cls, path: Path) -> LayoutRules:
        return cls.from_overrides(json.loads(path.read_text(encoding="utf-8")))
