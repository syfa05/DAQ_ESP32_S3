"""Étape « calepinage » : a_optimiser -> a_valider, puis consultation / BOM."""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from ..adapters.layout.base import LayoutEngine
from ..domain.bom import BomRow, build_bom
from ..domain.enums import ProjectStatus, ShapeCategory
from ..domain.errors import (
    AnalysisFailed, DomainError, InvalidTransition, NotFound, ValidationFailed,
)
from ..domain.layout import BrickShapeInput, LayoutResult, WallInput
from ..domain.geometry import OpeningGeometry, WallGeometry
from ..models import BrickShape, LayoutRun, Project, Wall, WallAssignment
from ..schemas.layout import (
    BomLineOut, BomOut, BomWallQuantity, LayoutOut, ShapeQuantity, WallCourseShape, WallDetailOut,
    WallLayoutOut,
)
from . import projects

log = logging.getLogger("brikia.layout")

# Le calepinage peut être recalculé tant que le projet n'est pas validé
# (ex. après avoir changé la disponibilité d'un moule).
_RUNNABLE = (ProjectStatus.A_OPTIMISER, ProjectStatus.A_VALIDER)


def _wall_input(w: Wall) -> WallInput:
    return WallInput(w.id, WallGeometry(
        w.nom, w.longueur_mm, w.hauteur_mm, w.is_corner,
        tuple(OpeningGeometry(o.type, o.largeur_mm, o.hauteur_mm, o.x_mm, o.sill_mm)
              for o in w.openings),
        w.start_kind, w.end_kind, tuple(w.junctions_mm or ()), w.thickness_mm, w.gamme))


def _shape_input(s: BrickShape) -> BrickShapeInput:
    return BrickShapeInput(s.id, s.code, s.nom, s.produit, ShapeCategory(s.categorie),
                           s.disponible, s.longueur_mm, s.largeur_mm, s.hauteur_mm,
                           s.cadence_par_heure)


def _check_result(result: LayoutResult, wall_ids: set[int], shape_ids: set[int]) -> None:
    """Un moteur (futur, potentiellement externe) ne doit pas pouvoir corrompre la base."""
    if {w.wall_id for w in result.walls} != wall_ids:
        raise ValidationFailed("Le calepinage ne couvre pas exactement les murs du projet.")
    for w in result.walls:
        for sid, qty in w.quantities.items():
            if sid not in shape_ids or qty < 0:
                raise ValidationFailed("Le calepinage contient une quantité ou un moule invalide.")


def run_layout(db: Session, engine: LayoutEngine, project: Project) -> Project:
    status = ProjectStatus(project.status)
    if status not in _RUNNABLE:
        raise InvalidTransition(
            "Le calepinage n'est possible que pour un projet « à optimiser » "
            "(ou « à valider », pour le recalculer).")

    walls = list(db.scalars(
        select(Wall).where(Wall.project_id == project.id).order_by(Wall.id)
        .options(selectinload(Wall.openings))))
    if not walls:
        raise InvalidTransition("Ce projet n'a aucun mur : lancez d'abord l'analyse.")
    shapes = list(db.scalars(select(BrickShape).order_by(BrickShape.id)))

    try:
        result = engine.calculate([_wall_input(w) for w in walls],
                                  [_shape_input(s) for s in shapes])
        _check_result(result, {w.id for w in walls}, {s.id for s in shapes})
    except DomainError:
        raise
    except Exception as exc:
        log.exception("Échec du calepinage du projet %s", project.id)
        raise AnalysisFailed(
            "Le calcul du calepinage a échoué. Le projet n'a pas été modifié.") from exc

    try:
        for old in list(project.layout_runs):  # remplace le calepinage précédent
            db.delete(old)
        db.flush()
        run = LayoutRun(
            project_id=project.id, engine=result.engine, parameters=result.parameters,
            warnings=list(result.warnings),
            estimated_duration_min=result.estimated_duration_min,
            detail=({str(wl.wall_id): wl.detail for wl in result.walls if wl.detail} or None))
        db.add(run)
        db.flush()
        for wl in result.walls:
            for shape_id, qty in wl.quantities.items():
                if qty > 0:
                    db.add(WallAssignment(layout_run_id=run.id, wall_id=wl.wall_id,
                                          brick_shape_id=shape_id, quantity=qty))
        if status == ProjectStatus.A_OPTIMISER:
            projects.transition(db, project, ProjectStatus.A_VALIDER)
        db.commit()
    except BaseException:
        db.rollback()
        raise
    log.info("Calepinage du projet %s calculé (%s, %d avertissement(s))",
             project.id, result.engine, len(result.warnings))
    db.refresh(project)
    return project


