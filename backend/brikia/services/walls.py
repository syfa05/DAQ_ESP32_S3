"""Correction manuelle de l'analyse : créer, modifier, supprimer un mur et ses ouvertures.

Autorisé tant que le projet n'est pas validé. Toute modification rend le calepinage caduc : il est
supprimé et un projet « à valider » revient à « à optimiser ». Chaque action est tracée (ActionLog).
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..domain import states
from ..domain.enums import ProjectStatus
from ..domain.errors import Conflict, NotFound, ValidationFailed
from ..models import LayoutRun, Opening, Project, User, Wall
from ..schemas.walls import WallEdit
from . import audit, projects

log = logging.getLogger("brikia.walls")
NOTE_PREFIX = "Plan corrigé à la main"


def validate_edit(data: WallEdit) -> None:
    """Cohérence géométrique du mur saisi (messages précis, destinés à l'utilisateur)."""
    for o in data.openings:
        label = {"porte": "La porte", "fenetre": "La fenêtre", "vitrine": "La vitrine",
                 "portail": "Le portail"}[o.type]
        if o.largeur_mm > data.longueur_mm:
            raise ValidationFailed(f"{label} ({o.largeur_mm} mm) est plus large que le mur ({data.longueur_mm} mm).")
        if o.hauteur_mm > data.hauteur_mm:
            raise ValidationFailed(f"{label} ({o.hauteur_mm} mm) est plus haute que le mur ({data.hauteur_mm} mm).")
        if o.x_mm is not None and o.x_mm + o.largeur_mm > data.longueur_mm:
            raise ValidationFailed(f"{label} dépasse la fin du mur : position {o.x_mm} mm + largeur "
                                   f"{o.largeur_mm} mm > {data.longueur_mm} mm.")
        if o.sill_mm is not None and o.sill_mm + o.hauteur_mm > data.hauteur_mm:
            raise ValidationFailed(f"{label} dépasse le haut du mur : allège {o.sill_mm} mm + hauteur "
                                   f"{o.hauteur_mm} mm > {data.hauteur_mm} mm.")
    placed = sorted((o for o in data.openings if o.x_mm is not None), key=lambda o: o.x_mm)
    for a, b in zip(placed, placed[1:]):
        if a.x_mm + a.largeur_mm > b.x_mm:
            raise ValidationFailed("Deux ouvertures se chevauchent le long du mur : "
                                   f"{a.x_mm}–{a.x_mm + a.largeur_mm} mm et {b.x_mm}–{b.x_mm + b.largeur_mm} mm.")
    if any(not (0 <= j <= data.longueur_mm) for j in data.junctions_mm):
        raise ValidationFailed("Une jonction en T est en dehors du mur (0 à la longueur du mur).")


def _ensure_editable(project: Project) -> None:
    if ProjectStatus(project.status) not in (ProjectStatus.A_OPTIMISER, ProjectStatus.A_VALIDER):
        raise Conflict("Les murs ne sont modifiables qu'après l'analyse et avant la validation du projet.")


def _get_wall(db: Session, project: Project, wall_id: int) -> Wall:
    wall = db.get(Wall, wall_id)
    if wall is None or wall.project_id != project.id:
        raise NotFound("Mur introuvable dans ce projet.")
    return wall


def _invalidate(db: Session, project: Project) -> None:
    """Le calepinage et le devis ne correspondent plus aux murs : on les retire."""
    for run in db.scalars(select(LayoutRun).where(LayoutRun.project_id == project.id)):
        db.delete(run)
    project.devis = None
    db.flush()
    if ProjectStatus(project.status) == ProjectStatus.A_VALIDER:
        projects.transition(db, project, ProjectStatus.A_OPTIMISER)


def _refresh_note(db: Session, project: Project) -> None:
    count = len(db.scalars(select(Wall.id).where(Wall.project_id == project.id,
                                                 Wall.manuel.is_(True))).all())
    notes = [x for x in (project.analysis_notes or []) if not x.startswith(NOTE_PREFIX)]
    if count:
        notes.append(f"{NOTE_PREFIX} : {count} mur(s) créé(s) ou modifié(s) manuellement. "
                     "Le calepinage doit être recalculé.")
    project.analysis_notes = notes


def _apply(wall: Wall, data: WallEdit) -> None:
    wall.nom, wall.longueur_mm, wall.hauteur_mm = data.nom, data.longueur_mm, data.hauteur_mm
    wall.start_kind, wall.end_kind = data.start_kind, data.end_kind
    wall.thickness_mm = data.thickness_mm
    wall.junctions_mm = sorted(set(data.junctions_mm)) or None
    if data.start_kind or data.end_kind:
        wall.is_corner = bool({"angle", "butee"} & {data.start_kind, data.end_kind})
    else:
        wall.is_corner = bool(data.is_corner)
    wall.manuel = True
    wall.openings = [Opening(type=o.type, largeur_mm=o.largeur_mm, hauteur_mm=o.hauteur_mm,
                             x_mm=o.x_mm, sill_mm=o.sill_mm, manuel=True) for o in data.openings]


def _summary(wall: Wall) -> dict:
    return {"nom": wall.nom, "longueur_mm": wall.longueur_mm, "hauteur_mm": wall.hauteur_mm,
            "ouvertures": len(wall.openings), "debut": wall.start_kind, "fin": wall.end_kind}


def create_wall(db: Session, actor: User, project: Project, data: WallEdit) -> Wall:
    _ensure_editable(project)
    validate_edit(data)
    wall = Wall(project_id=project.id)
    _apply(wall, data)
    db.add(wall)
    db.flush()
    _invalidate(db, project)
    _refresh_note(db, project)
    audit.record(db, actor, "wall.create", "wall", wall.id, _summary(wall))
    db.commit()
    return wall


def update_wall(db: Session, actor: User, project: Project, wall_id: int, data: WallEdit) -> Wall:
    _ensure_editable(project)
    validate_edit(data)
    wall = _get_wall(db, project, wall_id)
    before = _summary(wall)
    _apply(wall, data)
    db.flush()
    _invalidate(db, project)
    _refresh_note(db, project)
    audit.record(db, actor, "wall.update", "wall", wall.id, {"avant": before, "apres": _summary(wall)})
    db.commit()
    return wall


def delete_wall(db: Session, actor: User, project: Project, wall_id: int) -> None:
    _ensure_editable(project)
    wall = _get_wall(db, project, wall_id)
    remaining = len(db.scalars(select(Wall.id).where(Wall.project_id == project.id)).all())
    if remaining <= 1:
        raise Conflict("Un projet doit garder au moins un mur.")
    summary = _summary(wall)
    _invalidate(db, project)   # d'abord : les affectations du calepinage référencent le mur
    db.delete(wall)
    db.flush()
    _refresh_note(db, project)
    audit.record(db, actor, "wall.delete", "wall", wall_id, summary)
    db.commit()
