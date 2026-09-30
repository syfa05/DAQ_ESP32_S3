from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..deps import get_db, require_chef_projet
from ..models import User
from ..schemas.audit import ActionLogOut
from ..services import audit as svc

router = APIRouter(prefix="/api/audit", tags=["traçabilité"])


@router.get("", response_model=list[ActionLogOut])
def list_audit(
    limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
    action: str | None = None, target_type: str | None = None, target_id: int | None = None,
    _: User = Depends(require_chef_projet), db: Session = Depends(get_db),
):
    entries = svc.list_entries(db, limit=limit, offset=offset, action=action,
                               target_type=target_type, target_id=target_id)
    names = {u.id: u.nom for u in db.scalars(select(User))}
    return [ActionLogOut(
        id=e.id, user_id=e.user_id, utilisateur=names.get(e.user_id, "système"),
        action=e.action, target_type=e.target_type, target_id=e.target_id,
        details=e.details, created_at=e.created_at) for e in entries]
