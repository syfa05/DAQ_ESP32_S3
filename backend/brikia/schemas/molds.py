from __future__ import annotations

from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from ..domain.enums import ShapeCategory

_Dim = Annotated[int, Field(gt=0, le=5000)]
_Poids = Annotated[int, Field(gt=0, le=200_000)]          # grammes
_Cadence = Annotated[int, Field(gt=0, le=100_000)]        # blocs / heure
_Cout = Annotated[Decimal, Field(ge=0, le=Decimal("100000"), max_digits=12, decimal_places=4)]
_Text = Annotated[str, StringConstraints(strip_whitespace=True)]


class ShapeBase(BaseModel):
    nom: _Text = Field(min_length=1, max_length=120)
    produit: _Text = Field(min_length=1, max_length=120)
    role: _Text = Field(default="", max_length=255)
    forme: _Text | None = Field(default=None, max_length=60)
    categorie: ShapeCategory = ShapeCategory.STANDARD
    longueur_mm: _Dim | None = None
    largeur_mm: _Dim | None = None
    hauteur_mm: _Dim | None = None
    poids_g: _Poids | None = None
    cadence_par_heure: _Cadence | None = None
    cout_unitaire_eur: _Cout | None = None
    disponible: bool = True


class ShapeCreate(ShapeBase):
    code: _Text = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_.-]+$")


class ShapeUpdate(BaseModel):
    """Mise à jour partielle ; le code (identifiant stable) n'est pas modifiable."""

    nom: _Text | None = Field(default=None, min_length=1, max_length=120)
    produit: _Text | None = Field(default=None, min_length=1, max_length=120)
    role: _Text | None = Field(default=None, max_length=255)
    forme: _Text | None = Field(default=None, max_length=60)
    categorie: ShapeCategory | None = None
    longueur_mm: _Dim | None = None
    largeur_mm: _Dim | None = None
    hauteur_mm: _Dim | None = None
    poids_g: _Poids | None = None
    cadence_par_heure: _Cadence | None = None
    cout_unitaire_eur: _Cout | None = None
    disponible: bool | None = None


class Availability(BaseModel):
    disponible: bool


class ShapeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    nom: str
    produit: str
    role: str
    forme: str | None
    categorie: str
    longueur_mm: int | None
    largeur_mm: int | None
    hauteur_mm: int | None
    poids_g: int | None
    cadence_par_heure: int | None
    cout_unitaire_eur: Decimal | None  # réservé au chef de projet (masqué pour l'opérateur)
    disponible: bool


class GammeOut(BaseModel):
    """Famille de moules compatibles (même produit, même largeur = épaisseur de mur)."""

    cle: str
    produit: str
    largeur_mm: int | None
    nb_moules: int
    nb_disponibles: int
    categories: list[str]
    manque: list[str]       # fonctions utiles absentes (parmi celles posées par le calepinage)
    complete: bool
