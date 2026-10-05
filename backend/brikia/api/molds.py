from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..deps import current_user, get_db, require_chef_projet
from ..domain.enums import Role
from ..models import User
from ..schemas.molds import Availability, GammeOut, ShapeCreate, ShapeOut, ShapeUpdate
from ..services import molds as svc

router = APIRouter(prefix="/api/moulds", tags=["moules"])


def _visible(shape, user: User) -> ShapeOut:
    """Les coûts de revient sont réservés au chef de projet."""
    out = ShapeOut.model_validate(shape)
    if user.role != Role.CHEF_PROJET.value:
        out = out.model_copy(update={"cout_unitaire_eur": None})
    return out


@router.get("", response_model=list[ShapeOut])
def list_shapes(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return [_visible(s, user) for s in svc.list_shapes(db)]


@router.get("/gammes", response_model=list[GammeOut])
def list_gammes(_: User = Depends(current_user), db: Session = Depends(get_db)):
    """Gammes de moules (produit + largeur) : sert au choix automatique selon l'épaisseur des murs."""
    return svc.list_gammes(db)


@router.get("/{shape_id}", response_model=ShapeOut)
def get_shape(shape_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _visible(svc.get_shape(db, shape_id), user)


@router.post("", response_model=ShapeOut, status_code=201)
def create_shape(body: ShapeCreate, _: User = Depends(require_chef_projet),
                 db: Session = Depends(get_db)):
    return svc.create_shape(db, body)


@router.put("/{shape_id}", response_model=ShapeOut)
def update_shape(shape_id: int, body: ShapeUpdate, user: User = Depends(require_chef_projet),
                 db: Session = Depends(get_db)):
    return svc.update_shape(db, svc.get_shape(db, shape_id), body, user)


@router.patch("/{shape_id}/disponibilite", response_model=ShapeOut)
def set_availability(shape_id: int, body: Availability,
                     _: User = Depends(require_chef_projet), db: Session = Depends(get_db)):
    return svc.set_availability(db, svc.get_shape(db, shape_id), body.disponible)


@router.delete("/{shape_id}", status_code=204)
def delete_shape(shape_id: int, _: User = Depends(require_chef_projet),
                 db: Session = Depends(get_db)):
    svc.delete_shape(db, svc.get_shape(db, shape_id))
