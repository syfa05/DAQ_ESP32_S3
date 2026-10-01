"""Modèle relationnel de BrikIA.

Choix notables :
- dimensions en millimètres (entiers) : pas d'erreurs d'arrondi flottant,
  calculs déterministes ;
- énumérations stockées en texte + CHECK (portable SQLite/PostgreSQL) ;
- quantités de production en table dédiée plutôt qu'en JSON : contraintes
  d'intégrité (produit <= cible), requêtes de suivi simples.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    Integer,
    String,
    text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..domain.enums import OrderStatus, ProjectStatus, Role, ShapeCategory, values

from .base import Base, DecimalText, UTCDateTime, utcnow


def _in(column: str, enum_cls) -> str:  # noqa: ANN001
    return f"{column} IN ({', '.join(repr(v) for v in values(enum_cls))})"


_ACTIVE_ORDER = text(f"status = '{OrderStatus.EN_COURS.value}'")


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint(_in("role", Role), name="role"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(120))
    login: Mapped[str] = mapped_column(String(64), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))
    actif: Mapped[bool] = mapped_column(Boolean, default=True)


class UserSession(Base):
    """Session serveur ; seul le hash du jeton est stocké."""

    __tablename__ = "user_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    csrf_token: Mapped[str] = mapped_column(String(64))
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime)

    user: Mapped[User] = relationship()


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (CheckConstraint(_in("status", ProjectStatus), name="status"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nom: Mapped[str] = mapped_column(String(200))
    ville: Mapped[str] = mapped_column(String(120), default="")
    architecte: Mapped[str] = mapped_column(String(120), default="")
    plan_path: Mapped[str | None] = mapped_column(String(500))
    plan_original_name: Mapped[str | None] = mapped_column(String(255))
    plan_size: Mapped[int | None] = mapped_column(Integer)
    plan_sha256: Mapped[str | None] = mapped_column(String(64))
    # Provenance de la géométrie : simulated | ifc | step | dxf, et avertissements.
    analysis_source: Mapped[str | None] = mapped_column(String(20))
    analysis_notes: Mapped[list | None] = mapped_column(JSON)
    # Devis figé à la validation (les changements de tarifs ne modifient plus un projet validé).
    devis: Mapped[dict | None] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(
        String(20), default=ProjectStatus.A_ANALYSER.value, index=True
    )
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    validated_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    walls: Mapped[list[Wall]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="Wall.id"
    )
    layout_runs: Mapped[list[LayoutRun]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="LayoutRun.id"
    )
    orders: Mapped[list[ProductionOrder]] = relationship(
        back_populates="project", order_by="ProductionOrder.id"
    )


class Wall(Base):
    __tablename__ = "walls"
    __table_args__ = (
        CheckConstraint("longueur_mm > 0", name="longueur_pos"),
        CheckConstraint("hauteur_mm > 0", name="hauteur_pos"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    nom: Mapped[str] = mapped_column(String(120))
    longueur_mm: Mapped[int] = mapped_column(Integer)
    hauteur_mm: Mapped[int] = mapped_column(Integer)
    is_corner: Mapped[bool] = mapped_column(Boolean, default=False)

    project: Mapped[Project] = relationship(back_populates="walls")
    openings: Mapped[list[Opening]] = relationship(
        back_populates="wall", cascade="all, delete-orphan", order_by="Opening.id"
    )


class Opening(Base):
    __tablename__ = "openings"
    __table_args__ = (
        CheckConstraint("largeur_mm > 0", name="largeur_pos"),
        CheckConstraint("hauteur_mm > 0", name="hauteur_pos"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    wall_id: Mapped[int] = mapped_column(
        ForeignKey("walls.id", ondelete="CASCADE"), index=True
    )
    type: Mapped[str] = mapped_column(String(30))  # porte, fenetre, ...
    largeur_mm: Mapped[int] = mapped_column(Integer)
    hauteur_mm: Mapped[int] = mapped_column(Integer)

    wall: Mapped[Wall] = relationship(back_populates="openings")


class BrickShape(Base):
    """Bibliothèque de moules."""

    __tablename__ = "brick_shapes"
    __table_args__ = (CheckConstraint(_in("categorie", ShapeCategory), name="categorie"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    categorie: Mapped[str] = mapped_column(
        String(20), default=ShapeCategory.STANDARD.value,
        server_default=ShapeCategory.STANDARD.value,
    )
    nom: Mapped[str] = mapped_column(String(120))
    produit: Mapped[str] = mapped_column(String(120))
    role: Mapped[str] = mapped_column(String(255), default="")
    forme: Mapped[str | None] = mapped_column(String(60))
    # Dimensions optionnelles tant qu'elles ne sont pas confirmées.
    longueur_mm: Mapped[int | None] = mapped_column(Integer)
    largeur_mm: Mapped[int | None] = mapped_column(Integer)
    hauteur_mm: Mapped[int | None] = mapped_column(Integer)
    # Poids à l'unité (grammes), cadence de fabrication (blocs/heure) et coût de revient
    # unitaire ESTIMÉ (EUR) : modifiables à tout moment (page Tarifs / Moules).
    poids_g: Mapped[int | None] = mapped_column(Integer)
    cadence_par_heure: Mapped[int | None] = mapped_column(Integer)
    cout_unitaire_eur: Mapped[Decimal | None] = mapped_column(DecimalText)
    disponible: Mapped[bool] = mapped_column(Boolean, default=True)


class LayoutRun(Base):
    """Un calcul de calepinage ; refaire le calepinage remplace le précédent."""

    __tablename__ = "layout_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    engine: Mapped[str] = mapped_column(String(80))
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)  # audit
    warnings: Mapped[list] = mapped_column(JSON, default=list)
    estimated_duration_min: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)

    project: Mapped[Project] = relationship(back_populates="layout_runs")
    assignments: Mapped[list[WallAssignment]] = relationship(
        back_populates="layout_run", cascade="all, delete-orphan"
    )


class WallAssignment(Base):
    """Quantité d'une forme de bloc pour un mur, pour un calepinage donné."""

    __tablename__ = "wall_assignments"
    __table_args__ = (
        UniqueConstraint("layout_run_id", "wall_id", "brick_shape_id"),
        CheckConstraint("quantity >= 0", name="quantity_nonneg"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    layout_run_id: Mapped[int] = mapped_column(
        ForeignKey("layout_runs.id", ondelete="CASCADE"), index=True
    )
    wall_id: Mapped[int] = mapped_column(
        ForeignKey("walls.id", ondelete="CASCADE"), index=True
    )
    brick_shape_id: Mapped[int] = mapped_column(
        ForeignKey("brick_shapes.id", ondelete="RESTRICT"), index=True
    )
    quantity: Mapped[int] = mapped_column(Integer)

    layout_run: Mapped[LayoutRun] = relationship(back_populates="assignments")
    wall: Mapped[Wall] = relationship()
    brick_shape: Mapped[BrickShape] = relationship()


class ProductionOrder(Base):
    __tablename__ = "production_orders"
    __table_args__ = (
        CheckConstraint(_in("status", OrderStatus), name="status"),
        # Garde-fou d'idempotence : au plus un ordre en cours par projet,
        # garanti par la base même en cas de double requête concurrente.
        Index(
            "uq_production_orders_active_project",
            "project_id",
            unique=True,
            sqlite_where=_ACTIVE_ORDER,
            postgresql_where=_ACTIVE_ORDER,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Identifiant de lot : sera transmis tel quel à la future passerelle.
    lot_id: Mapped[str] = mapped_column(
        String(36), unique=True, default=lambda: str(uuid.uuid4())
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="RESTRICT"), index=True
    )
    status: Mapped[str] = mapped_column(
        String(20), default=OrderStatus.EN_COURS.value
    )
    created_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    message: Mapped[str | None] = mapped_column(String(255))  # alarme / erreur de la ligne

    project: Mapped[Project] = relationship(back_populates="orders")
    lines: Mapped[list[ProductionOrderLine]] = relationship(
        back_populates="order", cascade="all, delete-orphan", order_by="ProductionOrderLine.id"
    )


class ProductionOrderLine(Base):
    __tablename__ = "production_order_lines"
    __table_args__ = (
        UniqueConstraint("order_id", "brick_shape_id"),
        CheckConstraint("target >= 0", name="target_nonneg"),
        CheckConstraint("produced >= 0 AND produced <= target", name="produced_range"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(
        ForeignKey("production_orders.id", ondelete="CASCADE"), index=True
    )
    brick_shape_id: Mapped[int] = mapped_column(
        ForeignKey("brick_shapes.id", ondelete="RESTRICT")
    )
    target: Mapped[int] = mapped_column(Integer)
    produced: Mapped[int] = mapped_column(Integer, default=0)

    order: Mapped[ProductionOrder] = relationship(back_populates="lines")
    brick_shape: Mapped[BrickShape] = relationship()


class ActionLog(Base):
    """Journal métier de traçabilité (distinct des logs techniques)."""

    __tablename__ = "action_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    target_type: Mapped[str] = mapped_column(String(40))
    target_id: Mapped[int | None] = mapped_column(Integer)
    details: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, index=True)


__all__ = [
    "ActionLog", "BrickShape", "LayoutRun", "Opening", "ProductionOrder",
    "ProductionOrderLine", "Project", "User", "UserSession", "Wall", "WallAssignment",
]


class PricingSettings(Base):
    """Paramètres de chiffrage : une seule ligne (id = 1). Valeurs ESTIMATIVES."""

    __tablename__ = "pricing_settings"
    __table_args__ = (CheckConstraint("id = 1", name="singleton"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    taux_fcfa_par_eur: Mapped[Decimal] = mapped_column(DecimalText)
    marge_pct: Mapped[Decimal] = mapped_column(DecimalText)
    tva_pct: Mapped[Decimal] = mapped_column(DecimalText)
    frais_fixes_eur: Mapped[Decimal] = mapped_column(DecimalText)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow)
    updated_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
