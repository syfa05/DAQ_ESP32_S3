"""Géométrie d'un projet telle que produite par un ``PlanAnalyzer``.

Python pur : c'est le contrat entre l'analyse (simulée aujourd'hui, STEP/IFC
demain) et le calepinage. Dimensions en millimètres entiers ; surfaces en
mm² entiers, converties en m² seulement pour l'affichage.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .errors import ValidationFailed

MM2_PER_M2 = 1_000_000


def mm2_to_m2(value_mm2: int) -> float:
    return round(value_mm2 / MM2_PER_M2, 3)


@dataclass(frozen=True)
class OpeningGeometry:
    type: str
    largeur_mm: int
    hauteur_mm: int

    @property
    def area_mm2(self) -> int:
        return self.largeur_mm * self.hauteur_mm


@dataclass(frozen=True)
class WallGeometry:
    nom: str
    longueur_mm: int
    hauteur_mm: int
    is_corner: bool = False
    openings: tuple[OpeningGeometry, ...] = ()

    @property
    def gross_area_mm2(self) -> int:
        return self.longueur_mm * self.hauteur_mm

    @property
    def openings_area_mm2(self) -> int:
        return sum(o.area_mm2 for o in self.openings)

    @property
    def net_area_mm2(self) -> int:
        """surface_nette = longueur × hauteur − Σ surfaces des ouvertures."""
        return self.gross_area_mm2 - self.openings_area_mm2


@dataclass(frozen=True)
class ProjectGeometry:
    walls: tuple[WallGeometry, ...]
    source: str = "inconnue"  # ex. "simulé", plus tard "step" / "ifc"
    notes: tuple[str, ...] = field(default_factory=tuple)


def validate_geometry(geometry: ProjectGeometry) -> None:
    """Refuse une géométrie incohérente avant qu'elle n'atteigne la base."""
    if not geometry.walls:
        raise ValidationFailed("L'analyse n'a détecté aucun mur.")
    for w in geometry.walls:
        if w.longueur_mm <= 0 or w.hauteur_mm <= 0:
            raise ValidationFailed(f"Dimensions invalides pour le mur « {w.nom} ».")
        for o in w.openings:
            if o.largeur_mm <= 0 or o.hauteur_mm <= 0:
                raise ValidationFailed(f"Ouverture invalide dans le mur « {w.nom} ».")
            if o.largeur_mm > w.longueur_mm or o.hauteur_mm > w.hauteur_mm:
                raise ValidationFailed(
                    f"Une ouverture dépasse les dimensions du mur « {w.nom} »."
                )
        if w.net_area_mm2 <= 0:
            raise ValidationFailed(f"Les ouvertures occupent tout le mur « {w.nom} ».")
