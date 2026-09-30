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


PASSWORD = "mot-de-passe-test-1"


@pytest.fixture
def users(db):
    from brikia.db import session_scope
    from brikia.domain.enums import Role
    from brikia.services.auth import create_user

    with session_scope() as s:
        create_user(s, nom="Awa Chef", login="chef", password=PASSWORD, role=Role.CHEF_PROJET)
        create_user(s, nom="Ibrahim Op", login="oper", password=PASSWORD, role=Role.OPERATEUR)
    return {"chef": "chef", "oper": "oper"}


@pytest.fixture
def app(settings, users):
    from brikia.main import create_app

    return create_app(settings)


@pytest.fixture
def client(app):
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c


def login(app, who: str, password: str = PASSWORD):
    """Retourne (client connecté, en-têtes CSRF)."""
    from fastapi.testclient import TestClient

    c = TestClient(app)
    r = c.post("/api/auth/login", json={"login": who, "password": password})
    assert r.status_code == 200, r.text
    return c, {"X-CSRF-Token": r.json()["csrf_token"]}


@pytest.fixture
def chef(app):
    return login(app, "chef")


@pytest.fixture
def oper(app):
    return login(app, "oper")
