"""Bibliothèque de moules."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..domain.errors import Conflict, NotFound, ValidationFailed
from ..models import BrickShape, ProductionOrderLine, WallAssignment
from ..schemas.molds import ShapeCreate, ShapeUpdate

log = logging.getLogger("brikia.molds")


def list_shapes(db: Session) -> list[BrickShape]:
    return list(db.scalars(select(BrickShape).order_by(BrickShape.id)))


def get_shape(db: Session, shape_id: int) -> BrickShape:
    shape = db.get(BrickShape, shape_id)
    if shape is None:
        raise NotFound("Moule introuvable.")
    return shape


def create_shape(db: Session, data: ShapeCreate) -> BrickShape:
    code = data.code.upper()  # unicité insensible à la casse
    if db.scalar(select(BrickShape.id).where(BrickShape.code == code)):
        raise Conflict(f"Le code de moule « {code} » existe déjà.")
    shape = BrickShape(**{**data.model_dump(), "code": code,
                          "categorie": data.categorie.value})
    db.add(shape)
    try:
        db.commit()
    except IntegrityError as exc:  # course entre le contrôle et l'insertion
        db.rollback()
        raise Conflict(f"Le code de moule « {code} » existe déjà.") from exc
    log.info("Moule %s créé", code)
    return shape


def update_shape(db: Session, shape: BrickShape, data: ShapeUpdate) -> BrickShape:
    changes = data.model_dump(exclude_unset=True)
    for field in ("nom", "produit", "disponible", "categorie"):
        if field in changes and changes[field] is None:
            raise ValidationFailed(f"Le champ « {field} » ne peut pas être vide.")
    if "categorie" in changes:
        changes["categorie"] = changes["categorie"].value
    for k, v in changes.items():
        setattr(shape, k, v)
    db.commit()
    return shape


def set_availability(db: Session, shape: BrickShape, disponible: bool) -> BrickShape:
    shape.disponible = disponible
    db.commit()
    log.info("Moule %s %s", shape.code, "activé" if disponible else "désactivé")
    return shape


def delete_shape(db: Session, shape: BrickShape) -> None:
    used = db.scalar(select(WallAssignment.id).where(WallAssignment.brick_shape_id == shape.id).limit(1)) \
        or db.scalar(select(ProductionOrderLine.id).where(
            ProductionOrderLine.brick_shape_id == shape.id).limit(1))
    if used:
        raise Conflict(
            "Ce moule est utilisé par un calepinage ou une production : "
            "désactivez-le plutôt que de le supprimer."
        )
    db.delete(shape)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise Conflict("Ce moule est encore référencé et ne peut pas être supprimé.") from exc
    log.info("Moule %s supprimé", shape.code)
