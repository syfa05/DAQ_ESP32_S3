"""Application des migrations Alembic depuis Python (CLI, tests, démarrage)."""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config

from .config import Settings, get_settings

# Racine du dépôt : backend/brikia/migrate.py -> ../../
_ROOT = Path(__file__).resolve().parents[2]


def alembic_config(settings: Settings | None = None) -> Config:
    settings = settings or get_settings()
    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "migrations"))
    # Le '%' est un caractère spécial de l'interpolation ConfigParser.
    cfg.set_main_option(
        "sqlalchemy.url", settings.effective_database_url.replace("%", "%%")
    )
    return cfg


def upgrade(settings: Settings | None = None, revision: str = "head") -> None:
    settings = settings or get_settings()
    settings.ensure_dirs()
    command.upgrade(alembic_config(settings), revision)
