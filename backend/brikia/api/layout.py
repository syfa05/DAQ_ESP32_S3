from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..adapters.layout.base import LayoutEngine
from ..deps import current_user, get_db, get_layout_engine, require_chef_projet
from ..models import User
from ..schemas.layout import BomOut, LayoutOut
from ..services import layout as svc
from ..services import projects as projects_svc

router = APIRouter(prefix="/api/projects", tags=["calepinage"])


@router.post("/{project_id}/calepinage", response_model=LayoutOut)
def run_layout(project_id: int, user: User = Depends(require_chef_projet),
               db: Session = Depends(get_db),
               engine: LayoutEngine = Depends(get_layout_engine)):
    project = projects_svc.get_project(db, user, project_id)
    svc.run_layout(db, engine, project)
    return svc.layout_out(svc.latest_run(db, project))


@router.get("/{project_id}/calepinage", response_model=LayoutOut)
def get_layout(project_id: int, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    project = projects_svc.get_project(db, user, project_id)  # visibilité par rôle
    return svc.layout_out(svc.latest_run(db, project))


@router.get("/{project_id}/bom", response_model=BomOut)
def get_bom(project_id: int, user: User = Depends(current_user),
            db: Session = Depends(get_db)):
    project = projects_svc.get_project(db, user, project_id)
    return svc.build_bom_out(svc.latest_run(db, project))
