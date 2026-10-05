from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from ..domain.enums import Role


class UserAdminOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    nom: str
    login: str
    role: str
    actif: bool


class UserCreateIn(BaseModel):
    nom: str = Field(min_length=1, max_length=120)
    login: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    role: Role


class ActiveIn(BaseModel):
    actif: bool


class PasswordResetIn(BaseModel):
    password: str = Field(min_length=1, max_length=256)


class PasswordChangeIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class SetupIn(BaseModel):
    nom: str = Field(min_length=1, max_length=120)
    login: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=256)
