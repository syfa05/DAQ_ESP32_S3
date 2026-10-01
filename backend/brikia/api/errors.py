"""Traduction des erreurs en réponses JSON françaises (jamais de traceback)."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..domain import errors as e

log = logging.getLogger("brikia.api")

_STATUS: list[tuple[type[e.DomainError], int]] = [
    (e.AuthenticationRequired, 401),
    (e.InvalidCredentials, 401),
    (e.TooManyAttempts, 429),
    (e.PermissionDenied, 403),
    (e.CsrfError, 403),
    (e.NotFound, 404),
    (e.Conflict, 409),  # couvre InvalidTransition
    (e.PayloadTooLarge, 413),
    (e.GatewayError, 503),
    (e.AnalysisFailed, 422),
    (e.ValidationFailed, 422),
]


def _wants_html(request: Request) -> bool:
    return not request.url.path.startswith("/api/") and "text/html" in request.headers.get(
        "accept", "")


def _status_for(exc: e.DomainError) -> int:
    for cls, status in _STATUS:
        if isinstance(exc, cls):
            return status
    return 400


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(e.DomainError)
    async def domain_error(_: Request, exc: e.DomainError) -> JSONResponse:
        return JSONResponse({"code": exc.code, "detail": exc.message}, _status_for(exc))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            {"code": "donnees_invalides", "detail": "Les données envoyées sont invalides.",
             "champs": [".".join(str(p) for p in err["loc"][1:]) for err in exc.errors()]},
            422,
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException):
        detail = {404: "Ressource introuvable.", 405: "Méthode non autorisée."}.get(
            exc.status_code, "Requête refusée.")
        if _wants_html(request):
            from ..web.routes import error_page

            title = "Page introuvable" if exc.status_code == 404 else "Requête refusée"
            return error_page(request, exc.status_code, title,
                              "La page demandée n'existe pas." if exc.status_code == 404 else detail)
        return JSONResponse({"code": "erreur_http", "detail": detail}, exc.status_code)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("Erreur inattendue")  # détails techniques : logs seulement
        return JSONResponse(
            {"code": "erreur_interne",
             "detail": "Une erreur interne est survenue. Consultez l'administrateur."}, 500)
