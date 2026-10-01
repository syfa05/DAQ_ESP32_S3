"""Environnement Alembic : l'URL vient de la configuration BrikIA."""

from __future__ import annotations

from logging.config import fileConfig

from alembic import context

from brikia.config import get_settings
from brikia.db import make_engine
from brikia.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _url() -> str:
    # Permet aux tests / au CLI de forcer une URL via set_main_option.
    return config.get_main_option("sqlalchemy.url") or get_settings().effective_database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    get_settings().ensure_dirs()
    engine = make_engine(_url())
    with engine.connect() as connection:
        sqlite = connection.dialect.name == "sqlite"
        if sqlite:
            # Procédure SQLite pour modifier une table (DROP + RENAME) quand d'autres tables la
            # référencent : clés étrangères désactivées PENDANT la migration (sans effet dans une
            # transaction, donc avant), puis contrôle d'intégrité, puis réactivation.
            connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
            # Ferme la transaction « auto » ouverte par SQLAlchemy : sinon Alembic croit que la
            # transaction est externe et ne valide plus (commit) les migrations.
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,  # ALTER TABLE via recréation sous SQLite
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        if sqlite:
            broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
            if broken:
                raise RuntimeError(
                    f"Intégrité des données compromise après migration ({len(broken)} référence(s) "
                    "orpheline(s)). Une copie de la base d'avant migration est dans data/backups.")
            connection.exec_driver_sql("PRAGMA foreign_keys=ON")
            connection.commit()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
