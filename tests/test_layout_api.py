import io

import pytest
from fastapi.testclient import TestClient

from brikia.config import Settings
from brikia.db import init_db, session_scope
from brikia.main import create_app
from brikia.models import BrickShape, LayoutRun, Project, WallAssignment

@pytest.fixture(autouse=True)
def _rules_engine(monkeypatch):
    """Ces tests vérifient le moteur « regles » (estimation par surface) ; le moteur « assises »
    a ses propres tests (test_courses.py)."""
    monkeypatch.setenv("BRIKIA_LAYOUT_ENGINE", "regles")


F3 = b"f3-2"  # SHA-256 -> scénario « Maison type F3 » (6 murs)


def _analysed(c, csrf, content=F3):
    pid = c.post("/api/projects", headers=csrf, data={"nom": "Villa"},
                 files={"fichier": ("p.pdf", io.BytesIO(content))}).json()["id"]
    assert c.post(f"/api/projects/{pid}/analyse", headers=csrf).status_code == 200
    return pid


def _laid_out(c, csrf):
    pid = _analysed(c, csrf)
    r = c.post(f"/api/projects/{pid}/calepinage", headers=csrf)
    assert r.status_code == 200, r.text
    return pid, r.json()


def _set_status(pid, status):
    with session_scope() as s:
        s.get(Project, pid).status = status


def _qty(layout, wall_nom):
    wall = next(m for m in layout["murs"] if m["wall_nom"] == wall_nom)
    return {q["code"]: q["quantite"] for q in wall["quantites"]}


# --- Parcours nominal ---------------------------------------------------------
def test_layout_computes_assignments_bom_and_moves_to_a_valider(chef):
    c, csrf = chef
    pid, lay = _laid_out(c, csrf)
    assert c.get(f"/api/projects/{pid}").json()["status"] == "a_valider"
    assert len(lay["murs"]) == 6 and lay["avertissements"] == []
    assert lay["moteur"].startswith("default-rule-based")
    assert lay["parametres"]["temporaire"] is True
    # Façade nord (10000×2700, d'angle, 2 fenêtres 1200×1200), calcul à la main avec les
    # dimensions des moules BTC (300×150×100, linteau 450, appui 450) :
    # net 24 120 000 / 30 000 -> 804 -> ×1,05 = 845 ; angle 27 assises ; linteaux 2×4 = 8 ;
    # appuis 2×3 = 6 ; corps 804 ; chaînage 81 ; demi 49 ; standard 674.
    assert _qty(lay, "Façade nord") == {
        "BTC_STD": 674, "BTC_ANGLE": 27, "BTC_CHAINAGE": 81, "BTC_LINTEAU": 8,
        "BTC_DEMI": 49, "BTC_APPUI": 6}
    assert sum(_qty(lay, "Façade nord").values()) == 845


def test_bom_is_grouped_by_shape_and_consistent(chef):
    c, csrf = chef
    pid, lay = _laid_out(c, csrf)
    bom = c.get(f"/api/projects/{pid}/bom").json()
    assert bom == lay["bom"]
    assert [ln["code"] for ln in bom["lignes"]] == [
        "BTC_STD", "BTC_ANGLE", "BTC_CHAINAGE", "BTC_LINTEAU", "BTC_DEMI", "BTC_APPUI"]
    for ln in bom["lignes"]:
        assert ln["quantite_totale"] == sum(m["quantite"] for m in ln["par_mur"])
    assert bom["total_blocs"] == sum(m["total"] for m in lay["murs"]) \
        == sum(ln["quantite_totale"] for ln in bom["lignes"])
    assert bom["duree_estimee_min"] > 0 and bom["duree_indicative"] is True


def test_no_zero_quantity_rows_and_wall_without_opening(chef):
    c, csrf = chef
    _, lay = _laid_out(c, csrf)
    assert all(q["quantite"] > 0 for m in lay["murs"] for q in m["quantites"])
    # Refend sans angle ni fenêtre : pas de blocs d'angle, mais un linteau (porte).
    assert "BTC_ANGLE" not in _qty(lay, "Refend 1") and "BTC_LINTEAU" in _qty(lay, "Refend 1")
    assert set(_qty(lay, "Pignon ouest")) == {"BTC_STD", "BTC_ANGLE", "BTC_CHAINAGE", "BTC_DEMI"}


def test_layout_persists_across_restart(settings, chef):
    c, csrf = chef
    pid, lay = _laid_out(c, csrf)
    init_db(settings)
    assert c.get(f"/api/projects/{pid}/calepinage").json() == lay


# --- Recalcul / idempotence ---------------------------------------------------
def test_recalculation_replaces_previous_run_without_duplicates(chef):
    c, csrf = chef
    pid, first = _laid_out(c, csrf)
    with session_scope() as s:
        n = s.query(WallAssignment).count()
    second = c.post(f"/api/projects/{pid}/calepinage", headers=csrf).json()
    assert second["murs"] == first["murs"]  # déterministe (l'id peut être réutilisé par SQLite)
    with session_scope() as s:
        assert s.query(LayoutRun).count() == 1 and s.query(WallAssignment).count() == n
    assert c.get(f"/api/projects/{pid}").json()["status"] == "a_valider"


def test_recalculation_reflects_mold_availability(chef):
    c, csrf = chef
    pid, _ = _laid_out(c, csrf)
    c.patch("/api/moulds/2/disponibilite", headers=csrf, json={"disponible": False})  # BTC_ANGLE
    lay = c.post(f"/api/projects/{pid}/calepinage", headers=csrf).json()
    assert "PARP_ANGLE" in _qty(lay, "Façade nord") and "BTC_ANGLE" not in _qty(lay, "Façade nord")
    assert lay["avertissements"] and "Parpaing" in lay["avertissements"][0]
    assert lay["bom"]["avertissements"] == lay["avertissements"]


