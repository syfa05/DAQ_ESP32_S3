"""Validation d'un agencement par le chef de projet : a_valider -> valide."""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from ..domain import states
from ..domain.enums import ProjectStatus
from ..domain.errors import Conflict, NotFound
from ..models import Project, User
from . import audit, layout, projects

log = logging.getLogger("brikia.validation")


def validate_project(db: Session, user: User, project: Project) -> Project:
    status = ProjectStatus(project.status)
    if status in (ProjectStatus.VALIDE, ProjectStatus.EN_PRODUCTION, ProjectStatus.TERMINE):
        raise Conflict("Ce projet est déjà validé.")
    states.ensure_transition(status, ProjectStatus.VALIDE)  # refuse les autres statuts
    try:
        run = layout.latest_run(db, project)
    except NotFound as exc:
        raise Conflict("Aucun calepinage à valider : lancez d'abord le calepinage.") from exc

    bom = layout.build_bom_out(run)
    try:
        projects.transition(db, project, ProjectStatus.VALIDE)
        audit.record(db, user, "project.validate", "project", project.id, {
            "layout_run_id": run.id, "moteur": run.engine,
            "total_blocs": bom.total_blocs, "avertissements": len(bom.avertissements),
        })
        db.commit()  # statut + trace dans la même transaction
    except BaseException:
        db.rollback()
        raise
    log.info("Projet %s validé par %s", project.id, user.login)
    db.refresh(project)
    return project
