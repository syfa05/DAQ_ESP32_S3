from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ..adapters.production.base import ProductionGateway
from ..deps import current_user, get_db, get_production_gateway, require_operateur
from ..models import User
from ..schemas.production import OrderOut
from ..services import production as svc
from ..services import projects as projects_svc

router = APIRouter(tags=["production"])


@router.post("/api/projects/{project_id}/production", response_model=OrderOut, status_code=201)
def start_production(project_id: int, user: User = Depends(require_operateur),
                     db: Session = Depends(get_db),
                     gateway: ProductionGateway = Depends(get_production_gateway)):
    project = projects_svc.get_project(db, user, project_id)
    return svc.order_out(svc.start_production(db, gateway, user, project))


@router.get("/api/projects/{project_id}/production", response_model=OrderOut)
def project_production(project_id: int, user: User = Depends(current_user),
                       db: Session = Depends(get_db),
                       gateway: ProductionGateway = Depends(get_production_gateway)):
    project = projects_svc.get_project(db, user, project_id)
    order = svc.latest_order_for_project(db, project)
    return svc.order_out(svc.refresh_order(db, gateway, order))


@router.get("/api/production", response_model=list[OrderOut])
def list_production(_: User = Depends(current_user), db: Session = Depends(get_db),
                    gateway: ProductionGateway = Depends(get_production_gateway)):
    return [svc.order_out(o) for o in svc.list_orders(db, gateway)]


@router.get("/api/production/{order_id}", response_model=OrderOut)
def get_order(order_id: int, _: User = Depends(current_user), db: Session = Depends(get_db),
              gateway: ProductionGateway = Depends(get_production_gateway)):
    order = svc.get_order_row(db, order_id)
    return svc.order_out(svc.refresh_order(db, gateway, order))
