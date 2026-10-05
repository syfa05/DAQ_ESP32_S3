import re
from pathlib import Path

import pytest

import brikia

PKG = Path(brikia.__file__).parent
PAGES = ["/", "/moules", "/production", "/journal", "/projets/nouveau", "/projets/1"]


# --- Accès et redirections -------------------------------------------------------
@pytest.mark.parametrize("path", PAGES)
def test_unauthenticated_pages_redirect_to_login(client, path):
    r = client.get(path, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/connexion?suivant=")


def test_login_page_is_public_and_french(client):
    r = client.get("/connexion")
    assert r.status_code == 200 and 'lang="fr"' in r.text
    assert "Se connecter" in r.text and "Mot de passe" in r.text


def test_login_page_redirects_when_already_logged_in(chef):
    c, _ = chef
    assert c.get("/connexion", follow_redirects=False).headers["location"] == "/"


@pytest.mark.parametrize("path", ["/", "/moules", "/production", "/projets/1"])
def test_pages_render_for_both_roles(chef, oper, path):
    for c, _ in (chef, oper):
        r = c.get(path)
        assert r.status_code == 200 and "text/html" in r.headers["content-type"]


def test_chef_only_pages_refused_to_operator_but_available_to_chef(chef, oper):
    for path in ("/journal", "/projets/nouveau"):
        assert chef[0].get(path).status_code == 200
        r = oper[0].get(path)
        assert r.status_code == 403 and "Accès refusé" in r.text


def test_navigation_matches_role(chef, oper):
    assert "/journal" in chef[0].get("/").text
    assert "/journal" not in oper[0].get("/").text
    assert "Nouveau projet" in chef[0].get("/").text
    assert "Nouveau projet" not in oper[0].get("/").text
    assert "Nouveau moule" in chef[0].get("/moules").text
    assert "Nouveau moule" not in oper[0].get("/moules").text


def test_csrf_token_embedded_only_for_the_session_owner(chef):
    c, csrf = chef
    assert f'content="{csrf["X-CSRF-Token"]}"' in c.get("/").text


def test_unknown_page_is_html_for_browsers_json_for_api(client):
    r = client.get("/nimporte-quoi", headers={"accept": "text/html"})
    assert r.status_code == 404 and "Page introuvable" in r.text
    r = client.get("/api/nimporte-quoi", headers={"accept": "text/html"})
    assert r.headers["content-type"].startswith("application/json")


def test_page_html_escapes_user_data(chef):
    """Les données ne sont jamais injectées dans le HTML serveur (coquille seule)."""
    c, csrf = chef
    from helpers import new_project
    pid = new_project(c, csrf, name="<script>alert(1)</script>")
    assert "<script>alert(1)" not in c.get(f"/projets/{pid}").text


# --- Hors ligne, CSP ---------------------------------------------------------------
def test_static_assets_served_locally(client):
    for url in ("/static/css/app.css", "/static/css/fonts.css", "/static/js/app.js",
                "/static/js/pages/projet.js", "/static/fonts/oswald-latin-600-normal.woff2",
                "/static/fonts/inter-latin-400-normal.woff2",
                "/static/fonts/ibm-plex-mono-latin-400-normal.woff2"):
        assert client.get(url).status_code == 200, url


def test_no_external_resource_in_templates_css_or_js():
    """Aucun CDN ni police distante : tout doit être local (fonctionnement hors ligne)."""
    allowed = ("http://www.w3.org/2000/svg", "https://claude.com")
    offenders = []
    for f in list((PKG / "web/templates").glob("*.html")) + list((PKG / "static").rglob("*.css")) \
            + list((PKG / "static").rglob("*.js")):
        for m in re.finditer(r"""(?:https?:)?//[\w.-]+\.[a-z]{2,}[^\s"')]*""", f.read_text()):
            if not m.group(0).startswith(allowed):
                offenders.append((f.name, m.group(0)))
    assert offenders == []


def test_no_inline_script_or_style_that_the_csp_would_block():
    for f in (PKG / "web/templates").glob("*.html"):
        html = f.read_text()
        assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", html), f.name
        assert not re.search(r"\sstyle=", html), f.name
        assert not re.search(r"\son(click|load|submit|change)=", html), f.name


def test_html_pages_carry_csp(chef):
    r = chef[0].get("/")
    assert "script-src 'self'" in r.headers["content-security-policy"]
