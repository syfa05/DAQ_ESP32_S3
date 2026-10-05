from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LoginIn(BaseModel):
    login: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nom: str
    login: str
    role: str


class SessionOut(BaseModel):
    user: UserOut
    csrf_token: str
