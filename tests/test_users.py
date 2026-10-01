import pytest
from fastapi.testclient import TestClient

from brikia.db import session_scope
from brikia.domain.enums import Role
from brikia.domain.errors import Conflict, ValidationFailed
from brikia.services import audit
from brikia.services.auth import create_user
from conftest import PASSWORD, login

NEW = {"nom": "Moussa Op", "login": "Moussa.Op", "password": "motdepasse-9", "role": "operateur"}


def _users(c):
    return {u["login"]: u for u in c.get("/api/users").json()}


def test_chef_creates_user_who_can_login(app, chef):
    c, h = chef
    r = c.post("/api/users", json=NEW, headers=h)
    assert r.status_code == 201, r.text
    assert r.json()["login"] == "moussa.op" and r.json()["actif"] is True
    assert "password" not in r.text and "hash" not in r.text
    login(app, "moussa.op", "motdepasse-9")


def test_operator_cannot_administer_users(oper):
    c, h = oper
    assert c.get("/api/users").status_code == 403
    assert c.post("/api/users", json=NEW, headers=h).status_code == 403
    assert c.post("/api/users/1/actif", json={"actif": False}, headers=h).status_code == 403
    assert c.post("/api/users/1/mot-de-passe", json={"password": "xxxxxxxxx"}, headers=h).status_code == 403


def test_unauthenticated_and_csrf(client, chef):
    assert client.get("/api/users").status_code == 401
    c, _ = chef
    assert c.post("/api/users", json=NEW).status_code == 403  # sans jeton CSRF


@pytest.mark.parametrize("patch,msg", [
    ({"login": "chef"}, "existe déjà"),
    ({"login": "a b"}, "Identifiant invalide"),
    ({"login": "ab"}, "Identifiant invalide"),
    ({"password": "court"}, "au moins 8"),
    ({"nom": "  "}, "nom est obligatoire"),
])
def test_create_validation(chef, patch, msg):
    c, h = chef
    r = c.post("/api/users", json={**NEW, **patch}, headers=h)
    assert r.status_code in (409, 422) and msg in r.text


def test_deactivate_closes_sessions_and_blocks_login(app, chef):
    c, h = chef
    oc, _ = login(app, "oper")
    uid = _users(c)["oper"]["id"]
    assert c.post(f"/api/users/{uid}/actif", json={"actif": False}, headers=h).json()["actif"] is False
    assert oc.get("/api/auth/me").status_code == 401
    assert TestClient(app).post("/api/auth/login", json={"login": "oper", "password": PASSWORD}).status_code == 401
    c.post(f"/api/users/{uid}/actif", json={"actif": True}, headers=h)
    login(app, "oper")


def test_cannot_deactivate_self_nor_last_chef(app, chef):
    c, h = chef
    me = _users(c)["chef"]["id"]
    r = c.post(f"/api/users/{me}/actif", json={"actif": False}, headers=h)
    assert r.status_code == 409 and "propre compte" in r.text
    # un second chef peut désactiver le premier, mais pas le dernier restant
    c.post("/api/users", json={**NEW, "login": "chef2", "role": "chef_projet"}, headers=h)
    c2, h2 = login(app, "chef2", NEW["password"])
    assert c2.post(f"/api/users/{me}/actif", json={"actif": False}, headers=h2).status_code == 200
    me2 = _users(c2)["chef2"]["id"]
    assert c2.post(f"/api/users/{me2}/actif", json={"actif": False}, headers=h2).status_code == 409


def test_last_active_chef_protected_even_when_actor_is_other_role(db, users):
    from brikia.services import users as svc
    with session_scope() as s:
        create_user(s, nom="X", login="chefx", password=PASSWORD, role=Role.CHEF_PROJET)
    with session_scope() as s:
        ids = {u.login: u.id for u in svc.list_users(s)}
        svc.set_active(s, None, ids["chef"], False)
        with pytest.raises(Conflict):
            svc.set_active(s, None, ids["chefx"], False)


