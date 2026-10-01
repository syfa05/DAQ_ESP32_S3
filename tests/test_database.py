import sqlite3

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from brikia.models import (
    BrickShape, Opening, ProductionOrder, ProductionOrderLine, Project, User, Wall,
)

EXPECTED_TABLES = {
    "users", "user_sessions", "projects", "walls", "openings", "brick_shapes",
    "layout_runs", "wall_assignments", "production_orders",
    "production_order_lines", "action_logs", "pricing_settings", "alembic_version",
}


def test_migration_from_empty_db_creates_schema(db):
    assert set(inspect(db).get_table_names()) == EXPECTED_TABLES


def test_migrations_match_models(db):
    """Aucune dérive entre les modèles et la migration (autogenerate vide)."""
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext

    from brikia.models import Base

    with db.connect() as conn:
        ctx = MigrationContext.configure(conn, opts={"compare_type": True})
        diff = compare_metadata(ctx, Base.metadata)
    assert diff == []


def test_pragmas_applied(db):
    with db.connect() as conn:
        assert conn.execute(text("PRAGMA foreign_keys")).scalar() == 1
        assert conn.execute(text("PRAGMA journal_mode")).scalar() == "wal"


def test_foreign_keys_enforced(session):
    session.add(Wall(project_id=999, nom="M1", longueur_mm=1000, hauteur_mm=1000))
    with pytest.raises(IntegrityError):
        session.commit()


def test_check_constraints(session):
    session.add(User(nom="X", login="x", password_hash="h", role="pirate"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.add(Project(nom="P", status="nimporte_quoi"))
    with pytest.raises(IntegrityError):
        session.commit()


def test_cascade_delete_project_walls_openings(session):
    p = Project(nom="P")
    w = Wall(nom="M1", longueur_mm=4000, hauteur_mm=2500)
    w.openings.append(Opening(type="porte", largeur_mm=900, hauteur_mm=2100))
    p.walls.append(w)
    session.add(p)
    session.commit()
    session.delete(p)
    session.commit()
    assert session.query(Wall).count() == 0
    assert session.query(Opening).count() == 0


def test_persistence_across_engine_restart(settings, db):
    from brikia.db import init_db, session_scope

    with session_scope() as s:
        s.add(Project(nom="Persistant", ville="Abidjan"))
    init_db(settings)  # simule un redémarrage
    with session_scope() as s:
        assert s.query(Project).one().ville == "Abidjan"


def test_datetimes_are_utc_aware(session):
    p = Project(nom="P")
    session.add(p)
    session.commit()
    session.expire_all()
    assert session.get(Project, p.id).created_at.tzinfo is not None


def test_only_one_active_order_per_project(session):
    p = Project(nom="P")
    shape = BrickShape(code="S", nom="S", produit="X")
    session.add_all([p, shape])
    session.commit()
    session.add(ProductionOrder(project_id=p.id))
    session.commit()
    session.add(ProductionOrder(project_id=p.id))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    # Un ordre terminé n'empêche pas d'en créer un nouveau.
    first = session.query(ProductionOrder).one()
    first.status = "termine"
    session.commit()
    session.add(ProductionOrder(project_id=p.id))
    session.commit()


def test_order_line_produced_cannot_exceed_target(session):
    p = Project(nom="P")
    shape = BrickShape(code="S", nom="S", produit="X")
    o = ProductionOrder(project=p)
    o.lines.append(ProductionOrderLine(brick_shape=shape, target=10, produced=11))
    session.add(o)
    with pytest.raises(IntegrityError):
        session.commit()


def test_brick_shape_code_unique(session):
    session.add_all([BrickShape(code="A", nom="a", produit="p"),
                     BrickShape(code="A", nom="b", produit="p")])
    with pytest.raises(IntegrityError):
        session.commit()
