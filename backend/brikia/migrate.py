"""Application des migrations Alembic depuis Python (CLI, tests, démarrage).

Robustesse (SQLite n'a pas de DDL transactionnel : une migration interrompue laisse des restes) :
* un verrou de fichier empêche deux processus de migrer en même temps (le second attend, puis
  constate que la base est déjà à jour) ;
* les tables temporaires ``_alembic_tmp_*`` laissées par une exécution interrompue sont réparées ;
* une copie de la base est faite avant toute migration d'une base existante
  (``data/backups/avant-migration-*.db``, les 5 dernières sont conservées).
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
import time
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

from .config import Settings, get_settings

log = logging.getLogger("brikia.migrate")

# Racine du dépôt : backend/brikia/migrate.py -> ../../
_ROOT = Path(__file__).resolve().parents[2]
_KEEP_PRE_MIGRATION_COPIES = 5
_LOCK_TIMEOUT_S = 180


def alembic_config(settings: Settings | None = None) -> Config:
    settings = settings or get_settings()
    cfg = Config(str(_ROOT / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ROOT / "migrations"))
    # Le '%' est un caractère spécial de l'interpolation ConfigParser.
    cfg.set_main_option(
        "sqlalchemy.url", settings.effective_database_url.replace("%", "%%")
    )
    return cfg


# --- verrou inter-processus -------------------------------------------------------------------
def _try_lock(f) -> None:  # noqa: ANN001
    try:
        import msvcrt  # Windows

        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except ImportError:
        import fcntl

        fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock(f) -> None:  # noqa: ANN001
    try:
        import msvcrt

        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
    except ImportError:
        import fcntl

        fcntl.flock(f.fileno(), fcntl.LOCK_UN)


@contextlib.contextmanager
def migration_lock(settings: Settings, timeout_s: float = _LOCK_TIMEOUT_S) -> Iterator[None]:
    settings.ensure_dirs()
    f = open(settings.data_dir / ".migration.lock", "a+b")  # noqa: SIM115
    try:
        if f.tell() == 0 and not f.read(1):
            f.write(b"0")
            f.flush()
        deadline = time.monotonic() + timeout_s
        while True:
            try:
                _try_lock(f)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError(
                        "Une autre instance de BrikIA met la base à jour (délai dépassé). "
                        "Fermez les autres fenêtres BrikIA puis réessayez.") from None
                time.sleep(0.5)
        try:
            yield
        finally:
            _unlock(f)
    finally:
        f.close()


# --- réparation / sauvegarde (SQLite) ------------------------------------------------------------
def _is_sqlite(settings: Settings) -> bool:
    return settings.effective_database_url.startswith("sqlite")


def repair_interrupted_batch(settings: Settings) -> list[str]:
    """Supprime les tables temporaires d'une migration interrompue.

    Cas normal : la table d'origine existe encore -> la copie temporaire est inutile.
    Cas grave (arrêt entre « DROP » et « RENAME ») : la table d'origine a disparu -> la copie
    temporaire, complète, est renommée.
    """
    if not _is_sqlite(settings) or not settings.db_path.exists():
        return []
    done: list[str] = []
    con = sqlite3.connect(settings.db_path)
    try:
        names = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
        for tmp in sorted(n for n in names if n.startswith("_alembic_tmp_")):
            original = tmp.removeprefix("_alembic_tmp_")
            if original in names:
                con.execute(f'DROP TABLE "{tmp}"')
                done.append(f"{tmp} supprimée")
            else:
                con.execute(f'ALTER TABLE "{tmp}" RENAME TO "{original}"')
                done.append(f"{tmp} restaurée en {original}")
        con.commit()
    finally:
        con.close()
    for line in done:
        log.warning("Migration interrompue précédemment : %s", line)
    return done


def _current_revision(settings: Settings) -> str | None:
    if not _is_sqlite(settings) or not settings.db_path.exists():
        return None
    con = sqlite3.connect(settings.db_path)
    try:
        row = con.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    except sqlite3.OperationalError:
        return None
    finally:
        con.close()


def backup_before_migration(settings: Settings, cfg: Config, target: str) -> Path | None:
    current = _current_revision(settings)
    wanted = ScriptDirectory.from_config(cfg).get_current_head() if target == "head" else target
    if current is None or current == wanted:
        return None
    dest = settings.backups_dir / f"avant-migration-{current}-{datetime.now():%Y%m%d-%H%M%S}.db"
    src = sqlite3.connect(settings.db_path)
    try:
        dst = sqlite3.connect(dest)
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    old = sorted(settings.backups_dir.glob("avant-migration-*.db"))
    for stale in old[:-_KEEP_PRE_MIGRATION_COPIES]:
        stale.unlink(missing_ok=True)
    log.info("Copie de sécurité avant migration : %s", dest)
    return dest


def upgrade(settings: Settings | None = None, revision: str = "head") -> None:
    settings = settings or get_settings()
    settings.ensure_dirs()
    cfg = alembic_config(settings)
    with migration_lock(settings):
        repair_interrupted_batch(settings)
        backup_before_migration(settings, cfg, revision)
        command.upgrade(cfg, revision)
