import threading

import pytest
from fastapi.testclient import TestClient

from brikia.adapters.production.base import GatewayReceipt
from brikia.adapters.production.simulated import SimulatedProductionGateway
from brikia.db import get_session_factory, init_db, session_scope
from brikia.domain.errors import Conflict
from brikia.models import ActionLog, ProductionOrder, ProductionOrderLine, Project, User
from brikia.services.production import start_production
from helpers import Clock, to_a_valider, to_valide


@pytest.fixture
def clock(app):
    """Simulateur à horloge maîtrisée : 10 blocs / seconde."""
    ck = Clock()
    app.state.production_gateway = SimulatedProductionGateway(10.0, None, ck)
    return ck


def _launch(oper, pid):
    o, csrf = oper
    r = o.post(f"/api/projects/{pid}/production", headers=csrf)
    assert r.status_code == 201, r.text
    return r.json()


def _logs(action):
    with session_scope() as s:
        return s.query(ActionLog).filter_by(action=action).all()


def _n_orders():
    with session_scope() as s:
        return s.query(ProductionOrder).count()


# --- Lancement ---------------------------------------------------------------
def test_operator_launches_production_for_validated_project(chef, oper, clock):
    c, csrf = chef
    pid = to_valide(c, csrf)
    bom = c.get(f"/api/projects/{pid}/bom").json()
    order = _launch(oper, pid)
    assert order["status"] == "en_cours" and order["project_id"] == pid
    assert order["simulation"] is True and order["progression_pct"] == 0
    assert {l["code"]: l["cible"] for l in order["lignes"]} == \
        {l["code"]: l["quantite_totale"] for l in bom["lignes"]}
    assert order["total_cible"] == bom["total_blocs"] and order["lot_id"]
    assert c.get(f"/api/projects/{pid}").json()["status"] == "en_production"


def test_launch_is_traced_with_operator_identity(chef, oper, clock):
    c, csrf = chef
    pid = to_valide(c, csrf)
    order = _launch(oper, pid)
    (entry,) = _logs("production.start")
    assert entry.user_id == 2 and entry.target_type == "production_order"
    assert entry.target_id == order["id"]
    assert entry.details["lot_id"] == order["lot_id"]
    assert entry.details["project_id"] == pid and entry.details["total_blocs"] > 0


def test_chef_cannot_launch_production(chef, clock):
    c, csrf = chef
    pid = to_valide(c, csrf)
    r = c.post(f"/api/projects/{pid}/production", headers=csrf)
    assert r.status_code == 403
    assert _n_orders() == 0 and c.get(f"/api/projects/{pid}").json()["status"] == "valide"


def test_unauthenticated_and_csrf(client, oper, chef, clock):
    assert client.post("/api/projects/1/production").status_code == 401
    c, csrf = chef
    pid = to_valide(c, csrf)
    o, _ = oper
    assert o.post(f"/api/projects/{pid}/production").status_code == 403  # sans CSRF
    assert _n_orders() == 0


@pytest.mark.parametrize("prep", ["a_analyser", "a_optimiser", "a_valider"])
def test_launch_refused_before_validation(chef, oper, clock, prep):
    c, csrf = chef
    with session_scope() as s:
        s.add(Project(nom="P", status=prep))
    o, ocsrf = oper
    # L'opérateur ne voit pas ce projet : 404. Le chef (pas opérateur) : 403.
    assert o.post("/api/projects/1/production", headers=ocsrf).status_code == 404
    assert _n_orders() == 0


def test_launch_refused_on_validated_only_via_state_machine(chef, oper, clock):
    """Projet visible mais dans un statut interdit : terminé -> refus explicite."""
    with session_scope() as s:
        s.add(Project(nom="Fini", status="termine"))
    o, csrf = oper
    r = o.post("/api/projects/1/production", headers=csrf)
    assert r.status_code == 409 and r.json()["code"] == "transition_interdite"
    assert _n_orders() == 0


def test_double_launch_is_refused_and_creates_one_order(chef, oper, clock):
    c, csrf = chef
    pid = to_valide(c, csrf)
    first = _launch(oper, pid)
    o, ocsrf = oper
    r = o.post(f"/api/projects/{pid}/production", headers=ocsrf)
    assert r.status_code == 409 and "déjà en cours" in r.json()["detail"]
    assert _n_orders() == 1 and len(_logs("production.start")) == 1
    assert o.get(f"/api/projects/{pid}/production").json()["id"] == first["id"]


