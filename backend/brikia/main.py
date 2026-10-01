"""Fabrique de l'application FastAPI."""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pathlib import Path

from . import __version__
from .adapters.analyzers.dispatch import build_plan_analyzer
from .api import audit as audit_api
from .api import users as users_api
from .api import documents as documents_api
from .api import auth as auth_api
from .adapters.layout.rule_based import DefaultRuleBasedLayoutEngine
from .adapters.layout.rules_config import LayoutRules
from .api import layout as layout_api
from .adapters.production.simulated import SimulatedProductionGateway
from .api import molds as molds_api
from .api import production as production_api
from .api import projects as projects_api
from .api.errors import install_error_handlers
from .config import Settings, get_settings
from .db import init_db
from .logging_setup import setup_logging
from .services.auth import LoginThrottle
from .web import routes as web_routes

_STATIC = Path(__file__).parent / "static"

# CSP stricte : tout est servi localement (aucun CDN), aucun script inline.
_CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; "
        "script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings)
    init_db(settings)

    app = FastAPI(title="BrikIA", version=__version__, docs_url=None, redoc_url=None)
    app.state.settings = settings
    app.state.throttle = LoginThrottle()
    # Point unique de choix des adaptateurs (analyseur réel en phase 2).
    app.state.plan_analyzer = build_plan_analyzer(settings)
    rules = (LayoutRules.from_file(settings.layout_rules_file)
             if settings.layout_rules_file else LayoutRules())
    app.state.layout_engine = DefaultRuleBasedLayoutEngine(rules)
    # Phase 3 : RaspberryPiProductionGateway remplacera le simulateur ici.
    app.state.production_gateway = SimulatedProductionGateway(
        settings.sim_blocks_per_second, settings.sim_fault_at_percent)

    # Même origine pour l'UI et l'API : volontairement aucun CORS.
    if settings.allowed_hosts != ["*"]:
        app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_hosts)

    @app.middleware("http")
    async def security_headers(request: Request, call_next):  # noqa: ANN001
        response = await call_next(request)
        response.headers.setdefault("Content-Security-Policy", _CSP)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    install_error_handlers(app)
    app.include_router(auth_api.router)
    app.include_router(projects_api.router)
    app.include_router(molds_api.router)
    app.include_router(layout_api.router)
    app.include_router(production_api.router)
    app.include_router(audit_api.router)
    app.include_router(users_api.router)
    app.include_router(documents_api.router)

    app.include_router(web_routes.router)

    @app.get("/api/health", tags=["système"])
    def health() -> dict[str, str]:
        return {"statut": "ok", "version": __version__}

    app.mount("/static", StaticFiles(directory=_STATIC), name="static")
    return app
