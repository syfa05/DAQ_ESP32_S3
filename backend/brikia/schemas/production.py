from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class OrderLineOut(BaseModel):
    shape_id: int
    code: str
    nom: str
    cible: int
    produite: int


class OrderOut(BaseModel):
    id: int
    lot_id: str
    project_id: int
    project_nom: str
    status: str
    started_at: datetime
    completed_at: datetime | None
    lignes: list[OrderLineOut]
    total_cible: int
    total_produit: int
    progression_pct: int
    alarmes: list[str]
    simulation: bool = True  # phase 1 : aucune machine réelle