def test_concurrent_launch_creates_exactly_one_order(app, chef, oper, clock):
    c, csrf = chef
    pid = to_valide(c, csrf)
    gateway, factory = app.state.production_gateway, get_session_factory()
    barrier, results = threading.Barrier(2), []

    def attempt():
        db = factory()
        try:
            user, project = db.get(User, 2), db.get(Project, pid)  # même statut lu par les 2
            barrier.wait()
            try:
                start_production(db, gateway, user, project)
                results.append("ok")
            except Conflict:
                results.append("conflit")
        finally:
            db.close()

    threads = [threading.Thread(target=attempt) for _ in range(2)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == ["conflit", "ok"]
    assert _n_orders() == 1 and len(_logs("production.start")) == 1


def test_database_forbids_two_active_orders(chef, oper, clock):
    """Dernier rempart : l'index unique refuse un 2e ordre actif même si le code échouait."""
    from sqlalchemy.exc import IntegrityError

    c, csrf = chef
    pid = to_valide(c, csrf)
    _launch(oper, pid)
    with pytest.raises(IntegrityError), session_scope() as s:
        s.add(ProductionOrder(project_id=pid))
        s.flush()
    assert _n_orders() == 1


def test_gateway_refusal_rolls_everything_back(app, chef, oper, clock):
    class Refusing:
        name = "refusing"

        def send_order(self, o):
            return GatewayReceipt(o.lot_id, False, "presse à l'arrêt")

        def get_status(self, lot_id):
            raise AssertionError("ne doit pas être appelé")

    app.state.production_gateway = Refusing()
    c, csrf = chef
    pid = to_valide(c, csrf)
    o, ocsrf = oper
    r = o.post(f"/api/projects/{pid}/production", headers=ocsrf)
    assert r.status_code == 503 and r.json()["code"] == "ligne_indisponible"
    assert _n_orders() == 0 and _logs("production.start") == []
    assert c.get(f"/api/projects/{pid}").json()["status"] == "valide"
    # Le projet peut être relancé une fois la ligne rétablie.
    app.state.production_gateway = SimulatedProductionGateway(10.0, None, clock)
    assert o.post(f"/api/projects/{pid}/production", headers=ocsrf).status_code == 201


def test_gateway_crash_is_contained(app, chef, oper, clock):
    class Crashing:
        name = "crashing"

        def send_order(self, o):
            raise ConnectionError("10.0.0.5 unreachable")

        def get_status(self, lot_id):
            raise ConnectionError("x")

    app.state.production_gateway = Crashing()
    c, csrf = chef
    pid = to_valide(c, csrf)
    o, ocsrf = oper
    r = o.post(f"/api/projects/{pid}/production", headers=ocsrf)
    assert r.status_code == 503 and "10.0.0.5" not in r.text
    assert _n_orders() == 0 and c.get(f"/api/projects/{pid}").json()["status"] == "valide"


# --- Progression et fin ------------------------------------------------------
def test_progress_is_visible_and_monotonic(chef, oper, clock):
    c, csrf = chef
    pid = to_valide(c, csrf)
    order = _launch(oper, pid)
    clock.t = __import__("datetime").datetime.fromisoformat(order["started_at"])
    o, _ = oper
    seen = []
    for _ in range(3):
        clock.advance(5)  # +50 blocs à 10/s
        r = o.get(f"/api/production/{order['id']}").json()
        seen.append(r["total_produit"])
        assert r["status"] == "en_cours"
        assert all(0 <= l["produite"] <= l["cible"] for l in r["lignes"])
    assert seen == [50, 100, 150]
    assert r["progression_pct"] == 150 * 100 // r["total_cible"]
    first = r["lignes"][0]
    assert first["produite"] == 150 and all(l["produite"] == 0 for l in r["lignes"][1:])


def test_production_completes_project_and_traces_once(chef, oper, clock):
    c, csrf = chef
    pid = to_valide(c, csrf)
    order = _launch(oper, pid)
    clock.t = __import__("datetime").datetime.fromisoformat(order["started_at"])
    o, _ = oper
    clock.advance(100_000)
    done = o.get(f"/api/production/{order['id']}").json()
    assert done["status"] == "termine" and done["completed_at"] is not None
    assert done["progression_pct"] == 100 and done["total_produit"] == done["total_cible"]
    assert all(l["produite"] == l["cible"] for l in done["lignes"])
    proj = c.get(f"/api/projects/{pid}").json()
    assert proj["status"] == "termine" and proj["completed_at"] is not None
    # Rafraîchissements répétés : pas de doublon, état stable.
    for _ in range(3):
        assert o.get(f"/api/production/{order['id']}").json() == done
        o.get("/api/production")
    (entry,) = _logs("production.complete")
    assert entry.user_id is None and entry.target_id == order["id"]  # événement système


def test_project_list_refreshes_finished_production(chef, oper, clock):
    c, csrf = chef
    pid = to_valide(c, csrf)
    order = _launch(oper, pid)
    clock.t = __import__("datetime").datetime.fromisoformat(order["started_at"])
    clock.advance(100_000)
    o, _ = oper
    assert [p["status"] for p in o.get("/api/projects").json()] == ["termine"]


def test_list_production_and_project_production(chef, oper, clock):
    c, csrf = chef
    pid = to_valide(c, csrf)
    order = _launch(oper, pid)
    for cli in (chef[0], oper[0]):
        rows = cli.get("/api/production").json()
        assert [r["id"] for r in rows] == [order["id"]]
        assert cli.get(f"/api/projects/{pid}/production").json()["id"] == order["id"]
    assert c.get("/api/production/999").status_code == 404


def test_project_without_production_returns_404(chef):
    c, csrf = chef
    pid = to_valide(c, csrf)
    r = c.get(f"/api/projects/{pid}/production")
    assert r.status_code == 404 and "Aucune production" in r.json()["detail"]


def test_simulated_fault_marks_order_in_error_without_finishing_project(app, chef, oper):
    ck = Clock()
    app.state.production_gateway = SimulatedProductionGateway(10.0, 50, ck)
    c, csrf = chef
    pid = to_valide(c, csrf)
    order = _launch(oper, pid)
    ck.t = __import__("datetime").datetime.fromisoformat(order["started_at"])
    ck.advance(100_000)
    o, _ = oper
    r = o.get(f"/api/production/{order['id']}").json()
    assert r["status"] == "erreur" and r["alarmes"] and "simulé" in r["alarmes"][0]
    assert 0 < r["total_produit"] < r["total_cible"]
    assert c.get(f"/api/projects/{pid}").json()["status"] == "en_production"
    frozen = o.get(f"/api/production/{order['id']}").json()
    assert frozen == r
    (entry,) = _logs("production.error")
    assert entry.user_id is None and entry.details["message"] == r["alarmes"][0]
    assert _logs("production.complete") == []


# --- Persistance / redémarrage -----------------------------------------------
def test_progress_survives_restart_of_app_and_simulator(app, settings, chef, oper, clock):
    c, csrf = chef
    pid = to_valide(c, csrf)
    order = _launch(oper, pid)
    started = __import__("datetime").datetime.fromisoformat(order["started_at"])
    clock.t = started
    clock.advance(5)
    o, _ = oper
    assert o.get(f"/api/production/{order['id']}").json()["total_produit"] == 50

    init_db(settings)  # redémarrage base
    app.state.production_gateway = SimulatedProductionGateway(10.0, None, clock)  # mémoire perdue
    clock.advance(5)  # 10 s au total depuis le lancement
    r = o.get(f"/api/production/{order['id']}").json()
    assert r["status"] == "en_cours" and r["total_produit"] == 100  # repris, non recommencé
    assert r["lot_id"] == order["lot_id"]


def test_produced_never_decreases_or_exceeds_target(app, chef, oper, clock):
    """Un état incohérent de la ligne ne doit pas corrompre la base."""
    c, csrf = chef
    pid = to_valide(c, csrf)
    order = _launch(oper, pid)
    from brikia.adapters.production.base import GatewayStatus

    class Weird:
        name = "weird"
        calls = 0

        def send_order(self, o):
            return GatewayReceipt(o.lot_id, True)

        def get_status(self, lot_id):
            Weird.calls += 1
            codes = [l["code"] for l in order["lignes"]]
            val = 30 if Weird.calls == 1 else 5  # régression puis...
            return GatewayStatus(lot_id, "en_cours", {}, {codes[0]: val, "INCONNU": 9})

    app.state.production_gateway = Weird()
    o, _ = oper
    assert o.get(f"/api/production/{order['id']}").json()["total_produit"] == 30
    assert o.get(f"/api/production/{order['id']}").json()["total_produit"] == 30  # pas de recul
    with session_scope() as s:
        assert all(l.produced <= l.target for l in s.query(ProductionOrderLine))


def test_status_endpoint_when_line_unavailable_is_503_and_data_intact(app, chef, oper, clock):
    c, csrf = chef
    pid = to_valide(c, csrf)
    order = _launch(oper, pid)

    class Down:
        name = "down"

        def send_order(self, o):
            raise ConnectionError("réseau")

        def get_status(self, lot_id):
            raise ConnectionError("réseau")

    app.state.production_gateway = Down()
    o, _ = oper
    r = o.get(f"/api/production/{order['id']}")
    assert r.status_code == 503 and r.json()["code"] == "ligne_indisponible"
    # La liste des projets reste consultable malgré la panne de la ligne.
    assert o.get("/api/projects").status_code == 200
    assert c.get(f"/api/projects/{pid}").json()["status"] == "en_production"
