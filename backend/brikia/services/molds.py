"""Bibliothèque de moules."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..domain.errors import Conflict, NotFound, ValidationFailed
from ..models import BrickShape, ProductionOrderLine, User, WallAssignment
from ..schemas.molds import ShapeCreate, ShapeUpdate
from . import audit

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


def update_shape(db: Session, shape: BrickShape, data: ShapeUpdate,
                 actor: User | None = None) -> BrickShape:
    changes = data.model_dump(exclude_unset=True)
    for field in ("nom", "produit", "disponible", "categorie"):
        if field in changes and changes[field] is None:
            raise ValidationFailed(f"Le champ « {field} » ne peut pas être vide.")
    if "categorie" in changes:
        changes["categorie"] = changes["categorie"].value
    before = {k: getattr(shape, k) for k in changes}
    for k, v in changes.items():
        setattr(shape, k, v)
    diff = {k: {"avant": str(before[k]), "apres": str(v)} for k, v in changes.items()
            if before[k] != v}
    if diff:  # les coûts et dimensions influencent les devis : on garde la trace
        audit.record(db, actor, "mold.update", "brick_shape", shape.id,
                     {"code": shape.code, "modifications": diff})
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


# Fonctions posées par le calepinage assise par assise : une gamme est « complète » si elle les a toutes.
GAMME_FONCTIONS = ("standard", "angle", "chainage", "chainage_h", "linteau", "demi", "appui")


def gamme_key(produit: str, largeur_mm: int | None) -> str:
    return f"{produit}|{largeur_mm if largeur_mm is not None else ''}"


def list_gammes(db: Session) -> list[dict]:
    groups: dict[str, list[BrickShape]] = {}
    for s in db.scalars(select(BrickShape).order_by(BrickShape.id)):
        groups.setdefault(gamme_key(s.produit, s.largeur_mm), []).append(s)
    out = []
    for key, members in groups.items():
        if not any(m.categorie == "standard" for m in members):
            continue   # pas de moule standard (ex. acrotère seul) : pas une gamme de pose
        available = [m for m in members if m.disponible]
        cats = sorted({m.categorie for m in available})
        missing = [c for c in GAMME_FONCTIONS if c not in cats]
        out.append({"cle": key, "produit": members[0].produit, "largeur_mm": members[0].largeur_mm,
                    "nb_moules": len(members), "nb_disponibles": len(available), "categories": cats,
                    "manque": missing, "complete": not missing})
    return sorted(out, key=lambda g: (g["produit"], g["largeur_mm"] or 0))


def ensure_gamme_exists(db: Session, key: str | None) -> None:
    """Gamme imposée à un mur : elle doit exister et contenir un moule standard."""
    if not key:
        return
    for g in list_gammes(db):
        if g["cle"] == key and "standard" in g["categories"]:
            return
    raise ValidationFailed(f"Gamme de moules inconnue ou sans moule standard disponible : « {key} ».")
