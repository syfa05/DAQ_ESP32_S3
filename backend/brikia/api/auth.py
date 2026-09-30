from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import AuthContext, current_auth, get_db, get_settings_dep
from ..schemas.auth import LoginIn, SessionOut, UserOut
from ..services import auth as auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=SessionOut)
def login(
    body: LoginIn, request: Request, response: Response,
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep),
) -> SessionOut:
    user = auth_service.authenticate(db, request.app.state.throttle, body.login, body.password)
    token, session = auth_service.open_session(db, user, settings.session_ttl_hours)
    response.set_cookie(
        settings.cookie_name, token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True, secure=settings.cookie_secure,
        samesite=settings.cookie_samesite, path="/",
    )
    return SessionOut(user=UserOut.model_validate(user), csrf_token=session.csrf_token)


@router.post("/logout", status_code=204)
def logout(
    response: Response, auth: AuthContext = Depends(current_auth),
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings_dep),
) -> None:
    auth_service.close_session(db, auth.session)
    response.delete_cookie(settings.cookie_name, path="/")


@router.get("/me", response_model=SessionOut)
def me(auth: AuthContext = Depends(current_auth)) -> SessionOut:
    return SessionOut(user=UserOut.model_validate(auth.user), csrf_token=auth.session.csrf_token)
