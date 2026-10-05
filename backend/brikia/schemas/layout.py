from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ShapeQuantity(BaseModel):
    shape_id: int
    code: str
    nom: str
    categorie: str
    quantite: int


class WallLayoutOut(BaseModel):
    wall_id: int
    wall_nom: str
    quantites: list[ShapeQuantity]
    total: int


class BomWallQuantity(BaseModel):
    wall_id: int
    wall_nom: str
    quantite: int


class BomLineOut(BaseModel):
    shape_id: int
    code: str
    nom: str
    produit: str
    categorie: str
    quantite_totale: int
    par_mur: list[BomWallQuantity]


class BomOut(BaseModel):
    lignes: list[BomLineOut]
    total_blocs: int
    duree_estimee_min: int | None
    # Valeur de démonstration : cadences non confirmées.
    duree_indicative: bool = True
    avertissements: list[str]


class LayoutOut(BaseModel):
    id: int
    moteur: str
    created_at: datetime
    parametres: dict
    avertissements: list[str]
    murs: list[WallLayoutOut]
    bom: BomOut
    # Moteur « assises » : détail rang par rang disponible, et indicateurs globaux.
    detail_disponible: bool = False
    indicateurs: dict = {}


class WallCourseShape(BaseModel):
    id: int
    code: str
    nom: str
    categorie: str
    longueur_mm: int | None
    hauteur_mm: int | None


class WallDetailOut(BaseModel):
    wall_id: int
    wall_nom: str
    formes: list[WallCourseShape]
    detail: dict
