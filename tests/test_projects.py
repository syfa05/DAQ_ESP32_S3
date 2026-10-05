import io

import pytest

from brikia.db import init_db, session_scope
from brikia.models import Project

PDF = b"%PDF-1.4 plan de demonstration"


def _post(c, csrf, *, name="Villa Test", filename="plan.pdf", content=PDF, **extra):
    return c.post(
        "/api/projects", headers=csrf,
        data={"nom": name, "ville": "Abidjan", "architecte": "Kone", **extra},
        files={"fichier": (filename, io.BytesIO(content), "application/octet-stream")},
    )


def _seed(*statuses):
    with session_scope() as s:
        for i, st in enumerate(statuses):
            s.add(Project(nom=f"P{i}", status=st))


# --- Création ---------------------------------------------------------------
def test_chef_creates_project_and_file_is_stored(settings, chef):
    c, csrf = chef
    r = _post(c, csrf)
    assert r.status_code == 201, r.text
    p = r.json()
    assert p["status"] == "a_analyser" and p["nom"] == "Villa Test"
    assert p["plan_original_name"] == "plan.pdf" and p["plan_size"] == len(PDF)
    import hashlib
    assert p["plan_sha256"] == hashlib.sha256(PDF).hexdigest()
    with session_scope() as s:
        stored = s.get(Project, p["id"]).plan_path
    assert (settings.uploads_dir / stored).read_bytes() == PDF
    assert stored.startswith(f"{p['id']}/") and stored.endswith(".pdf")


@pytest.mark.parametrize("ext", ["step", "stp", "ifc", "pdf", "STEP"])
def test_accepted_formats(chef, ext):
    c, csrf = chef
    assert _post(c, csrf, filename=f"plan.{ext}").status_code == 201


@pytest.mark.parametrize("filename", ["plan.exe", "plan.dwg", "plan", "plan.pdf.sh"])
def test_refused_formats_create_nothing(settings, chef, filename):
    c, csrf = chef
    r = _post(c, csrf, filename=filename)
    assert r.status_code == 422 and "Format" in r.json()["detail"]
    with session_scope() as s:
        assert s.query(Project).count() == 0
    assert not [f for f in settings.uploads_dir.rglob("*") if f.is_file()]


def test_empty_file_refused(chef):
    c, csrf = chef
    r = _post(c, csrf, content=b"")
    assert r.status_code == 422 and "vide" in r.json()["detail"]


def test_file_too_large_refused_and_cleaned(app, settings, chef):
    app.state.settings.max_upload_mb = 1
    c, csrf = chef
    r = _post(c, csrf, content=b"x" * (2 * 1024 * 1024))
    assert r.status_code == 413
    with session_scope() as s:
        assert s.query(Project).count() == 0
    assert not [f for f in settings.uploads_dir.rglob("*") if f.is_file()]


def test_hostile_filename_never_used_as_path(settings, chef):
    c, csrf = chef
    r = _post(c, csrf, filename="../../etc/evil.pdf")
    assert r.status_code == 201
    assert r.json()["plan_original_name"] == "evil.pdf"
    files = [f for f in settings.uploads_dir.rglob("*") if f.is_file()]
    assert len(files) == 1 and files[0].is_relative_to(settings.uploads_dir)
    assert "evil" not in files[0].name


def test_missing_name_or_file_is_validation_error(chef):
    c, csrf = chef
    assert _post(c, csrf, name="   ").status_code == 422
    r = c.post("/api/projects", headers=csrf, data={"nom": "X"})
    assert r.status_code == 422 and "invalides" in r.json()["detail"]


def test_creation_rolls_back_when_storage_fails(settings, chef, monkeypatch):
    """Erreur inattendue au stockage : aucune ligne orpheline en base."""
    from brikia.services import storage

    def boom(*a, **k):
        raise OSError("disque plein")

    monkeypatch.setattr(storage, "save_upload", boom)
    c, csrf = chef
    from fastapi.testclient import TestClient
    r = TestClient(c.app, raise_server_exceptions=False, cookies=c.cookies).post(
        "/api/projects", headers=csrf, data={"nom": "X"},
        files={"fichier": ("a.pdf", PDF)})
    assert r.status_code == 500 and "disque" not in r.text
    with session_scope() as s:
        assert s.query(Project).count() == 0


# --- Permissions -------------------------------------------------------------
def test_operator_cannot_create_project(oper):
    c, csrf = oper
    r = _post(c, csrf)
    assert r.status_code == 403
    with session_scope() as s:
        assert s.query(Project).count() == 0


def test_unauthenticated_and_csrf(client, chef):
    assert client.get("/api/projects").status_code == 401
    c, _ = chef
    assert _post(c, {}).status_code == 403  # sans jeton CSRF


def test_operator_sees_only_production_projects(chef, oper):
    _seed("a_analyser", "a_optimiser", "a_valider", "valide", "en_production", "termine")
    c, _ = chef
    assert len(c.get("/api/projects").json()) == 6
    o, _ = oper
    seen = {p["status"] for p in o.get("/api/projects").json()}
    assert seen == {"valide", "en_production", "termine"}


def test_operator_gets_404_on_hidden_project_and_200_on_visible(oper):
    _seed("a_analyser", "valide")
    o, _ = oper
    assert o.get("/api/projects/1").status_code == 404
    assert o.get("/api/projects/2").status_code == 200


# --- Récupération / persistance ---------------------------------------------
def test_get_returns_detail_and_404(chef):
    c, csrf = chef
    pid = _post(c, csrf).json()["id"]
    d = c.get(f"/api/projects/{pid}").json()
    assert d["id"] == pid and d["walls"] == []
    r = c.get("/api/projects/9999")
    assert r.status_code == 404 and r.json()["detail"] == "Projet introuvable."


def test_project_persists_across_restart(settings, chef):
    c, csrf = chef
    pid = _post(c, csrf).json()["id"]
    init_db(settings)  # redémarrage
    assert c.get(f"/api/projects/{pid}").json()["nom"] == "Villa Test"


# --- Mise à jour -------------------------------------------------------------
def test_update_allowed_before_validation(chef):
    c, csrf = chef
    pid = _post(c, csrf).json()["id"]
    r = c.patch(f"/api/projects/{pid}", headers=csrf, json={"ville": "Bouaké"})
    assert r.status_code == 200 and r.json()["ville"] == "Bouaké"
    assert r.json()["nom"] == "Villa Test"  # champs non envoyés inchangés
    assert c.patch(f"/api/projects/{pid}", headers=csrf, json={"nom": " "}).status_code == 422


def test_update_refused_once_validated_and_never_changes_status(chef):
    _seed("valide")
    c, csrf = chef
    r = c.patch("/api/projects/1", headers=csrf, json={"nom": "Autre"})
    assert r.status_code == 409
    # Le statut n'est pas modifiable par l'API de mise à jour.
    _seed("a_analyser")
    c.patch("/api/projects/2", headers=csrf, json={"status": "valide"})
    assert c.get("/api/projects/2").json()["status"] == "a_analyser"


def test_operator_cannot_update(oper):
    _seed("valide")
    o, csrf = oper
    assert o.patch("/api/projects/1", headers=csrf, json={"nom": "X"}).status_code == 403
