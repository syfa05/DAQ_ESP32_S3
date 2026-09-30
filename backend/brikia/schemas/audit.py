from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ActionLogOut(BaseModel):
    id: int
    user_id: int | None
    utilisateur: str  # nom de l'utilisateur, ou « système »
    action: str
    target_type: str
    target_id: int | None
    details: dict | None
    created_at: datetime
