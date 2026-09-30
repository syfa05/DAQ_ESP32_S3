"""Dépendances FastAPI : base, utilisateur courant, contrôle des rôles."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .adapters.analyzers.base import PlanAnalyzer
from .config import Settings
from .db import get_session_factory
from .domain.enums import Role
from .domain.errors import AuthenticationRequired, CsrfError, PermissionDenied
from .models import User, UserSession
from .security import safe_equal
from .services import auth as auth_service

UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def get_settings_dep(request: Request) -> Settings:
    return request.app.state.settings


def get_plan_analyzer(request: Request) -> PlanAnalyzer:
    return request.app.state.plan_analyzer


def get_db() -> Iterator[Session]:
    """Session par requête. Les services valident (commit) explicitement ;
    ce qui n'a pas été validé est annulé à la fermeture."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


@dataclass
class AuthContext:
    user: User
    session: UserSession


def current_auth(
    request: Request,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings_dep),
) -> AuthContext:
    session = auth_service.resolve_session(db, request.cookies.get(settings.cookie_name))
    if session is None:
        raise AuthenticationRequired("Veuillez vous connecter.")
    if request.method in UNSAFE_METHODS:
        sent = request.headers.get("x-csrf-token", "")
        if not safe_equal(sent, session.csrf_token):
            raise CsrfError("Requête refusée : jeton de sécurité invalide. Rechargez la page.")
    return AuthContext(user=session.user, session=session)


def current_user(auth: AuthContext = Depends(current_auth)) -> User:
    return auth.user


def require_role(*roles: Role) -> Callable[..., User]:
    """Contrôle d'accès côté backend, à appliquer sur chaque endpoint protégé."""
    allowed = {r.value for r in roles}

    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise PermissionDenied("Vous n'avez pas les droits pour effectuer cette action.")
        return user

    return dependency


require_chef_projet = require_role(Role.CHEF_PROJET)
require_operateur = require_role(Role.OPERATEUR)
