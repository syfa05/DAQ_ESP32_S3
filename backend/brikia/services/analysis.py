"""Étape « analyse » : a_analyser -> a_optimiser."""

from __future__ import annotations

import hashlib
import logging

from sqlalchemy.orm import Session

from ..adapters.analyzers.base import PlanAnalyzer, PlanFile
from ..config import Settings
from ..domain import states
from ..domain.enums import ProjectStatus
from ..domain.errors import AnalysisFailed, DomainError, Conflict
from ..domain.geometry import ProjectGeometry, validate_geometry
from ..models import Opening, Project, Wall
from . import projects

log = logging.getLogger("brikia.analysis")


def _plan_file(settings: Settings, project: Project) -> PlanFile:
    if not project.plan_path:
        raise Conflict("Ce projet n'a pas de plan importé.")
    path = settings.uploads_dir / project.plan_path
    if not path.is_file():
        log.error("Plan introuvable sur disque : %s", path)
        raise Conflict("Le fichier de plan est introuvable sur le serveur. Réimportez le plan.")
    return PlanFile(path=path, original_name=project.plan_original_name or path.name,
                    extension=path.suffix.lower(), size=project.plan_size or 0,
                    sha256=project.plan_sha256 or hashlib.sha256(path.read_bytes()).hexdigest())


def analyse_project(db: Session, settings: Settings, analyzer: PlanAnalyzer,
                    project: Project) -> Project:
    # Échec rapide et message clair avant tout travail : un second appel
    # (double clic, rafraîchissement) est refusé ici, sans doublon de murs.
    states.ensure_transition(project.status, ProjectStatus.A_OPTIMISER)
    plan = _plan_file(settings, project)

    try:
        geometry: ProjectGeometry = analyzer.analyse(plan)
        validate_geometry(geometry)
    except DomainError:
        raise
    except Exception as exc:  # analyseur défaillant : détails en log seulement
        log.exception("Échec de l'analyse du projet %s", project.id)
        raise AnalysisFailed("L'analyse du plan a échoué. Le projet n'a pas été modifié.") from exc

    try:
        # Transition gardée d'abord : si une requête concurrente a déjà
        # transitionné, on échoue avant d'insérer le moindre mur.
        projects.transition(db, project, ProjectStatus.A_OPTIMISER)
        project.analysis_source = geometry.source
        project.analysis_notes = list(geometry.notes)
        for w in geometry.walls:
            wall = Wall(project_id=project.id, nom=w.nom, longueur_mm=w.longueur_mm,
                        hauteur_mm=w.hauteur_mm, is_corner=w.is_corner,
                        start_kind=w.start_kind, end_kind=w.end_kind,
                        junctions_mm=list(w.junctions_mm) or None, thickness_mm=w.thickness_mm)
            wall.openings = [Opening(type=o.type, largeur_mm=o.largeur_mm, hauteur_mm=o.hauteur_mm,
                                     x_mm=o.x_mm, sill_mm=o.sill_mm) for o in w.openings]
            db.add(wall)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    log.info("Projet %s analysé (%d murs, source %s)", project.id, len(geometry.walls),
             geometry.source)
    db.refresh(project)
    return project
