import logging
import sqlite3

import pytest
from fastapi.testclient import TestClient

from brikia.cli import main
from brikia.db import session_scope
from brikia.models import ActionLog, BrickShape, LayoutRun, ProductionOrder, Project, User, Wall
from brikia.seed import DEMO_PREFIX, DEMO_PROJECTS, seed_demo
from conftest import login


@pytest.fixture
def seeded(settings, db, monkeypatch):
    monkeypatch.delenv("BRIKIA_SEED_CHEF_PASSWORD", raising=False)
    monkeypatch.delenv("BRIKIA_SEED_OPERATEUR_PASSWORD", raising=False)
    with session_scope() as s:
        return seed_demo(s, settings)


@pytest.fixture
def seed_app(settings, seeded):
    """Application sans les comptes de test standards (le seed crée les siens)."""
    from brikia.main import create_app

    return create_app(settings)


def test_one_project_per_status(seeded):
    with session_scope() as s:
        statuses = sorted(p.status for p in s.query(Project))
    assert statuses == sorted(["a_analyser", "a_optimiser", "a_valider", "valide",
                               "en_production", "termine"])
    assert all(n.startswith(DEMO_PREFIX) for n in seeded.created_projects)
    assert len(seeded.created_projects) == 6


def test_accounts_created_with_both_roles(seeded):
    with session_scope() as s:
        roles = {u.login: u.role for u in s.query(User)}
    assert roles == {"chef": "chef_projet", "operateur": "operateur"}
    assert set(seeded.new_passwords) == {"chef", "operateur"}


def test_generated_passwords_work_and_are_never_stored_in_clear(settings, seeded, seed_app):
    pw = seeded.new_passwords
    assert len(set(pw.values())) == 2 and all(len(p) >= 12 for p in pw.values())
    login(seed_app, "chef", pw["chef"])
    login(seed_app, "operateur", pw["operateur"])
    con = sqlite3.connect(settings.db_path)
    dump = "\n".join(con.iterdump())
    con.close()
    assert not any(p in dump for p in pw.values()) and "$argon2" in dump


def test_passwords_can_come_from_configuration(settings, db):
    """Variables d'environnement ou fichier .env (via la configuration)."""
    from brikia.config import Settings

    configured = Settings(_env_file=None, data_dir=settings.data_dir,
                          seed_chef_password="mot-de-passe-choisi-1",
                          seed_operateur_password="mot-de-passe-choisi-2")
    with session_scope() as s:
        rep = seed_demo(s, configured)
    assert rep.new_passwords == {"chef": "mot-de-passe-choisi-1",
                                 "operateur": "mot-de-passe-choisi-2"}


def test_passwords_not_leaked_to_technical_logs(settings, db, caplog, monkeypatch):
    monkeypatch.delenv("BRIKIA_SEED_CHEF_PASSWORD", raising=False)
    with caplog.at_level(logging.DEBUG), session_scope() as s:
        rep = seed_demo(s, settings)
    assert not any(p in caplog.text for p in rep.new_passwords.values())


def test_seed_is_idempotent(settings, seeded):
    with session_scope() as s:
        before = (s.query(Project).count(), s.query(User).count(), s.query(ActionLog).count())
        again = seed_demo(s, settings)
    assert again.created_projects == [] and again.new_passwords == {}
    assert len(again.skipped_projects) == 6 and set(again.existing_users) == {"chef", "operateur"}
    with session_scope() as s:
        assert (s.query(Project).count(), s.query(User).count(),
                s.query(ActionLog).count()) == before


def test_seed_data_is_consistent_with_the_workflow(seeded):
    with session_scope() as s:
        by = {p.status: p for p in s.query(Project)}
        assert by["a_analyser"].walls == []
        assert by["a_optimiser"].walls and not by["a_optimiser"].layout_runs
        assert by["a_valider"].layout_runs and by["a_valider"].validated_at is None
        for st in ("valide", "en_production", "termine"):
            assert by[st].validated_at is not None
        active = s.query(ProductionOrder).filter_by(project_id=by["en_production"].id).one()
        assert active.status == "en_cours"
        done = s.query(ProductionOrder).filter_by(project_id=by["termine"].id).one()
        assert done.status == "termine" and by["termine"].completed_at is not None
        assert all(l.produced == l.target for l in done.lines)
        assert s.query(LayoutRun).count() == 4  # a_valider, valide, en_production, termine


def test_action_log_populated_by_the_real_workflow(seeded):
    with session_scope() as s:
        actions = sorted(e.action for e in s.query(ActionLog))
    assert actions == sorted(["project.validate"] * 3 + ["production.start"] * 2
                             + ["production.complete"])


def test_scenarios_are_varied_and_molds_untouched(seeded):
    with session_scope() as s:
        counts = {len(p.walls) for p in s.query(Project) if p.walls}
        assert counts == {6, 4, 3}  # F3, local commercial, clôture
        assert s.query(BrickShape).count() == 23


def test_each_role_sees_the_right_projects_through_the_ui_api(seed_app, seeded):
    chef, _ = login(seed_app, "chef", seeded.new_passwords["chef"])
    oper, _ = login(seed_app, "operateur", seeded.new_passwords["operateur"])
    assert len(chef.get("/api/projects").json()) == 6
    assert {p["status"] for p in oper.get("/api/projects").json()} == \
        {"valide", "en_production", "termine"}


def test_cli_seed_prints_passwords_once(settings, capsys, monkeypatch):
    monkeypatch.delenv("BRIKIA_SEED_CHEF_PASSWORD", raising=False)
    assert main(["seed"]) == 0
    out = capsys.readouterr().out
    assert "UNE SEULE FOIS" in out and "chef" in out and "operateur" in out
    assert main(["seed"]) == 0
    out2 = capsys.readouterr().out
    assert "mot de passe inchangé" in out2 and "UNE SEULE FOIS" not in out2


def test_cli_seed_rejects_too_short_env_password(settings, capsys, monkeypatch):
    from brikia import config

    monkeypatch.setenv("BRIKIA_SEED_CHEF_PASSWORD", "court")
    config.get_settings.cache_clear()
    assert main(["seed"]) == 1
    assert "au moins" in capsys.readouterr().err
