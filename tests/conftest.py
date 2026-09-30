from __future__ import annotations

import pytest

from brikia import config as config_mod
from brikia.config import Settings
from brikia.db import init_db
from brikia.migrate import upgrade


@pytest.fixture
def settings(tmp_path, monkeypatch) -> Settings:
    """Configuration isolée : données dans un répertoire temporaire."""
    monkeypatch.setenv("BRIKIA_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.delenv("BRIKIA_DATABASE_URL", raising=False)
    config_mod.get_settings.cache_clear()
    s = config_mod.get_settings()
    yield s
    config_mod.get_settings.cache_clear()


@pytest.fixture
def db(settings):
    """Base migrée par Alembic (valide aussi les migrations)."""
    upgrade(settings)
    engine = init_db(settings)
    yield engine
    engine.dispose()


@pytest.fixture
def session(db):
    from brikia.db import get_session_factory

    with get_session_factory()() as s:
        yield s
