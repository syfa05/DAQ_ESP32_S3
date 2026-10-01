import pytest

from brikia.db import session_scope
from brikia.models import BrickShape, LayoutRun, Project, ProductionOrder, ProductionOrderLine, Wall, WallAssignment

NEW = {"code": "btc_mini", "nom": "BTC demi", "produit": "BTC autobloquante",
       "role": "Demi-bloc", "categorie": "standard", "longueur_mm": 120}


def test_initial_library_is_seeded_by_migration(oper):
    o, _ = oper
    shapes = o.get("/api/moulds").json()
    codes = [s["code"] for s in shapes]
    assert codes[:6] == ["BTC_STD", "BTC_ANGLE", "BTC_CHAINAGE", "BTC_LINTEAU",
                         "PARP_STD", "PARP_ANGLE"]
    assert len(codes) == 23
    assert {s["produit"] for s in shapes} == {"BTC autobloquante", "Parpaing autobloquant"}
    assert all(s["disponible"] for s in shapes)
    by = {s["code"]: s for s in shapes}
    assert by["BTC_ANGLE"]["categorie"] == "angle"
    # Tous les types demandés sont présents, avec dimensions et poids.
    assert {s["categorie"] for s in shapes} >= {
        "standard", "creux", "demi", "trois_quarts", "angle", "angle_135", "te",
        "chainage", "chainage_h", "linteau", "appui", "pignon", "acrotere"}
    assert all(s["longueur_mm"] and s["largeur_mm"] and s["hauteur_mm"] and s["poids_g"]
               for s in shapes)
    assert (by["BTC_STD"]["longueur_mm"], by["BTC_STD"]["largeur_mm"],
            by["BTC_STD"]["hauteur_mm"]) == (300, 150, 100)


def test_both_roles_can_read(chef, oper):
    for c, _ in (chef, oper):
        assert c.get("/api/moulds").status_code == 200
        assert c.get("/api/moulds/1").json()["code"] == "BTC_STD"
    assert chef[0].get("/api/moulds/999").status_code == 404


def test_unauthenticated_refused(client):
    assert client.get("/api/moulds").status_code == 401


# --- CRUD chef de projet ---------------------------------------------------
def test_chef_full_crud(chef):
    c, csrf = chef
    r = c.post("/api/moulds", headers=csrf, json=NEW)
    assert r.status_code == 201
    s = r.json()
    assert s["code"] == "BTC_MINI" and s["disponible"] is True  # code normalisé
    sid = s["id"]

    r = c.put(f"/api/moulds/{sid}", headers=csrf, json={"nom": "BTC demi-bloc", "largeur_mm": 115})
    assert r.status_code == 200
    assert r.json()["nom"] == "BTC demi-bloc" and r.json()["largeur_mm"] == 115
    assert r.json()["longueur_mm"] == 120 and r.json()["code"] == "BTC_MINI"

    r = c.patch(f"/api/moulds/{sid}/disponibilite", headers=csrf, json={"disponible": False})
    assert r.json()["disponible"] is False
    assert c.get(f"/api/moulds/{sid}").json()["disponible"] is False
    r = c.patch(f"/api/moulds/{sid}/disponibilite", headers=csrf, json={"disponible": True})
    assert r.json()["disponible"] is True

    assert c.delete(f"/api/moulds/{sid}", headers=csrf).status_code == 204
    assert c.get(f"/api/moulds/{sid}").status_code == 404


def test_duplicate_code_refused_case_insensitive(chef):
    c, csrf = chef
    r = c.post("/api/moulds", headers=csrf, json={**NEW, "code": "btc_std"})
    assert r.status_code == 409 and "existe déjà" in r.json()["detail"]


@pytest.mark.parametrize("patch", [
    {"code": ""}, {"code": "avec espace"}, {"nom": ""}, {"produit": " "},
    {"categorie": "inconnue"}, {"longueur_mm": -5}, {"longueur_mm": 0},
])
def test_invalid_payload_refused(chef, patch):
    c, csrf = chef
    r = c.post("/api/moulds", headers=csrf, json={**NEW, **patch})
    assert r.status_code == 422 and "invalides" in r.json()["detail"]


def test_update_cannot_change_code_or_blank_required_fields(chef):
    c, csrf = chef
    c.put("/api/moulds/1", headers=csrf, json={"code": "AUTRE"})
    assert c.get("/api/moulds/1").json()["code"] == "BTC_STD"
    assert c.put("/api/moulds/1", headers=csrf, json={"nom": None}).status_code == 422
    assert c.put("/api/moulds/999", headers=csrf, json={"nom": "x"}).status_code == 404


def test_dimensions_optional(chef):
    c, csrf = chef
    r = c.post("/api/moulds", headers=csrf, json={"code": "X1", "nom": "X", "produit": "P"})
    assert r.status_code == 201 and r.json()["longueur_mm"] is None
    assert r.json()["categorie"] == "standard"


# --- Suppression protégée ---------------------------------------------------
def test_cannot_delete_shape_used_by_layout(chef):
    with session_scope() as s:
        p = Project(nom="P", status="a_valider")
        w = Wall(project=p, nom="M", longueur_mm=1000, hauteur_mm=1000)
        run = LayoutRun(project=p, engine="t")
        run.assignments.append(WallAssignment(wall=w, brick_shape_id=1, quantity=3))
        s.add(run)
    c, csrf = chef
    r = c.delete("/api/moulds/1", headers=csrf)
    assert r.status_code == 409 and "désactivez" in r.json()["detail"]
    assert c.get("/api/moulds/1").status_code == 200


def test_cannot_delete_shape_used_by_production(chef):
    with session_scope() as s:
        p = Project(nom="P", status="en_production")
        o = ProductionOrder(project=p)
        o.lines.append(ProductionOrderLine(brick_shape_id=2, target=5))
        s.add(o)
    c, csrf = chef
    assert c.delete("/api/moulds/2", headers=csrf).status_code == 409


# --- Permissions opérateur --------------------------------------------------
def test_operator_cannot_manage_molds(oper):
    o, csrf = oper
    assert o.post("/api/moulds", headers=csrf, json=NEW).status_code == 403
    assert o.put("/api/moulds/1", headers=csrf, json={"nom": "x"}).status_code == 403
    assert o.patch("/api/moulds/1/disponibilite", headers=csrf,
                   json={"disponible": False}).status_code == 403
    assert o.delete("/api/moulds/1", headers=csrf).status_code == 403
    with session_scope() as s:
        s1 = s.get(BrickShape, 1)
        assert s1.nom == "BTC standard" and s1.disponible
        assert s.query(BrickShape).count() == 23


def test_csrf_required_on_mold_writes(chef):
    c, _ = chef
    assert c.post("/api/moulds", json=NEW).status_code == 403


def test_molds_persist_across_restart(settings, chef):
    from brikia.db import init_db

    c, csrf = chef
    c.post("/api/moulds", headers=csrf, json=NEW)
    c.patch("/api/moulds/1/disponibilite", headers=csrf, json={"disponible": False})
    init_db(settings)
    shapes = c.get("/api/moulds").json()
    assert len(shapes) == 24 and shapes[0]["disponible"] is False
