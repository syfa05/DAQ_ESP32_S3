"""Types d'entrée/sortie du calepinage (Python pur).

Ce contrat est indépendant du moteur : un futur optimiseur ou moteur d'IA
recevra les mêmes entrées et devra produire le même ``LayoutResult``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .enums import ShapeCategory
from .errors import Conflict
from .geometry import WallGeometry


class LayoutImpossible(Conflict):
    code = "calepinage_impossible"


@dataclass(frozen=True)
class WallInput:
    id: int
    geometry: WallGeometry

    @property
    def nom(self) -> str:
        return self.geometry.nom


@dataclass(frozen=True)
class BrickShapeInput:
    id: int
    code: str
    nom: str
    produit: str
    categorie: ShapeCategory
    disponible: bool
    # Propriétés issues de la bibliothèque (None = valeur par défaut des règles).
    longueur_mm: int | None = None
    largeur_mm: int | None = None
    hauteur_mm: int | None = None
    cadence_par_heure: int | None = None


@dataclass(frozen=True)
class WallLayout:
    wall_id: int
    quantities: dict[int, int]  # brick_shape_id -> quantité à produire (> 0 uniquement)
    # Détail assise par assise (moteur « assises ») ; vide pour le moteur à règles.
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True)
class LayoutResult:
    engine: str
    walls: tuple[WallLayout, ...]
    warnings: tuple[str, ...] = ()
    estimated_duration_min: int = 0
    parameters: dict = field(default_factory=dict)  # règles utilisées (audit)
    # Information sans moule dédié (ex. demi-blocs à recouper) : {libellé: quantité}
    indicators: dict[str, int] = field(default_factory=dict)
