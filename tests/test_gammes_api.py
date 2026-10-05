import io
from pathlib import Path

DXF = Path(__file__).parent / "fixtures" / "dxf" / "Demo - Restaurant (Template F0).dxf"
F3 = b"f3-2"


def _wall(c, pid, i=0):
    return c.get(f"/api/projects/{pid}").json()["walls"][i]


def _simulated(c, csrf):
    pid = c.post("/api/projects", headers=csrf, data={"nom": "Villa"},
                 files={"fichier": ("p.pdf", io.BytesIO(F3))}).json()["id"]
    c.post(f"/api/projects/{pid}/analyse", headers=csrf)
    return pid


def _put(c, csrf, pid, wall, **patch):
    body = {"nom": wall["nom"], "longueur_mm": wall["longueur_mm"], "hauteur_mm": wall["hauteur_mm"],
            "start_kind": wall["start_kind"], "end_kind": wall["end_kind"], "is_corner": wall["is_corner"],
            "thickness_mm": wall["thickness_mm"], "gamme": wall["gamme"], "openings": []}
    body.update(patch)
    return c.put(f"/api/projects/{pid}/murs/{wall['id']}", headers=csrf, json=body)


def test_gammes_endpoint_lists_all_families_complete(chef, oper):
    c, _ = chef
    g = c.get("/api/moulds/gammes").json()
    assert [(x["produit"][:3], x["largeur_mm"]) for x in g] == [
        ("BTC", 100), ("BTC", 150), ("BTC", 200), ("BTC", 300),
        ("Par", 100), ("Par", 150), ("Par", 200), ("Par", 300)]
    assert all(x["complete"] and x["manque"] == [] and x["nb_disponibles"] >= 8 for x in g)
    assert g[1]["cle"] == "BTC autobloquante|150"
    o, _ = oper
    assert o.get("/api/moulds/gammes").status_code == 200


def test_disabling_a_mold_marks_the_family_incomplete(chef):
    c, csrf = chef
    shapes = {s["code"]: s for s in c.get("/api/moulds").json()}
    c.patch(f"/api/moulds/{shapes['BTC_LINTEAU_200']['id']}/disponibilite", headers=csrf, json={"disponible": False})
    fam = next(x for x in c.get("/api/moulds/gammes").json() if x["cle"] == "BTC autobloquante|200")
    assert fam["complete"] is False and fam["manque"] == ["linteau"]


def test_wall_thickness_picks_the_family_in_the_real_layout(chef):
    c, csrf = chef
    pid = _simulated(c, csrf)
    w = _wall(c, pid)
    assert _put(c, csrf, pid, w, thickness_mm=200).status_code == 200
    lay = c.post(f"/api/projects/{pid}/calepinage", headers=csrf).json()
    mur = next(m for m in lay["murs"] if m["wall_id"] == w["id"])
    assert mur["quantites"] and all(q["code"].endswith("_200") for q in mur["quantites"])
    d = c.get(f"/api/projects/{pid}/calepinage/murs/{w['id']}").json()["detail"]
    assert d["gamme"] == "BTC autobloquante 200 mm" and d["gamme_origine"] == "epaisseur"
    assert d["epaisseur_mm"] == 200 and "BTC autobloquante 200 mm" in lay["parametres"]["gammes_utilisees"]
    # les autres murs (épaisseur inconnue) gardent la gamme par défaut (BTC 150)
    other = next(m for m in lay["murs"] if m["wall_id"] != w["id"])
    assert all(not q["code"].endswith(("_100", "_200", "_300")) for q in other["quantites"])


def test_forced_family_on_a_wall_and_validation_of_the_key(chef):
    c, csrf = chef
    pid = _simulated(c, csrf)
    w = _wall(c, pid)
    bad = _put(c, csrf, pid, w, gamme="BTC autobloquante|999")
    assert bad.status_code == 422 and "Gamme de moules inconnue" in bad.text
    ok = _put(c, csrf, pid, w, thickness_mm=200, gamme="Parpaing autobloquant|300")
    assert ok.status_code == 200 and ok.json()["gamme"] == "Parpaing autobloquant|300"
    c.post(f"/api/projects/{pid}/calepinage", headers=csrf)
    d = c.get(f"/api/projects/{pid}/calepinage/murs/{w['id']}").json()
    assert d["detail"]["gamme_origine"] == "manuelle"
    assert all(s["code"].startswith("PARP_") and s["code"].endswith("_300") for s in d["formes"])
    # retour à l'automatique
    assert _put(c, csrf, pid, w, thickness_mm=200, gamme=None).json()["gamme"] is None


def test_real_dxf_walls_get_their_own_families_from_their_thickness(chef):
    c, csrf = chef
    pid = c.post("/api/projects", headers=csrf, data={"nom": "Restaurant"},
                 files={"fichier": ("r.dxf", DXF.read_bytes())}).json()["id"]
    assert c.post(f"/api/projects/{pid}/analyse", headers=csrf).status_code == 200
    walls = c.get(f"/api/projects/{pid}").json()["walls"]
    assert {round(w["thickness_mm"], -1) for w in walls} == {100, 300}      # cloisons / murs extérieurs
    lay = c.post(f"/api/projects/{pid}/calepinage", headers=csrf).json()
    codes = {ln["code"] for ln in lay["bom"]["lignes"]}
    assert any(x.endswith("_100") for x in codes) and any(x.endswith("_300") for x in codes)
    assert not any(x.endswith("_200") for x in codes)
    assert sorted(lay["parametres"]["gammes_utilisees"]) == ["BTC autobloquante 100 mm", "BTC autobloquante 300 mm"]
    assert lay["avertissements"] == []


def test_rules_engine_ignores_families_and_keeps_working(chef, monkeypatch):
    # le moteur « regles » (ancien) n'utilise pas les gammes : il ne doit pas casser avec la bibliothèque étendue
    from brikia.adapters.layout.rule_based import DefaultRuleBasedLayoutEngine
    from brikia.domain.enums import ShapeCategory as C
    from brikia.domain.geometry import WallGeometry as W
    from brikia.domain.layout import BrickShapeInput as S
    from brikia.domain.layout import WallInput
    shapes = [S(1, "BTC_STD", "s", "BTC autobloquante", C.STANDARD, True, 300, 150, 100),
              S(2, "BTC_STD_200", "s2", "BTC autobloquante", C.STANDARD, True, 400, 200, 100)]
    r = DefaultRuleBasedLayoutEngine().calculate([WallInput(1, W("M", 3000, 1000))], shapes)
    assert set(r.walls[0].quantities) == {1}
