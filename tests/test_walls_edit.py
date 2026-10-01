import io

import pytest

F3 = b"f3-2"
OK = {"nom": "Mur corrigé", "longueur_mm": 6000, "hauteur_mm": 2500, "start_kind": "angle",
      "end_kind": "butee", "junctions_mm": [3000], "thickness_mm": 150,
      "openings": [{"type": "fenetre", "largeur_mm": 1200, "hauteur_mm": 1200, "x_mm": 1500, "sill_mm": 900},
                   {"type": "porte", "largeur_mm": 900, "hauteur_mm": 2100}]}


def _project(c, csrf, laid=True, validate=False):
    pid = c.post("/api/projects", headers=csrf, data={"nom": "Villa"},
                 files={"fichier": ("p.pdf", io.BytesIO(F3))}).json()["id"]
    c.post(f"/api/projects/{pid}/analyse", headers=csrf)
    if laid:
        assert c.post(f"/api/projects/{pid}/calepinage", headers=csrf).status_code == 200
    if validate:
        assert c.post(f"/api/projects/{pid}/validation", headers=csrf).status_code == 200
    return pid


def _walls(c, pid):
    return c.get(f"/api/projects/{pid}").json()["walls"]


def test_update_wall_replaces_fields_and_openings_and_flags_manual(chef):
    c, csrf = chef
    pid = _project(c, csrf, laid=False)
    wid = _walls(c, pid)[0]["id"]
    r = c.put(f"/api/projects/{pid}/murs/{wid}", headers=csrf, json=OK)
    assert r.status_code == 200, r.text
    w = r.json()
    assert (w["nom"], w["longueur_mm"], w["start_kind"], w["end_kind"], w["junctions_mm"]) == (
        "Mur corrigé", 6000, "angle", "butee", [3000])
    assert w["manuel"] is True and w["is_corner"] is True and w["thickness_mm"] == 150
    assert [(o["type"], o["x_mm"], o["sill_mm"], o["manuel"]) for o in w["openings"]] == [
        ("fenetre", 1500, 900, True), ("porte", None, None, True)]
    project = c.get(f"/api/projects/{pid}").json()
    assert any("Plan corrigé à la main : 1 mur(s)" in n for n in project["analysis_notes"])


def test_edit_invalidates_layout_and_sends_validated_to_optimise(chef):
    c, csrf = chef
    pid = _project(c, csrf)                                        # a_valider avec calepinage
    assert c.get(f"/api/projects/{pid}").json()["status"] == "a_valider"
    wid = _walls(c, pid)[0]["id"]
    assert c.put(f"/api/projects/{pid}/murs/{wid}", headers=csrf, json=OK).status_code == 200
    assert c.get(f"/api/projects/{pid}").json()["status"] == "a_optimiser"
    assert c.get(f"/api/projects/{pid}/calepinage").status_code == 404      # caduc
    assert c.post(f"/api/projects/{pid}/calepinage", headers=csrf).status_code == 200  # recalculable
    lay = c.get(f"/api/projects/{pid}/calepinage").json()
    assert lay["detail_disponible"] is True


def test_recomputed_layout_uses_the_manual_geometry(chef):
    c, csrf = chef
    pid = _project(c, csrf, laid=False)
    wid = _walls(c, pid)[0]["id"]
    c.put(f"/api/projects/{pid}/murs/{wid}", headers=csrf, json=OK)
    c.post(f"/api/projects/{pid}/calepinage", headers=csrf)
    d = c.get(f"/api/projects/{pid}/calepinage/murs/{wid}").json()["detail"]
    assert d["longueur_mm"] == 6000 and d["extremites"] == {"debut": "angle", "fin": "butee"}
    assert d["jonctions"] == [3000]
    win = next(o for o in d["ouvertures"] if o["type"] == "fenetre")
    assert (win["x"], win["allege"], win["position_estimee"]) == (1500, 900, False)


def test_create_and_delete_wall(chef):
    c, csrf = chef
    pid = _project(c, csrf, laid=False)
    n = len(_walls(c, pid))
    r = c.post(f"/api/projects/{pid}/murs", headers=csrf, json=OK)
    assert r.status_code == 201 and len(_walls(c, pid)) == n + 1
    assert c.delete(f"/api/projects/{pid}/murs/{r.json()['id']}", headers=csrf).status_code == 204
    assert len(_walls(c, pid)) == n


