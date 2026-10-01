"""Migrations sur une base DÉJÀ remplie (projets, calepinages, productions)."""

import sqlite3

from alembic import command

from brikia.migrate import alembic_config, upgrade


def _populate_at_0004(settings):
    """Base à 0004 avec un projet, un calepinage et un ordre de production qui référencent des moules."""
    settings.ensure_dirs()
    command.upgrade(alembic_config(settings), "0004")
    con = sqlite3.connect(settings.db_path)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("INSERT INTO users (nom, login, password_hash, role, actif) "
                "VALUES ('Chef', 'chef', 'x', 'chef_projet', 1)")
    con.execute("INSERT INTO projects (nom, ville, architecte, status, created_at, created_by_id) "
                "VALUES ('Villa', '', '', 'valide', '2026-01-01 00:00:00+00:00', 1)")
    con.execute("INSERT INTO walls (project_id, nom, longueur_mm, hauteur_mm, is_corner) "
                "VALUES (1, 'M1', 4000, 2500, 0)")
    con.execute("INSERT INTO layout_runs (project_id, engine, parameters, warnings, "
                "estimated_duration_min, created_at) VALUES (1, 'e', '{}', '[]', 10, "
                "'2026-01-01 00:00:00+00:00')")
    con.execute("INSERT INTO wall_assignments (layout_run_id, wall_id, brick_shape_id, quantity) "
                "VALUES (1, 1, 1, 100)")
    con.commit()
    con.close()


def test_upgrade_keeps_existing_layouts_and_references(settings):
    """Régression : « FOREIGN KEY constraint failed » sur DROP TABLE brick_shapes."""
    _populate_at_0004(settings)
    upgrade(settings)
    con = sqlite3.connect(settings.db_path)
    con.execute("PRAGMA foreign_keys=ON")
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    assert con.execute("SELECT brick_shape_id, quantity FROM wall_assignments").fetchall() == [(1, 100)]
    assert con.execute("SELECT code, poids_g FROM brick_shapes WHERE id = 1").fetchone() == ("BTC_STD", 8550)
    assert con.execute("SELECT count(*) FROM brick_shapes").fetchone()[0] == 23
    assert con.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0007"
    # La contrainte reste active pour l'application : on ne peut pas supprimer un moule utilisé.
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        con.execute("DELETE FROM brick_shapes WHERE id = 1")
    con.close()


def test_downgrade_with_data_also_works(settings):
    _populate_at_0004(settings)
    upgrade(settings)
    command.downgrade(alembic_config(settings), "0004")
    con = sqlite3.connect(settings.db_path)
    con.execute("PRAGMA foreign_keys=ON")
    assert con.execute("PRAGMA foreign_key_check").fetchall() == []
    assert con.execute("SELECT count(*) FROM wall_assignments").fetchone()[0] == 1
    con.close()
