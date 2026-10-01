"""Documents : plans de moules (SVG), devis, tarifs et rapport PDF."""

from __future__ import annotations

import re

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from ..deps import current_user, get_db, require_chef_projet
from ..models import User
from ..schemas.pricing import TarifsIn, TarifsOut
from ..services import molds as molds_svc
from ..services import pricing as pricing_svc
from ..services import projects as projects_svc
from ..services import reports as reports_svc

router = APIRouter(prefix="/api", tags=["documents"])


@router.get("/moulds/{shape_id}/plan.svg")
def mold_plan(shape_id: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    svg = reports_svc.shape_svg(molds_svc.get_shape(db, shape_id))
    return Response(svg, media_type="image/svg+xml", headers={"Cache-Control": "no-store"})


@router.get("/tarifs", response_model=TarifsOut)
def get_tarifs(_: User = Depends(require_chef_projet), db: Session = Depends(get_db)):
    return pricing_svc.get_settings(db)


@router.put("/tarifs", response_model=TarifsOut)
def put_tarifs(body: TarifsIn, user: User = Depends(require_chef_projet),
               db: Session = Depends(get_db)):
    return pricing_svc.update_settings(db, user, body)


@router.get("/projects/{project_id}/devis")
def get_devis(project_id: int, user: User = Depends(require_chef_projet),
              db: Session = Depends(get_db)):
    project = projects_svc.get_project(db, user, project_id)
    return pricing_svc.quote_for_project(db, project)


@router.get("/projects/{project_id}/rapport.pdf")
def get_report(project_id: int, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    project = projects_svc.get_project(db, user, project_id)
    pdf = reports_svc.project_report(db, user, project)
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", project.nom).strip("_") or "projet"
    return Response(pdf, media_type="application/pdf", headers={
        "Content-Disposition": f'inline; filename="rapport-{project.id}-{name}.pdf"',
        "Cache-Control": "no-store"})
