import sqlite3

from fastapi import APIRouter, Depends
from fastapi.testclient import TestClient

from brikia.deps import require_chef_projet, require_operateur, require_role
from brikia.domain.enums import Role
from brikia.security import hash_password, hash_token, verify_password
from brikia.services.auth import LoginThrottle
from conftest import PASSWORD, login


# --- Connexion ----------------------------------------------------------
def test_login_valid_sets_secure_flags_and_returns_csrf(client):
    r = client.post("/api/auth/login", json={"login": "chef", "password": PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["user"] == {"id": 1, "nom": "Awa Chef", "login": "chef", "role": "chef_projet"}
    assert body["csrf_token"]
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert "secure" not in cookie  # HTTP local par défaut
    assert "password" not in r.text


def test_login_is_case_insensitive_on_identifier(client):
    assert client.post("/api/auth/login", json={"login": " CHEF ", "password": PASSWORD}).status_code == 200


def test_login_invalid_password_and_unknown_user_same_message(client):
    a = client.post("/api/auth/login", json={"login": "chef", "password": "faux"})
    b = client.post("/api/auth/login", json={"login": "inconnu", "password": "faux"})
    assert a.status_code == b.status_code == 401
    assert a.json() == b.json()
    assert "incorrect" in a.json()["detail"]


def test_inactive_user_cannot_login(app, client):
    from brikia.db import session_scope
    from brikia.models import User

    with session_scope() as s:
        s.query(User).filter_by(login="oper").one().actif = False
    r = client.post("/api/auth/login", json={"login": "oper", "password": PASSWORD})
    assert r.status_code == 401


def test_login_payload_validation_is_french_and_generic(client):
    r = client.post("/api/auth/login", json={"login": ""})
    assert r.status_code == 422
    assert "invalides" in r.json()["detail"]


def test_throttle_blocks_after_repeated_failures(client):
    for _ in range(5):
        assert client.post("/api/auth/login", json={"login": "chef", "password": "x"}).status_code == 401
    r = client.post("/api/auth/login", json={"login": "chef", "password": PASSWORD})
    assert r.status_code == 429


def test_throttle_window_expires():
    now = [0.0]
    t = LoginThrottle(max_failures=2, window_s=10, clock=lambda: now[0])
    t.fail("a"); t.fail("a")
    try:
        t.check("a")
        raise AssertionError("aurait dû être bloqué")
    except Exception as exc:
        assert exc.code == "trop_de_tentatives"
    now[0] = 11
    t.check("a")


# --- Utilisateur non authentifié ---------------------------------------
def test_unauthenticated_access_refused(client):
    assert client.get("/api/auth/me").status_code == 401
    assert client.post("/api/auth/logout").status_code == 401


def test_invalid_or_forged_cookie_refused(client):
    client.cookies.set("brikia_session", "n-importe-quoi")
    assert client.get("/api/auth/me").status_code == 401


# --- Session, logout, CSRF ---------------------------------------------
def test_me_and_logout_flow(chef):
    c, csrf = chef
    assert c.get("/api/auth/me").json()["user"]["login"] == "chef"
    assert c.post("/api/auth/logout").status_code == 403  # CSRF requis
    assert c.post("/api/auth/logout", headers=csrf).status_code == 204
    assert c.get("/api/auth/me").status_code == 401


def test_logout_clears_cookie_with_same_attributes(chef):
    c, csrf = chef
    r = c.post("/api/auth/logout", headers=csrf)
    cookie = r.headers["set-cookie"].lower()
    assert "max-age=0" in cookie and "httponly" in cookie and "samesite=strict" in cookie


def test_logged_out_token_is_invalidated_server_side(app):
    c, csrf = login(app, "chef")
    token = c.cookies.get("brikia_session")
    c.post("/api/auth/logout", headers=csrf)
    c2 = TestClient(app)
    c2.cookies.set("brikia_session", token)
    assert c2.get("/api/auth/me").status_code == 401


def test_expired_session_refused(app, chef):
    from brikia.db import session_scope
    from brikia.models import UserSession
    from brikia.models.base import utcnow
    from datetime import timedelta

    c, _ = chef
    with session_scope() as s:
        for us in s.query(UserSession):
            us.expires_at = utcnow() - timedelta(seconds=1)
    assert c.get("/api/auth/me").status_code == 401


def test_deactivated_user_session_stops_working(chef):
    from brikia.db import session_scope
    from brikia.models import User

    c, _ = chef
    with session_scope() as s:
        s.query(User).filter_by(login="chef").one().actif = False
    assert c.get("/api/auth/me").status_code == 401


# --- Pas de secret en base ni dans les logs -----------------------------
def test_no_plaintext_secrets_stored_or_logged(settings, app, chef, caplog):
    import logging

    c, _ = chef
    token = c.cookies.get("brikia_session")
    with caplog.at_level(logging.DEBUG):
        c.post("/api/auth/login", json={"login": "chef", "password": "secret-faux-xyz"})
    con = sqlite3.connect(settings.db_path)
    dump = "\n".join(con.iterdump())
    con.close()
    assert PASSWORD not in dump
    assert token not in dump and hash_token(token) in dump
    assert "$argon2" in dump
    assert "secret-faux-xyz" not in caplog.text and PASSWORD not in caplog.text


def test_password_hash_roundtrip():
    h = hash_password("abc12345")
    assert h != "abc12345" and verify_password("abc12345", h)
    assert not verify_password("autre", h)
    assert not verify_password("abc12345", None)


# --- Rôles (RBAC) : routeur de test appliquant les dépendances réelles ---
def _rbac_app(app):
    r = APIRouter(prefix="/api/_test")

    @r.get("/chef")
    def chef_only(u=Depends(require_chef_projet)): return {"ok": u.login}

    @r.post("/chef")
    def chef_only_post(u=Depends(require_chef_projet)): return {"ok": u.login}

    @r.get("/oper")
    def oper_only(u=Depends(require_operateur)): return {"ok": u.login}

    @r.get("/both")
    def both(u=Depends(require_role(Role.CHEF_PROJET, Role.OPERATEUR))): return {"ok": u.login}

    app.include_router(r)
    return app


def test_rbac_operator_denied_on_chef_endpoints(app, oper):
    _rbac_app(app)
    c, csrf = oper
    assert c.get("/api/_test/chef").status_code == 403
    r = c.post("/api/_test/chef", headers=csrf)
    assert r.status_code == 403 and r.json()["code"] == "acces_refuse"
    assert c.get("/api/_test/oper").status_code == 200
    assert c.get("/api/_test/both").status_code == 200


def test_rbac_chef_allowed_and_denied_on_operator_endpoint(app, chef):
    _rbac_app(app)
    c, csrf = chef
    assert c.get("/api/_test/chef").status_code == 200
    assert c.post("/api/_test/chef", headers=csrf).status_code == 200
    assert c.get("/api/_test/oper").status_code == 403


def test_rbac_unauthenticated_gets_401_not_403(app, client):
    _rbac_app(app)
    assert client.get("/api/_test/chef").status_code == 401


def test_csrf_required_on_unsafe_methods(app, chef):
    _rbac_app(app)
    c, csrf = chef
    assert c.post("/api/_test/chef").status_code == 403
    assert c.post("/api/_test/chef", headers={"X-CSRF-Token": "faux"}).status_code == 403
    assert c.post("/api/_test/chef", headers=csrf).status_code == 200


# --- Application / réseau ------------------------------------------------
def test_health_security_headers_and_no_cors(client):
    r = client.get("/api/health", headers={"Origin": "http://evil.example"})
    assert r.status_code == 200
    assert "access-control-allow-origin" not in r.headers
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"


def test_unknown_route_and_errors_are_french_json(client):
    r = client.get("/api/inexistant")
    assert r.status_code == 404 and "introuvable" in r.json()["detail"]


def test_allowed_hosts_enforced(settings, users, monkeypatch):
    from brikia.config import Settings
    from brikia.main import create_app

    s = Settings(_env_file=None, data_dir=settings.data_dir, allowed_hosts=["brikia.usine.local"])
    c = TestClient(create_app(s))
    assert c.get("/api/health", headers={"host": "brikia.usine.local"}).status_code == 200
    assert c.get("/api/health", headers={"host": "evil.example"}).status_code == 400


def test_cookie_secure_when_configured_for_https(settings, users):
    from brikia.config import Settings
    from brikia.main import create_app

    s = Settings(_env_file=None, data_dir=settings.data_dir, cookie_secure=True)
    c = TestClient(create_app(s), base_url="https://testserver")
    r = c.post("/api/auth/login", json={"login": "chef", "password": PASSWORD})
    assert "secure" in r.headers["set-cookie"].lower()


def test_unexpected_error_hides_traceback(settings, users):
    from brikia.main import create_app

    app = create_app(settings)

    @app.get("/api/_boom")
    def boom(): raise RuntimeError("secret SQL: SELECT * FROM users")

    c = TestClient(app, raise_server_exceptions=False)
    r = c.get("/api/_boom")
    assert r.status_code == 500
    assert "SELECT" not in r.text and "Traceback" not in r.text
