"""Moteur SQLAlchemy et sessions.

Écrit pour SQLite mais sans logique spécifique dans le domaine : les PRAGMA
ne sont appliqués que si le dialecte est SQLite, ce qui laisse la porte
ouverte à PostgreSQL.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from .config import Settings, get_settings


def _install_sqlite_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_conn, _record):  # noqa: ANN001
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA busy_timeout=5000")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()


def make_engine(url: str) -> Engine:
    kwargs: dict = {}
    if url.startswith("sqlite"):
        # FastAPI exécute les endpoints sync dans un pool de threads.
        kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(url, **kwargs)
    if engine.dialect.name == "sqlite":
        _install_sqlite_pragmas(engine)
    return engine


_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def init_db(settings: Settings | None = None) -> Engine:
    """(Ré)initialise le moteur global depuis la configuration."""
    global _engine, _session_factory
    settings = settings or get_settings()
    settings.ensure_dirs()
    if _engine is not None:
        _engine.dispose()
    _engine = make_engine(settings.effective_database_url)
    _session_factory = sessionmaker(_engine, expire_on_commit=False)
    return _engine


def get_engine() -> Engine:
    if _engine is None:
        init_db()
    assert _engine is not None
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    if _session_factory is None:
        init_db()
    assert _session_factory is not None
    return _session_factory


@contextmanager
def session_scope() -> Iterator[Session]:
    """Transaction : commit si tout va bien, rollback sinon."""
    session = get_session_factory()()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()
