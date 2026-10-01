"""ActionLog : journal métier de traçabilité (distinct des logs techniques).

``record`` n'effectue pas de commit : l'entrée est écrite dans la même
transaction que l'action qu'elle trace (les deux existent ou aucune).
Ne jamais y mettre de secret ni de mot de passe.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ActionLog, User


def record(db: Session, user: User | None, action: str, target_type: str,
           target_id: int | None, details: dict | None = None) -> ActionLog:
    entry = ActionLog(user_id=user.id if user else None, action=action,
                      target_type=target_type, target_id=target_id, details=details)
    db.add(entry)
    return entry


def list_entries(db: Session, *, limit: int = 50, offset: int = 0, action: str | None = None,
                 target_type: str | None = None, target_id: int | None = None):
    q = select(ActionLog).order_by(ActionLog.id.desc()).limit(limit).offset(offset)
    if action:
        q = q.where(ActionLog.action == action)
    if target_type:
        q = q.where(ActionLog.target_type == target_type)
    if target_id is not None:
        q = q.where(ActionLog.target_id == target_id)
    return list(db.scalars(q))
