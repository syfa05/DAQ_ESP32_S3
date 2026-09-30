import pytest

from brikia.db import session_scope
from brikia.models import ActionLog, Project
from helpers import new_project, to_a_valider, to_valide


def _logs(action=None):
    with session_scope() as s:
        q = s.query(ActionLog)
        if action:
            q = q.filter_by(action=action)
        return [(e.user_id, e.action, e.target_type, e.target_id, e.details) for e in q.all()]


def test_chef_validates_project_and_it_is_traced(chef):
    c, csrf = chef
    pid = to_a_valider(c, csrf)
    r = c.post(f"/api/projects/{pid}/validation", headers=csrf)
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "valide" and d["validated_at"] is not None
    logs = _logs("project.validate")
    assert len(logs) == 1
    user_id, _, target_type, target_id, details = logs[0]
    assert user_id == 1 and target_type == "project" and target_id == pid
    assert details["total_blocs"] > 0 and details["avertissements"] == 0
    assert details["layout_run_id"] and "password" not in str(details)


def test_second_validation_is_refused_and_not_logged_twice(chef):
    c, csrf = chef
    pid = to_valide(c, csrf)
    r = c.post(f"/api/projects/{pid}/validation", headers=csrf)
    assert r.status_code == 409 and "déjà validé" in r.json()["detail"]
    assert len(_logs("project.validate")) == 1


@pytest.mark.parametrize("prep", ["a_analyser", "a_optimiser"])
def test_validation_refused_before_layout(chef, prep):
    c, csrf = chef
    pid = new_project(c, csrf)
    if prep == "a_optimiser":
        c.post(f"/api/projects/{pid}/analyse", headers=csrf)
    r = c.post(f"/api/projects/{pid}/validation", headers=csrf)
    assert r.status_code == 409 and r.json()["code"] == "transition_interdite"
    assert c.get(f"/api/projects/{pid}").json()["status"] == prep
    assert _logs() == []


def test_validation_refused_without_layout_run(chef):
    c, csrf = chef
    with session_scope() as s:
        s.add(Project(nom="X", status="a_valider"))
    r = c.post("/api/projects/1/validation", headers=csrf)
    assert r.status_code == 409 and "calepinage" in r.json()["detail"]
    assert c.get("/api/projects/1").json()["status"] == "a_valider"


def test_operator_cannot_validate(chef, oper):
    c, csrf = chef
    pid = to_a_valider(c, csrf)
    o, ocsrf = oper
    assert o.post(f"/api/projects/{pid}/validation", headers=ocsrf).status_code == 403
    assert c.get(f"/api/projects/{pid}").json()["status"] == "a_valider"
    assert _logs() == []


def test_unauthenticated_unknown_and_csrf(client, chef):
    assert client.post("/api/projects/1/validation").status_code == 401
    c, csrf = chef
    assert c.post("/api/projects/999/validation", headers=csrf).status_code == 404
    pid = to_a_valider(c, csrf)
    assert c.post(f"/api/projects/{pid}/validation").status_code == 403


def test_validation_is_atomic_with_its_trace(chef, monkeypatch):
    """Si la trace ne peut pas être écrite, le projet n'est pas validé."""
    from fastapi.testclient import TestClient

    from brikia.services import audit, validation

    c, csrf = chef
    pid = to_a_valider(c, csrf)

    def boom(*a, **k):
        raise RuntimeError("panne")

    monkeypatch.setattr(validation.audit, "record", boom)
    r = TestClient(c.app, raise_server_exceptions=False, cookies=c.cookies).post(
        f"/api/projects/{pid}/validation", headers=csrf)
    assert r.status_code == 500
    monkeypatch.undo()
    assert c.get(f"/api/projects/{pid}").json()["status"] == "a_valider"


def test_validated_project_is_frozen(chef):
    c, csrf = chef
    pid = to_valide(c, csrf)
    assert c.patch(f"/api/projects/{pid}", headers=csrf, json={"nom": "X"}).status_code == 409
    assert c.post(f"/api/projects/{pid}/calepinage", headers=csrf).status_code == 409
    assert c.post(f"/api/projects/{pid}/analyse", headers=csrf).status_code == 409


def test_operator_sees_validated_project_and_its_bom(chef, oper):
    c, csrf = chef
    pid = to_valide(c, csrf)
    o, _ = oper
    assert [p["id"] for p in o.get("/api/projects").json()] == [pid]
    assert o.get(f"/api/projects/{pid}/bom").json()["total_blocs"] > 0


# --- Consultation du journal ---------------------------------------------------
def test_audit_endpoint_chef_only_and_filterable(chef, oper):
    c, csrf = chef
    pid = to_valide(c, csrf)
    rows = c.get("/api/audit").json()
    assert len(rows) == 1 and rows[0]["action"] == "project.validate"
    assert rows[0]["utilisateur"] == "Awa Chef"
    assert c.get("/api/audit?action=production.start").json() == []
    assert len(c.get(f"/api/audit?target_type=project&target_id={pid}").json()) == 1
    assert c.get("/api/audit?limit=0").status_code == 422
    o, _ = oper
    assert o.get("/api/audit").status_code == 403
