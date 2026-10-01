"""Cas d'usage projets : création, consultation, mise à jour, transitions."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import BinaryIO

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from ..config import Settings
from ..domain import states
from ..domain.enums import ProjectStatus, Role
from ..domain.errors import Conflict, NotFound, ValidationFailed
from ..models import Project, User
from ..models.base import utcnow
from . import storage

log = logging.getLogger("brikia.projects")


def _clean(value: str | None, field: str, *, required: bool = False, max_len: int = 200) -> str:
    v = (value or "").strip()
    if required and not v:
        raise ValidationFailed(f"Le champ « {field} » est obligatoire.")
    if len(v) > max_len:
        raise ValidationFailed(f"Le champ « {field} » est trop long ({max_len} caractères max).")
    return v


def create_project(db: Session, settings: Settings, user: User, *, nom: str, ville: str,
                   architecte: str, filename: str | None, stream: BinaryIO) -> Project:
    """Crée le projet et stocke son plan de façon atomique.

    Si le stockage ou la validation échoue, ni ligne en base ni fichier ne
    subsistent.
    """
    project = Project(
        nom=_clean(nom, "nom", required=True), ville=_clean(ville, "ville", max_len=120),
        architecte=_clean(architecte, "architecte", max_len=120),
        status=ProjectStatus.A_ANALYSER.value, created_by_id=user.id,
    )
    stored = None
    try:
        db.add(project)
        db.flush()  # obtient l'id pour le répertoire de stockage
        stored = storage.save_upload(settings, project.id, filename, stream)
        project.plan_path = stored.relative_path
        project.plan_original_name = stored.original_name
        project.plan_size = stored.size
        project.plan_sha256 = stored.sha256
        db.commit()
    except BaseException:
        db.rollback()
        if stored:
            storage.delete_stored(settings, stored)
        raise
    log.info("Projet %s créé par %s", project.id, user.login)
    return project


def _visible(user: User, project: Project) -> bool:
    if user.role == Role.CHEF_PROJET.value:
        return True
    return ProjectStatus(project.status) in states.OPERATOR_VISIBLE


def list_projects(db: Session, user: User) -> list[Project]:
    q = select(Project).order_by(Project.id.desc())
    if user.role != Role.CHEF_PROJET.value:
        q = q.where(Project.status.in_([s.value for s in states.OPERATOR_VISIBLE]))
    return list(db.scalars(q))


def get_project(db: Session, user: User, project_id: int) -> Project:
    project = db.scalar(
        select(Project).where(Project.id == project_id)
        .options(selectinload(Project.walls))
    )
    # 404 (et non 403) : un opérateur ne doit pas deviner l'existence
    # d'un projet qui ne lui est pas accessible.
    if project is None or not _visible(user, project):
        raise NotFound("Projet introuvable.")
    return project


def update_project(db: Session, project: Project, *, nom: str | None = None,
                   ville: str | None = None, architecte: str | None = None) -> Project:
    if ProjectStatus(project.status) not in states.EDITABLE:
        raise Conflict("Ce projet est validé : ses informations ne peuvent plus être modifiées.")
    if nom is not None:
        project.nom = _clean(nom, "nom", required=True)
    if ville is not None:
        project.ville = _clean(ville, "ville", max_len=120)
    if architecte is not None:
        project.architecte = _clean(architecte, "architecte", max_len=120)
    db.commit()
    return project


def transition(db: Session, project: Project, target: ProjectStatus,
               now: datetime | None = None) -> None:
    """Unique point de changement de statut ; ne commit pas (l'appelant
    regroupe le changement de statut et ses effets dans une transaction).

    Le UPDATE conditionnel (``WHERE status = <statut lu>``) empêche deux
    requêtes concurrentes d'appliquer chacune la même transition.
    """
    states.ensure_transition(project.status, target)
    now = now or utcnow()
    values: dict = {"status": target.value}
    if target == ProjectStatus.VALIDE:
        values["validated_at"] = now
    elif target == ProjectStatus.TERMINE:
        values["completed_at"] = now
    result = db.execute(
        update(Project).where(Project.id == project.id, Project.status == project.status)
        .values(**values).execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        raise Conflict("Le projet a été modifié entre-temps. Rechargez la page.")
    db.refresh(project)