def test_delete_wall_with_existing_layout(chef):
    c, csrf = chef
    pid = _project(c, csrf)                                        # calepinage existant
    wid = _walls(c, pid)[0]["id"]
    assert c.delete(f"/api/projects/{pid}/murs/{wid}", headers=csrf).status_code == 204
    assert c.get(f"/api/projects/{pid}").json()["status"] == "a_optimiser"


def test_cannot_delete_the_last_wall(chef):
    c, csrf = chef
    pid = _project(c, csrf, laid=False)
    ids = [w["id"] for w in _walls(c, pid)]
    for wid in ids[:-1]:
        assert c.delete(f"/api/projects/{pid}/murs/{wid}", headers=csrf).status_code == 204
    r = c.delete(f"/api/projects/{pid}/murs/{ids[-1]}", headers=csrf)
    assert r.status_code == 409 and "au moins un mur" in r.text


def test_validated_or_unanalysed_project_cannot_be_edited(chef):
    c, csrf = chef
    pid = _project(c, csrf, validate=True)
    wid = _walls(c, pid)[0]["id"]
    r = c.put(f"/api/projects/{pid}/murs/{wid}", headers=csrf, json=OK)
    assert r.status_code == 409 and "avant la validation" in r.text
    fresh = c.post("/api/projects", headers=csrf, data={"nom": "Neuf"},
                   files={"fichier": ("p.pdf", io.BytesIO(b"x"))}).json()["id"]
    assert c.post(f"/api/projects/{fresh}/murs", headers=csrf, json=OK).status_code == 409


@pytest.mark.parametrize("patch,msg", [
    ({"longueur_mm": 100}, None),
    ({"openings": [{"type": "porte", "largeur_mm": 7000, "hauteur_mm": 2100}]}, "plus large"),
    ({"openings": [{"type": "porte", "largeur_mm": 900, "hauteur_mm": 3000}]}, "plus haute"),
    ({"openings": [{"type": "fenetre", "largeur_mm": 1200, "hauteur_mm": 1200, "x_mm": 5500}]}, "dépasse la fin"),
    ({"openings": [{"type": "fenetre", "largeur_mm": 1200, "hauteur_mm": 1200, "sill_mm": 1800}]}, "dépasse le haut"),
    ({"openings": [{"type": "porte", "largeur_mm": 1000, "hauteur_mm": 2000, "x_mm": 1000},
                   {"type": "porte", "largeur_mm": 1000, "hauteur_mm": 2000, "x_mm": 1500}]}, "chevauchent"),
    ({"junctions_mm": [9000]}, "jonction"),
    ({"start_kind": "inconnu"}, None),
    ({"nom": "  "}, None),
])
def test_invalid_walls_are_refused_with_french_messages(chef, patch, msg):
    c, csrf = chef
    pid = _project(c, csrf, laid=False)
    wid = _walls(c, pid)[0]["id"]
    r = c.put(f"/api/projects/{pid}/murs/{wid}", headers=csrf, json={**OK, **patch})
    assert r.status_code == 422, r.text
    if msg:
        assert msg in r.text


def test_operator_cannot_edit_and_actions_are_audited(chef, oper, session):
    from brikia.services import audit
    c, csrf = chef
    pid = _project(c, csrf, laid=False)
    wid = _walls(c, pid)[0]["id"]
    o, ocsrf = oper
    assert o.put(f"/api/projects/{pid}/murs/{wid}", headers=ocsrf, json=OK).status_code in (403, 404)
    c.put(f"/api/projects/{pid}/murs/{wid}", headers=csrf, json=OK)
    c.delete(f"/api/projects/{pid}/murs/{wid}", headers=csrf)
    actions = {e.action for e in audit.list_entries(session, target_type="wall")}
    assert {"wall.update", "wall.delete"} <= actions


def test_kinds_missing_fall_back_to_the_corner_flag(chef):
    c, csrf = chef
    pid = _project(c, csrf, laid=False)
    wid = _walls(c, pid)[0]["id"]
    body = {k: v for k, v in OK.items() if k not in ("start_kind", "end_kind")}
    w = c.put(f"/api/projects/{pid}/murs/{wid}", headers=csrf, json={**body, "is_corner": True}).json()
    assert w["is_corner"] is True and w["start_kind"] is None