# --- Refus / garde-fous -----------------------------------------------------------
@pytest.mark.parametrize("status", ["a_analyser", "valide", "en_production", "termine"])
def test_layout_refused_outside_optimisation_phase(chef, status):
    c, csrf = chef
    with session_scope() as s:
        s.add(Project(nom="P", status=status))
    r = c.post("/api/projects/1/calepinage", headers=csrf)
    assert r.status_code == 409 and r.json()["code"] == "transition_interdite"


def test_no_standard_mold_leaves_project_unchanged(chef):
    c, csrf = chef
    pid = _analysed(c, csrf)
    for sid in (1, 5):  # BTC_STD, PARP_STD
        c.patch(f"/api/moulds/{sid}/disponibilite", headers=csrf, json={"disponible": False})
    r = c.post(f"/api/projects/{pid}/calepinage", headers=csrf)
    assert r.status_code == 409 and r.json()["code"] == "calepinage_impossible"
    assert c.get(f"/api/projects/{pid}").json()["status"] == "a_optimiser"
    assert c.get(f"/api/projects/{pid}/calepinage").status_code == 404


def test_engine_crash_is_contained(app, chef):
    class Broken:
        name = "broken"

        def calculate(self, walls, shapes):
            raise RuntimeError("secret interne SELECT")

    app.state.layout_engine = Broken()
    c, csrf = chef
    pid = _analysed(c, csrf)
    r = c.post(f"/api/projects/{pid}/calepinage", headers=csrf)
    assert r.status_code == 422 and "SELECT" not in r.text
    assert c.get(f"/api/projects/{pid}").json()["status"] == "a_optimiser"
    with session_scope() as s:
        assert s.query(LayoutRun).count() == 0


@pytest.mark.parametrize("bad", ["missing_wall", "negative", "unknown_shape"])
def test_invalid_engine_output_is_rejected(app, chef, bad):
    from brikia.domain.layout import LayoutResult, WallLayout

    class Bad:
        name = "bad"

        def calculate(self, walls, shapes):
            ws = [WallLayout(w.id, {shapes[0].id: 5}) for w in walls]
            if bad == "missing_wall":
                ws = ws[:-1]
            elif bad == "negative":
                ws[0] = WallLayout(ws[0].wall_id, {shapes[0].id: -1})
            else:
                ws[0] = WallLayout(ws[0].wall_id, {9999: 1})
            return LayoutResult("bad", tuple(ws))

    app.state.layout_engine = Bad()
    c, csrf = chef
    pid = _analysed(c, csrf)
    assert c.post(f"/api/projects/{pid}/calepinage", headers=csrf).status_code == 422
    with session_scope() as s:
        assert s.query(LayoutRun).count() == 0 and s.query(WallAssignment).count() == 0
    assert c.get(f"/api/projects/{pid}").json()["status"] == "a_optimiser"


def test_rollback_when_persistence_fails_midway(chef, monkeypatch):
    from brikia.services import layout

    def boom(*a, **k):
        raise RuntimeError("panne disque")

    c, csrf = chef
    pid = _analysed(c, csrf)
    monkeypatch.setattr(layout, "WallAssignment", boom)
    r = TestClient(c.app, raise_server_exceptions=False, cookies=c.cookies).post(
        f"/api/projects/{pid}/calepinage", headers=csrf)
    assert r.status_code == 500 and "disque" not in r.text
    monkeypatch.undo()
    assert c.get(f"/api/projects/{pid}").json()["status"] == "a_optimiser"
    with session_scope() as s:
        assert s.query(LayoutRun).count() == 0


def test_get_before_layout_is_404_with_message(chef):
    c, csrf = chef
    pid = _analysed(c, csrf)
    r = c.get(f"/api/projects/{pid}/bom")
    assert r.status_code == 404 and "Aucun calepinage" in r.json()["detail"]
    assert c.get("/api/projects/999/calepinage").status_code == 404


# --- Permissions ------------------------------------------------------------------
def test_operator_cannot_run_layout(chef, oper):
    c, csrf = chef
    pid = _analysed(c, csrf)
    o, ocsrf = oper
    assert o.post(f"/api/projects/{pid}/calepinage", headers=ocsrf).status_code == 403
    assert c.get(f"/api/projects/{pid}").json()["status"] == "a_optimiser"


def test_operator_sees_layout_and_bom_only_of_validated_projects(chef, oper):
    c, csrf = chef
    pid, _ = _laid_out(c, csrf)
    o, _ = oper
    assert o.get(f"/api/projects/{pid}/bom").status_code == 404  # a_valider : invisible
    assert o.get(f"/api/projects/{pid}/calepinage").status_code == 404
    _set_status(pid, "valide")
    assert o.get(f"/api/projects/{pid}/bom").status_code == 200
    assert o.get(f"/api/projects/{pid}/calepinage").status_code == 200


def test_unauthenticated_and_csrf(client, chef):
    assert client.post("/api/projects/1/calepinage").status_code == 401
    assert client.get("/api/projects/1/bom").status_code == 401
    c, _ = chef
    assert c.post("/api/projects/1/calepinage").status_code == 403


# --- Configuration des règles ------------------------------------------------------
def test_rules_file_setting_is_applied(settings, users, tmp_path):
    f = tmp_path / "rules.json"
    f.write_text('{"waste_margin": "0.10"}')
    s = Settings(_env_file=None, data_dir=settings.data_dir, layout_rules_file=f)
    app = create_app(s)
    from decimal import Decimal
    assert app.state.layout_engine.rules.waste_margin == Decimal("0.10")
