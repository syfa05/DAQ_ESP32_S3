from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..deps import current_user, get_db, require_chef_projet
from ..models import User
from ..schemas.molds import Availability, ShapeCreate, ShapeOut, ShapeUpdate
from ..services import molds as svc

router = APIRouter(prefix="/api/moulds", tags=["moules"])


@router.get("", response_model=list[ShapeOut])
def list_shapes(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return svc.list_shapes(db)


@router.get("/{shape_id}", response_model=ShapeOut)
def get_shape(shape_id: int, _: User = Depends(current_user), db: Session = Depends(get_db)):
    return svc.get_shape(db, shape_id)


@router.post("", response_model=ShapeOut, status_code=201)
def create_shape(body: ShapeCreate, _: User = Depends(require_chef_projet),
                 db: Session = Depends(get_db)):
    return svc.create_shape(db, body)


@router.put("/{shape_id}", response_model=ShapeOut)
def update_shape(shape_id: int, body: ShapeUpdate, _: User = Depends(require_chef_projet),
                 db: Session = Depends(get_db)):
    return svc.update_shape(db, svc.get_shape(db, shape_id), body)


@router.patch("/{shape_id}/disponibilite", response_model=ShapeOut)
def set_availability(shape_id: int, body: Availability,
                     _: User = Depends(require_chef_projet), db: Session = Depends(get_db)):
    return svc.set_availability(db, svc.get_shape(db, shape_id), body.disponible)


@router.delete("/{shape_id}", status_code=204)
def delete_shape(shape_id: int, _: User = Depends(require_chef_projet),
                 db: Session = Depends(get_db)):
    svc.delete_shape(db, svc.get_shape(db, shape_id))
