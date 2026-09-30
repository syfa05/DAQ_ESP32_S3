from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class OpeningOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: str
    largeur_mm: int
    hauteur_mm: int


class WallOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nom: str
    longueur_mm: int
    hauteur_mm: int
    is_corner: bool
    openings: list[OpeningOut] = []


class ProjectOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nom: str
    ville: str
    architecte: str
    status: str
    plan_original_name: str | None
    plan_size: int | None
    plan_sha256: str | None
    created_at: datetime
    validated_at: datetime | None
    completed_at: datetime | None


class ProjectDetail(ProjectOut):
    walls: list[WallOut] = []


class ProjectUpdate(BaseModel):
    nom: str | None = Field(default=None, max_length=200)
    ville: str | None = Field(default=None, max_length=120)
    architecte: str | None = Field(default=None, max_length=120)
