from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints

_Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=120)]
EndKind = Literal["libre", "angle", "butee", "te", "suite"]
OpeningType = Literal["porte", "fenetre", "vitrine", "portail"]


class OpeningEdit(BaseModel):
    type: OpeningType
    largeur_mm: int = Field(ge=100, le=20000)
    hauteur_mm: int = Field(ge=100, le=10000)
    x_mm: int | None = Field(default=None, ge=0, le=100000)      # None = placée automatiquement
    sill_mm: int | None = Field(default=None, ge=0, le=10000)    # None = défaut (porte 0, fenêtre 900)


class WallEdit(BaseModel):
    """Mur complet (remplace l'existant) : les ouvertures fournies remplacent celles du mur."""

    nom: _Text
    longueur_mm: int = Field(ge=300, le=100000)
    hauteur_mm: int = Field(ge=500, le=20000)
    start_kind: EndKind | None = None
    end_kind: EndKind | None = None
    is_corner: bool | None = None            # utilisé seulement si les extrémités ne sont pas précisées
    junctions_mm: list[int] = Field(default_factory=list, max_length=50)
    thickness_mm: int | None = Field(default=None, ge=40, le=1000)
    openings: list[OpeningEdit] = Field(default_factory=list, max_length=100)
