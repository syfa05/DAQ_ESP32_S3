from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from sqlalchemy.orm import Session

from ..config import Settings
from ..adapters.analyzers.base import PlanAnalyzer
from ..adapters.production.base import ProductionGateway
from ..deps import (
    current_user, get_db, get_plan_analyzer, get_production_gateway, get_settings_dep,
    require_chef_projet,
)
from ..domain.errors import PayloadTooLarge
from ..models import User
from ..schemas.projects import ProjectDetail, ProjectOut, ProjectUpdate
from ..services import analysis as analysis_svc
from ..services import validation as validation_svc
from ..services import production as production_svc
from ..services import projects as svc

router = APIRouter(prefix="/api/projects", tags=["projets"])


@router.post("", response_model=ProjectOut, status_code=201)
def create_project(
    request: Request,
    nom: str = Form(...), ville: str = Form(""), architecte: str = Form(""),
    fichier: UploadFile = File(...),
    user: User = Depends(require_chef_projet), db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
):
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > settings.max_upload_bytes + 64 * 1024:
        raise PayloadTooLarge(f"Fichier trop volumineux (maximum {settings.max_upload_mb} Mo).")
    return svc.create_project(db, settings, user, nom=nom, ville=ville, architecte=architecte,
                              filename=fichier.filename, stream=fichier.file)


@router.get("", response_model=list[ProjectOut])
def list_projects(user: User = Depends(current_user), db: Session = Depends(get_db),
                  gateway: ProductionGateway = Depends(get_production_gateway)):
    # Rapatrie l'état des productions actives pour que la liste ne soit pas périmée.
    production_svc.refresh_active_orders(db, gateway)
    return svc.list_projects(db, user)


@router.get("/{project_id}", response_model=ProjectDetail)
def get_project(project_id: int, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    return svc.get_project(db, user, project_id)


@router.patch("/{project_id}", response_model=ProjectOut)
def update_project(project_id: int, body: ProjectUpdate,
                   user: User = Depends(require_chef_projet), db: Session = Depends(get_db)):
    project = svc.get_project(db, user, project_id)
    return svc.update_project(db, project, **body.model_dump(exclude_unset=True))


@router.post("/{project_id}/analyse", response_model=ProjectDetail)
def analyse_project(
    project_id: int, user: User = Depends(require_chef_projet),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep),
    analyzer: PlanAnalyzer = Depends(get_plan_analyzer),
):
    project = svc.get_project(db, user, project_id)
    return analysis_svc.analyse_project(db, settings, analyzer, project)


@router.post("/{project_id}/validation", response_model=ProjectDetail)
def validate_project(project_id: int, user: User = Depends(require_chef_projet),
                     db: Session = Depends(get_db)):
    project = svc.get_project(db, user, project_id)
    return validation_svc.validate_project(db, user, project)
