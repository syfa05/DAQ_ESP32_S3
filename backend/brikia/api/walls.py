from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..deps import get_db, require_chef_projet
from ..models import User
from ..schemas.projects import WallOut
from ..schemas.walls import WallEdit
from ..services import projects as projects_svc
from ..services import walls as svc

router = APIRouter(prefix="/api/projects", tags=["murs"])


@router.post("/{project_id}/murs", response_model=WallOut, status_code=201)
def create_wall(project_id: int, body: WallEdit, user: User = Depends(require_chef_projet),
                db: Session = Depends(get_db)):
    return svc.create_wall(db, user, projects_svc.get_project(db, user, project_id), body)


@router.put("/{project_id}/murs/{wall_id}", response_model=WallOut)
def update_wall(project_id: int, wall_id: int, body: WallEdit,
                user: User = Depends(require_chef_projet), db: Session = Depends(get_db)):
    return svc.update_wall(db, user, projects_svc.get_project(db, user, project_id), wall_id, body)


@router.delete("/{project_id}/murs/{wall_id}", status_code=204)
def delete_wall(project_id: int, wall_id: int, user: User = Depends(require_chef_projet),
                db: Session = Depends(get_db)):
    svc.delete_wall(db, user, projects_svc.get_project(db, user, project_id), wall_id)
