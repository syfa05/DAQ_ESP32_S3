import io

import pytest

F3 = b"f3-2"  # scénario simulé « Maison type F3 » (6 murs, ouvertures sans position)


def _laid_out(c, csrf, content=F3):
    pid = c.post("/api/projects", headers=csrf, data={"nom": "Villa"},
                 files={"fichier": ("p.pdf", io.BytesIO(content))}).json()["id"]
    c.post(f"/api/projects/{pid}/analyse", headers=csrf)
    r = c.post(f"/api/projects/{pid}/calepinage", headers=csrf)
    assert r.status_code == 200, r.text
    return pid, r.json()


def test_default_engine_is_course_by_course_and_returns_indicators(chef):
    c, csrf = chef
    pid, lay = _laid_out(c, csrf)
    assert lay["moteur"].startswith("assises") and lay["detail_disponible"] is True
    assert lay["parametres"]["moteur"] == "assises"
    assert set(lay["indicateurs"]) == {"pieces_coupees", "chutes_totales_m"}
    assert lay["bom"]["total_blocs"] == sum(m["total"] for m in lay["murs"]) > 0


def test_wall_detail_endpoint_and_consistency_with_quantities(chef, oper):
    c, csrf = chef
    pid, lay = _laid_out(c, csrf)
    for mur in lay["murs"]:
        r = c.get(f"/api/projects/{pid}/calepinage/murs/{mur['wall_id']}")
        assert r.status_code == 200
        body = r.json()
        d, shapes = body["detail"], {s["id"]: s for s in body["formes"]}
        assert d["assises"] > 0 and len(d["courses"]) == d["assises"]
        laid = {}
        for runs in d["courses"]:
            assert sum(plen * n for _, _, plen, n, _ in runs) == d["longueur_mm"]
            for _, shape, _, n, _ in runs:
                if shape:
                    assert shape in shapes and shapes[shape]["categorie"]
                    laid[shape] = laid.get(shape, 0) + n
        produce = {q["shape_id"]: q["quantite"] for q in mur["quantites"]}
        assert set(produce) == set(laid)
        assert all(produce[s] >= laid[s] for s in laid)  # à produire = pose + marge de casse
    o, _ = oper
    wid = lay["murs"][0]["wall_id"]
    assert o.get(f"/api/projects/{pid}/calepinage/murs/{wid}").status_code == 404  # pas encore validé
    assert c.post(f"/api/projects/{pid}/validation", headers=csrf).status_code == 200
    assert o.get(f"/api/projects/{pid}/calepinage/murs/{wid}").status_code == 200


def test_simulated_openings_are_flagged_as_auto_placed(chef):
    c, csrf = chef
    pid, lay = _laid_out(c, csrf)
    notes = []
    for mur in lay["murs"]:
        notes += c.get(f"/api/projects/{pid}/calepinage/murs/{mur['wall_id']}").json()["detail"]["notes"]
    assert any("placée(s) automatiquement" in n for n in notes)


def test_wall_detail_unknown_wall_and_other_project(chef):
    c, csrf = chef
    pid, lay = _laid_out(c, csrf)
    assert c.get(f"/api/projects/{pid}/calepinage/murs/9999").status_code == 404
    pid2, lay2 = _laid_out(c, csrf)
    other_wall = lay2["murs"][0]["wall_id"]
    assert c.get(f"/api/projects/{pid}/calepinage/murs/{other_wall}").status_code == 404


def test_recompute_replaces_detail_and_disabling_a_mold_changes_it(chef):
    c, csrf = chef
    pid, lay = _laid_out(c, csrf)
    before = c.get(f"/api/projects/{pid}/calepinage/murs/{lay['murs'][0]['wall_id']}").json()["detail"]
    c.patch("/api/moulds/3/disponibilite", headers=csrf, json={"disponible": False})  # BTC_CHAINAGE
    r = c.post(f"/api/projects/{pid}/calepinage", headers=csrf).json()
    after = c.get(f"/api/projects/{pid}/calepinage/murs/{r['murs'][0]['wall_id']}").json()["detail"]
    assert before["courses"] != after["courses"]
    assert any("chaînage" in n for n in after["notes"]) or "BTC_CHAINAGE" not in str(after)


def test_rules_engine_still_available_and_has_no_detail(settings, monkeypatch):
    monkeypatch.setenv("BRIKIA_LAYOUT_ENGINE", "regles")
    from brikia import config
    config.get_settings.cache_clear()
    from conftest import login
    from brikia.main import create_app
    from brikia.db import session_scope
    from brikia.domain.enums import Role
    from brikia.services.auth import create_user
    from brikia.migrate import upgrade
    from brikia.db import init_db
    upgrade(settings)
    init_db(settings)
    with session_scope() as s:
        create_user(s, nom="Chef", login="chef", password="mot-de-passe-test-1", role=Role.CHEF_PROJET)
    app = create_app(config.get_settings())
    c, csrf = login(app, "chef")
    pid, lay = _laid_out(c, csrf)
    assert lay["moteur"].startswith("default-rule-based") and lay["detail_disponible"] is False
    assert c.get(f"/api/projects/{pid}/calepinage/murs/{lay['murs'][0]['wall_id']}").status_code == 404


def test_pdf_report_contains_course_by_course_section(chef):
    from pypdf import PdfReader
    c, csrf = chef
    pid, lay = _laid_out(c, csrf)
    r = c.get(f"/api/projects/{pid}/rapport.pdf")
    assert r.status_code == 200
    text = "\n".join(p.extract_text() for p in PdfReader(io.BytesIO(r.content)).pages)
    assert "Calepinage assise par assise" in text and "assises" in text and "coupe(s)" in text
    assert lay["murs"][0]["wall_nom"] in text
