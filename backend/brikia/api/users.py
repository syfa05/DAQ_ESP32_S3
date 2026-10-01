from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import AuthContext, current_auth, get_db, get_settings_dep, require_chef_projet
from ..domain.errors import Conflict, PermissionDenied
from ..models import User
from ..schemas.auth import SessionOut, UserOut
from ..schemas.users import (
    ActiveIn, PasswordChangeIn, PasswordResetIn, SetupIn, UserAdminOut, UserCreateIn,
)
from ..services import auth as auth_service
from ..services import users as users_service

router = APIRouter(prefix="/api", tags=["utilisateurs"])


@router.get("/users", response_model=list[UserAdminOut])
def list_users(_: User = Depends(require_chef_projet),
               db: Session = Depends(get_db)) -> list[User]:
    return users_service.list_users(db)


@router.post("/users", response_model=UserAdminOut, status_code=201)
def create_user(body: UserCreateIn, actor: User = Depends(require_chef_projet),
                db: Session = Depends(get_db)) -> User:
    return users_service.add_user(db, actor, nom=body.nom, login=body.login,
                                  password=body.password, role=body.role)


@router.post("/users/{user_id}/actif", response_model=UserAdminOut)
def set_active(user_id: int, body: ActiveIn, actor: User = Depends(require_chef_projet),
               db: Session = Depends(get_db)) -> User:
    return users_service.set_active(db, actor, user_id, body.actif)


@router.post("/users/{user_id}/mot-de-passe", response_model=UserAdminOut)
def reset_password(user_id: int, body: PasswordResetIn,
                   actor: User = Depends(require_chef_projet),
                   db: Session = Depends(get_db)) -> User:
    return users_service.reset_password(db, actor, user_id, body.password)


@router.post("/auth/password", status_code=204)
def change_password(body: PasswordChangeIn, auth: AuthContext = Depends(current_auth),
                    db: Session = Depends(get_db)) -> None:
    users_service.change_own_password(db, auth.user, auth.session.id,
                                      body.current_password, body.new_password)


@router.post("/setup", response_model=SessionOut, status_code=201)
def first_run_setup(body: SetupIn, request: Request, response: Response,
                    db: Session = Depends(get_db),
                    settings: Settings = Depends(get_settings_dep)) -> SessionOut:
    """Création du premier chef de projet, une seule fois, depuis le poste local."""
    if request.client is None or request.client.host not in LOCAL_HOSTS:
        raise PermissionDenied(
            "La configuration initiale ne peut se faire que depuis le PC qui héberge BrikIA."
        )
    if users_service.has_users(db):
        raise Conflict("La configuration initiale a déjà été effectuée.")
    user = users_service.bootstrap_first_chef(db, nom=body.nom, login=body.login,
                                              password=body.password)
    token, session = auth_service.open_session(db, user, settings.session_ttl_hours)
    response.set_cookie(
        settings.cookie_name, token, max_age=settings.session_ttl_hours * 3600,
        httponly=True, secure=settings.cookie_secure,
        samesite=settings.cookie_samesite, path="/")
    return SessionOut(user=UserOut.model_validate(user), csrf_token=session.csrf_token)


LOCAL_HOSTS = {"127.0.0.1", "::1", "testclient"}
