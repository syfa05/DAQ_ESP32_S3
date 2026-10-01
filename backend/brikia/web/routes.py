"""Pages HTML (coquilles Jinja2). Toute donnée métier est chargée par l'API JSON.

Ces routes ne portent aucune sécurité métier : elles redirigent les visiteurs
non connectés et évitent d'afficher des pages inutiles au mauvais rôle, mais
l'autorisation réelle reste appliquée par les endpoints ``/api``.
"""

from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import AuthContext, get_db, get_settings_dep
from ..domain.enums import Role
from ..services import auth as auth_service
from ..services import users as users_service

templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

ROLE_LABELS = {Role.CHEF_PROJET.value: "Chef de projet", Role.OPERATEUR.value: "Opérateur"}

router = APIRouter(include_in_schema=False)


def optional_auth(request: Request, db: Session = Depends(get_db),
                  settings: Settings = Depends(get_settings_dep)) -> AuthContext | None:
    session = auth_service.resolve_session(db, request.cookies.get(settings.cookie_name))
    return AuthContext(user=session.user, session=session) if session else None


def error_page(request: Request, status: int, title: str, message: str) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "erreur.html", {"status": status, "title": title, "message": message,
                                 "user": None, "role_labels": ROLE_LABELS},
        status_code=status)


def _render(request: Request, auth: AuthContext | None, template: str,
            roles: set[str] | None = None, **ctx):
    if auth is None:
        return RedirectResponse(f"/connexion?suivant={quote(request.url.path)}", status_code=303)
    if roles and auth.user.role not in roles:
        return error_page(request, 403, "Accès refusé",
                          "Cette page n'est pas accessible avec votre rôle.")
    return templates.TemplateResponse(request, template, {
        "user": auth.user, "csrf": auth.session.csrf_token, "role_labels": ROLE_LABELS,
        "is_chef": auth.user.role == Role.CHEF_PROJET.value, **ctx})


CHEF = {Role.CHEF_PROJET.value}


@router.get("/connexion")
def login_page(request: Request, auth: AuthContext | None = Depends(optional_auth),
               db: Session = Depends(get_db)):
    if auth:
        return RedirectResponse("/", status_code=303)
    if not users_service.has_users(db):
        return RedirectResponse("/installation", status_code=303)
    return templates.TemplateResponse(request, "login.html", {"user": None, "role_labels": ROLE_LABELS})


@router.get("/")
def home(request: Request, auth=Depends(optional_auth)):
    return _render(request, auth, "projets.html", nav="projets")


@router.get("/projets/nouveau")
def new_project(request: Request, auth=Depends(optional_auth)):
    return _render(request, auth, "projet_nouveau.html", roles=CHEF, nav="projets",
                   settings=request.app.state.settings)


@router.get("/projets/{project_id}")
def project_page(project_id: int, request: Request, auth=Depends(optional_auth)):
    return _render(request, auth, "projet.html", nav="projets", project_id=project_id)


@router.get("/moules")
def molds_page(request: Request, auth=Depends(optional_auth)):
    return _render(request, auth, "moules.html", nav="moules")


@router.get("/production")
def production_page(request: Request, auth=Depends(optional_auth)):
    return _render(request, auth, "production.html", nav="production")


@router.get("/journal")
def audit_page(request: Request, auth=Depends(optional_auth)):
    return _render(request, auth, "journal.html", roles=CHEF, nav="journal")


@router.get("/utilisateurs")
def users_page(request: Request, auth=Depends(optional_auth)):
    return _render(request, auth, "utilisateurs.html", roles=CHEF, nav="utilisateurs")


@router.get("/compte")
def account_page(request: Request, auth=Depends(optional_auth)):
    return _render(request, auth, "compte.html", nav="compte")


@router.get("/installation")
def setup_page(request: Request, auth=Depends(optional_auth), db: Session = Depends(get_db)):
    """Premier démarrage : création du premier compte chef de projet."""
    if auth or users_service.has_users(db):
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(request, "installation.html",
                                      {"user": None, "role_labels": ROLE_LABELS})