def test_admin_password_reset(app, chef):
    c, h = chef
    oc, _ = login(app, "oper")
    uid = _users(c)["oper"]["id"]
    assert c.post(f"/api/users/{uid}/mot-de-passe", json={"password": "court"}, headers=h).status_code == 422
    assert c.post(f"/api/users/{uid}/mot-de-passe", json={"password": "nouveau-mdp-1"}, headers=h).status_code == 200
    assert oc.get("/api/auth/me").status_code == 401
    assert TestClient(app).post("/api/auth/login", json={"login": "oper", "password": PASSWORD}).status_code == 401
    login(app, "oper", "nouveau-mdp-1")
    assert c.post("/api/users/999/mot-de-passe", json={"password": "nouveau-mdp-1"}, headers=h).status_code == 404


def test_change_own_password(app, oper):
    c, h = oper
    bad = c.post("/api/auth/password", json={"current_password": "faux", "new_password": "autre-mdp-12"}, headers=h)
    assert bad.status_code == 401
    same = c.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": PASSWORD}, headers=h)
    assert same.status_code == 422
    other, _ = login(app, "oper")  # second appareil
    ok = c.post("/api/auth/password", json={"current_password": PASSWORD, "new_password": "autre-mdp-12"}, headers=h)
    assert ok.status_code == 204
    assert c.get("/api/auth/me").status_code == 200       # session courante conservée
    assert other.get("/api/auth/me").status_code == 401   # autres sessions fermées
    login(app, "oper", "autre-mdp-12")


def test_actions_are_audited_without_secrets(app, chef, session):
    c, h = chef
    c.post("/api/users", json=NEW, headers=h)
    uid = _users(c)["moussa.op"]["id"]
    c.post(f"/api/users/{uid}/mot-de-passe", json={"password": "nouveau-mdp-1"}, headers=h)
    c.post(f"/api/users/{uid}/actif", json={"actif": False}, headers=h)
    entries = audit.list_entries(session, target_type="user")
    assert {e.action for e in entries} >= {"user.create", "user.password_reset", "user.deactivate"}
    dump = " ".join(str(e.details) for e in entries)
    assert "motdepasse-9" not in dump and "nouveau-mdp-1" not in dump


# --- Premier démarrage --------------------------------------------------
@pytest.fixture
def empty_app(settings, db):
    from brikia.main import create_app
    return create_app(settings)


def test_first_run_flow(empty_app):
    with TestClient(empty_app) as c:
        r = c.get("/connexion", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/installation"
        assert c.get("/installation").status_code == 200
        body = {"nom": "Awa", "login": "Admin", "password": "premier-mdp-1"}
        r = c.post("/api/setup", json=body)
        assert r.status_code == 201 and r.json()["user"]["role"] == "chef_projet"
        assert c.get("/api/auth/me").status_code == 200  # connecté d'office
        assert c.post("/api/setup", json=body).status_code == 409  # une seule fois
        assert c.get("/installation", follow_redirects=False).headers["location"] == "/"


def test_setup_refused_once_users_exist(client):
    r = client.post("/api/setup", json={"nom": "x", "login": "pirate", "password": "motdepasse-9"})
    assert r.status_code == 409


def test_setup_refused_from_remote_client(settings, db):
    from brikia.main import create_app
    app = create_app(settings)
    with TestClient(app, client=("192.168.1.50", 5555)) as c:
        r = c.post("/api/setup", json={"nom": "x", "login": "pirate", "password": "motdepasse-9"})
        assert r.status_code == 403 and "PC qui héberge" in r.text


def test_pages(chef, oper):
    c, _ = chef
    assert c.get("/utilisateurs").status_code == 200 and c.get("/compte").status_code == 200
    o, _ = oper
    assert o.get("/utilisateurs").status_code == 403 and o.get("/compte").status_code == 200


def test_create_user_service_validation(db):
    with session_scope() as s:
        with pytest.raises(ValidationFailed):
            create_user(s, nom="x", login="BAD LOGIN", password=PASSWORD, role=Role.OPERATEUR)


def test_email_accepted_as_login_and_lowercased(chef, app):
    c, h = chef
    r = c.post("/api/users", json={**NEW, "login": "Prenom.Nom+x@Exemple.FR"}, headers=h)
    assert r.status_code == 201 and r.json()["login"] == "prenom.nom+x@exemple.fr"
    login(app, "PRENOM.nom+x@exemple.fr", NEW["password"])
    assert c.post("/api/users", json={**NEW, "login": "a@b c"}, headers=h).status_code == 422
