"""Robustesse des migrations : restes d'une exécution interrompue, doubles lancements, sauvegarde."""

import os
import sqlite3
import subprocess
import sys
import textwrap

import pytest
from alembic import command

from brikia.migrate import (
    alembic_config, backup_before_migration, migration_lock, repair_interrupted_batch, upgrade,
)


def _tables(path):
    con = sqlite3.connect(path)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        con.close()


def _at_0004(settings):
    settings.ensure_dirs()
    command.upgrade(alembic_config(settings), "0004")


def test_stale_tmp_table_from_interrupted_run_is_cleaned(settings):
    """Régression : « table _alembic_tmp_brick_shapes already exists » au démarrage."""
    _at_0004(settings)
    con = sqlite3.connect(settings.db_path)
    con.execute("CREATE TABLE _alembic_tmp_brick_shapes (id INTEGER PRIMARY KEY)")
    con.commit()
    con.close()
    upgrade(settings)
    names = _tables(settings.db_path)
    assert "_alembic_tmp_brick_shapes" not in names and "pricing_settings" in names
    con = sqlite3.connect(settings.db_path)
    assert con.execute("SELECT count(*) FROM brick_shapes").fetchone()[0] == 71
    con.close()


def test_original_table_lost_between_drop_and_rename_is_restored(settings):
    _at_0004(settings)
    con = sqlite3.connect(settings.db_path)
    con.execute("ALTER TABLE brick_shapes RENAME TO _alembic_tmp_brick_shapes")
    con.commit()
    con.close()
    assert repair_interrupted_batch(settings) == ["_alembic_tmp_brick_shapes restaurée en brick_shapes"]
    con = sqlite3.connect(settings.db_path)
    assert con.execute("SELECT count(*) FROM brick_shapes").fetchone()[0] == 6  # données intactes
    con.close()
    upgrade(settings)


def test_migration_is_idempotent_when_partly_applied(settings):
    """Colonnes déjà ajoutées mais version encore à 0004 (arrêt en cours de route)."""
    _at_0004(settings)
    con = sqlite3.connect(settings.db_path)
    con.execute("ALTER TABLE brick_shapes ADD COLUMN poids_g INTEGER")
    con.execute("ALTER TABLE projects ADD COLUMN devis JSON")
    con.commit()
    con.close()
    upgrade(settings)
    con = sqlite3.connect(settings.db_path)
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0008"
    assert con.execute("SELECT count(*) FROM pricing_settings").fetchone()[0] == 1
    con.close()
    upgrade(settings)  # rejouable sans effet


def test_database_copy_made_before_migrating_an_existing_base(settings):
    _at_0004(settings)
    con = sqlite3.connect(settings.db_path)
    con.execute("UPDATE brick_shapes SET nom = 'Nom saisi par le chef' WHERE code = 'BTC_STD'")
    con.commit()
    con.close()
    upgrade(settings)
    copies = list(settings.backups_dir.glob("avant-migration-0004-*.db"))
    assert len(copies) == 1
    old = sqlite3.connect(copies[0])
    assert old.execute("SELECT nom FROM brick_shapes WHERE code = 'BTC_STD'").fetchone()[0] \
        == "Nom saisi par le chef"
    assert "pricing_settings" not in _tables(copies[0])  # copie = état d'AVANT
    old.close()
    upgrade(settings)  # déjà à jour : pas de nouvelle copie
    assert len(list(settings.backups_dir.glob("avant-migration-*.db"))) == 1


def test_no_copy_for_a_brand_new_database_and_old_copies_are_pruned(settings):
    upgrade(settings)
    assert not list(settings.backups_dir.glob("avant-migration-*.db"))
    for i in range(8):
        (settings.backups_dir / f"avant-migration-0001-2026010{i}-000000.db").write_bytes(b"x")
    cfg = alembic_config(settings)
    command.downgrade(cfg, "0004")
    assert backup_before_migration(settings, cfg, "head") is not None
    assert len(list(settings.backups_dir.glob("avant-migration-*.db"))) == 5


def test_lock_serialises_two_processes_and_times_out(settings, tmp_path):
    settings.ensure_dirs()
    with migration_lock(settings):
        code = textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {str(os.path.join(os.getcwd(), 'backend'))!r})
            from brikia.config import Settings
            from brikia.migrate import migration_lock
            s = Settings(data_dir={str(settings.data_dir)!r})
            try:
                with migration_lock(s, timeout_s=1.5):
                    print("OBTENU")
            except RuntimeError as e:
                print("TIMEOUT", e)
        """)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                             env={**os.environ, "BRIKIA_DATA_DIR": str(settings.data_dir)},
                             timeout=60).stdout
        assert "TIMEOUT" in out and "OBTENU" not in out
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env={**os.environ, "BRIKIA_DATA_DIR": str(settings.data_dir)},
                         timeout=60).stdout
    assert "OBTENU" in out  # libéré après la sortie du bloc


@pytest.mark.parametrize("n", [3])
def test_concurrent_startups_all_succeed(settings, n):
    """Plusieurs lancements simultanés (installeur + raccourci) : aucun ne doit échouer."""
    code = textwrap.dedent(f"""
        import sys
        sys.path.insert(0, {str(os.path.join(os.getcwd(), 'backend'))!r})
        from brikia.config import get_settings
        from brikia.migrate import upgrade
        upgrade(get_settings())
        print("OK")
    """)
    env = {**os.environ, "BRIKIA_DATA_DIR": str(settings.data_dir)}
    procs = [subprocess.Popen([sys.executable, "-c", code], env=env, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, text=True) for _ in range(n)]
    results = [p.communicate(timeout=120) + (p.returncode,) for p in procs]
    assert all(rc == 0 and "OK" in out for out, err, rc in results), results
    assert "pricing_settings" in _tables(settings.db_path)
