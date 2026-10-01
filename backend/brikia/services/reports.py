"""Assemblage des données du rapport PDF d'un projet et des plans de moules."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from .. import __version__
from ..adapters.reports.pdf import build_report
from ..domain.enums import Role
from ..domain.errors import NotFound, ValidationFailed
from ..domain.geometry import OpeningGeometry, WallGeometry
from ..domain.moldplan import Prim, mold_sheet, to_svg
from ..models import BrickShape, Project, User, Wall
from ..models.base import utcnow
from . import layout, pricing

STATUS_LABELS = {
    "a_analyser": "À analyser", "a_optimiser": "À optimiser", "a_valider": "À valider",
    "valide": "Validé", "en_production": "En production", "termine": "Terminé",
}


def shape_sheet(shape: BrickShape) -> list[Prim]:
    if not (shape.longueur_mm and shape.largeur_mm and shape.hauteur_mm):
        raise ValidationFailed(
            "Ce moule n'a pas de dimensions (longueur, largeur, hauteur) : renseignez-les "
            "pour obtenir son plan.")
    return mold_sheet(shape.code, shape.nom, shape.produit, shape.categorie, shape.forme,
                      shape.longueur_mm, shape.largeur_mm, shape.hauteur_mm, shape.poids_g)


def shape_svg(shape: BrickShape) -> str:
    return to_svg(shape_sheet(shape))


def _date(dt) -> str:
    return dt.strftime("%d/%m/%Y") if dt else ""


def project_report(db: Session, user: User, project: Project, *, with_molds: bool = True) -> bytes:
    walls = list(db.scalars(select(Wall).where(Wall.project_id == project.id).order_by(Wall.id)
                            .options(selectinload(Wall.openings))))
    wall_rows = []
    for w in walls:
        g = WallGeometry(w.nom, w.longueur_mm, w.hauteur_mm, w.is_corner,
                         tuple(OpeningGeometry(o.type, o.largeur_mm, o.hauteur_mm) for o in w.openings))
        wall_rows.append({
            "nom": w.nom, "longueur_m": Decimal(w.longueur_mm) / 1000,
            "hauteur_m": Decimal(w.hauteur_mm) / 1000,
            "brut_m2": Decimal(g.gross_area_mm2) / 1_000_000,
            "ouvertures_m2": Decimal(g.openings_area_mm2) / 1_000_000,
            "net_m2": Decimal(g.net_area_mm2) / 1_000_000, "angle": w.is_corner})

    bom, quote, sheets = None, None, []
    try:
        run = layout.latest_run(db, project)
    except NotFound:
        run = None
    if run is not None:
        out = layout.build_bom_out(run)
        shapes = {s.id: s for s in db.scalars(select(BrickShape).where(
            BrickShape.id.in_([ln.shape_id for ln in out.lignes])))}
        lines, total_kg, known = [], Decimal(0), True
        for ln in out.lignes:
            s = shapes.get(ln.shape_id)
            kg = (Decimal(ln.quantite_totale) * s.poids_g / 1000) if s and s.poids_g else None
            known = known and kg is not None
            total_kg += kg or 0
            lines.append({"code": ln.code, "nom": ln.nom, "produit": ln.produit,
                          "quantite": ln.quantite_totale, "poids_kg": kg})
            if with_molds and s and s.longueur_mm and s.largeur_mm and s.hauteur_mm:
                sheets.append((s.code, shape_sheet(s)))
        bom = {"lignes": lines, "total_blocs": out.total_blocs,
               "poids_total_kg": total_kg if known else None,
               "duree_estimee_min": out.duree_estimee_min, "avertissements": out.avertissements}
        if user.role == Role.CHEF_PROJET.value:  # les prix ne sont pas diffusés aux opérateurs
            quote = pricing.quote_for_project(db, project)

    return build_report(
        project={"nom": project.nom, "ville": project.ville, "architecte": project.architecte,
                 "statut": STATUS_LABELS.get(project.status, project.status),
                 "cree_le": _date(project.created_at), "valide_le": _date(project.validated_at),
                 "plan": project.plan_original_name, "analyse_source": project.analysis_source,
                 "analyse_notes": project.analysis_notes},
        walls=wall_rows, bom=bom, quote=quote, mold_sheets=sheets,
        generated_by=f"{user.nom} ({user.login})", generated_at=utcnow(), version=__version__)