def latest_run(db: Session, project: Project) -> LayoutRun:
    run = db.scalar(
        select(LayoutRun).where(LayoutRun.project_id == project.id)
        .order_by(LayoutRun.id.desc()).limit(1)
        .options(selectinload(LayoutRun.assignments).selectinload(WallAssignment.brick_shape),
                 selectinload(LayoutRun.assignments).selectinload(WallAssignment.wall)))
    if run is None:
        raise NotFound("Aucun calepinage n'a encore été calculé pour ce projet.")
    return run


def build_bom_out(run: LayoutRun) -> BomOut:
    lines = build_bom([
        BomRow(a.wall_id, a.wall.nom, a.brick_shape_id, a.brick_shape.code, a.brick_shape.nom,
               a.brick_shape.produit, a.brick_shape.categorie, a.quantity)
        for a in run.assignments])
    return BomOut(
        lignes=[BomLineOut(
            shape_id=ln.shape_id, code=ln.code, nom=ln.nom, produit=ln.produit,
            categorie=ln.categorie, quantite_totale=ln.total,
            par_mur=[BomWallQuantity(wall_id=i, wall_nom=n, quantite=q) for i, n, q in ln.per_wall])
            for ln in lines],
        total_blocs=sum(ln.total for ln in lines),
        duree_estimee_min=run.estimated_duration_min,
        avertissements=list(run.warnings or []),
    )


def layout_out(run: LayoutRun) -> LayoutOut:
    by_wall: dict[int, list[WallAssignment]] = {}
    for a in sorted(run.assignments, key=lambda a: (a.wall_id, a.brick_shape_id)):
        by_wall.setdefault(a.wall_id, []).append(a)
    murs = [WallLayoutOut(
        wall_id=wid, wall_nom=items[0].wall.nom, total=sum(a.quantity for a in items),
        quantites=[ShapeQuantity(shape_id=a.brick_shape_id, code=a.brick_shape.code,
                                 nom=a.brick_shape.nom, categorie=a.brick_shape.categorie,
                                 quantite=a.quantity) for a in items])
        for wid, items in by_wall.items()]
    detail = run.detail or {}
    indicators = ({"pieces_coupees": sum(d.get("coupes", 0) for d in detail.values()),
                   "chutes_totales_m": round(sum(d.get("chutes_mm", 0) for d in detail.values()) / 1000)}
                  if detail else {})
    return LayoutOut(id=run.id, moteur=run.engine, created_at=run.created_at,
                     parametres=run.parameters or {}, avertissements=list(run.warnings or []),
                     murs=murs, bom=build_bom_out(run), detail_disponible=bool(detail),
                     indicateurs=indicators)


def wall_detail(db: Session, project: Project, wall_id: int) -> WallDetailOut:
    """Détail assise par assise d'un mur (chargé à la demande : il peut être volumineux)."""
    run = latest_run(db, project)
    detail = (run.detail or {}).get(str(wall_id))
    wall = db.get(Wall, wall_id)
    if detail is None or wall is None or wall.project_id != project.id:
        raise NotFound("Aucun détail assise par assise pour ce mur (recalculez le calepinage).")
    ids = {int(k) for k in detail.get("pose", {})} | {
        int(run_[1]) for course in detail["courses"] for run_ in course if run_[1]}
    shapes = db.scalars(select(BrickShape).where(BrickShape.id.in_(ids))).all()
    return WallDetailOut(
        wall_id=wall.id, wall_nom=wall.nom, detail=detail,
        formes=[WallCourseShape(id=s.id, code=s.code, nom=s.nom, categorie=s.categorie,
                                longueur_mm=s.longueur_mm, hauteur_mm=s.hauteur_mm) for s in shapes])
