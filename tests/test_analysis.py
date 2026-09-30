import hashlib
import io
from pathlib import Path

import pytest

from brikia.adapters.analyzers.base import PlanFile
from brikia.adapters.analyzers.simulated import SCENARIOS, SimulatedPlanAnalyzer
from brikia.db import init_db, session_scope
from brikia.domain.geometry import (
    OpeningGeometry, ProjectGeometry, WallGeometry, mm2_to_m2, validate_geometry,
)
from brikia.domain.errors import ValidationFailed
from brikia.models import Opening, Project, Wall


# Contenu dont le SHA-256 sélectionne le scénario « Maison type F3 » (6 murs).
F3_CONTENT = b"f3-2"


def _plan(content: bytes, name="plan.pdf") -> PlanFile:
    return PlanFile(Path(name), name, Path(name).suffix, len(content),
                    hashlib.sha256(content).hexdigest())


def _create(c, csrf, content=b"%PDF plan A", filename="plan.pdf"):
    r = c.post("/api/projects", headers=csrf, data={"nom": "Villa"},
               files={"fichier": (filename, io.BytesIO(content))})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def _shape(project_detail):
    return [(w["nom"], w["longueur_mm"], w["hauteur_mm"], w["is_corner"],
             [(o["type"], o["largeur_mm"], o["hauteur_mm"]) for o in w["openings"]])
            for w in project_detail["walls"]]


# --- Analyseur simulé : déterminisme et cohérence -------------------------
def test_same_content_gives_same_result_regardless_of_name():
    a = SimulatedPlanAnalyzer()
    r1 = a.analyse(_plan(b"contenu", "a.pdf"))
    r2 = a.analyse(_plan(b"contenu", "autre-nom.ifc"))
    assert r1 == r2 and r1.source == "simulated"


def test_scenario_is_stable_for_known_content():
    """Épingle le comportement : un changement d'algorithme casserait ce test."""
    geo = SimulatedPlanAnalyzer().analyse(_plan(F3_CONTENT))
    # Phase 2 : l'analyse simulée se déclare toujours comme telle dans ses notes.
    assert geo.notes == ("Analyse SIMULÉE : le contenu du plan n'a pas été lu.",
                         "Scénario de démonstration : Maison type F3")
    assert len(geo.walls) == 6


def test_all_three_scenarios_reachable_and_valid():
    a = SimulatedPlanAnalyzer()
    seen = {a.analyse(_plan(f"c{i}".encode())).notes[-1] for i in range(60)}
    assert len(seen) == len(SCENARIOS) == 3
    for walls in SCENARIOS.values():
        validate_geometry(ProjectGeometry(walls))
        assert any(w.is_corner for w in walls)
    assert any(w.openings for walls in SCENARIOS.values() for w in walls)
    assert any(not w.openings for walls in SCENARIOS.values() for w in walls)


def test_surface_computation():
    w = WallGeometry("M", 4000, 2500, False, (OpeningGeometry("porte", 900, 2100),
                                               OpeningGeometry("fenetre", 1200, 1200)))
    assert w.gross_area_mm2 == 10_000_000
    assert w.openings_area_mm2 == 1_890_000 + 1_440_000
    assert w.net_area_mm2 == 6_670_000
    assert mm2_to_m2(w.net_area_mm2) == 6.67


@pytest.mark.parametrize("walls", [
    (),
    (WallGeometry("M", 0, 2500),),
    (WallGeometry("M", 3000, 2500, False, (OpeningGeometry("porte", 4000, 2100),)),),
    (WallGeometry("M", 3000, 2500, False, (OpeningGeometry("porte", 900, 3000),)),),
    (WallGeometry("M", 3000, 2500, False, (OpeningGeometry("baie", 3000, 2500),)),),
])
def test_invalid_geometry_rejected(walls):
    with pytest.raises(ValidationFailed):
        validate_geometry(ProjectGeometry(walls))


# --- API : parcours nominal ---------------------------------------------
def test_analyse_creates_walls_openings_surfaces_and_status(chef):
    c, csrf = chef
    pid = _create(c, csrf, F3_CONTENT)
    r = c.post(f"/api/projects/{pid}/analyse", headers=csrf)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["status"] == "a_optimiser" and len(d["walls"]) == 6
    nord = d["walls"][0]
    assert nord["nom"] == "Façade nord" and len(nord["openings"]) == 2
    assert nord["surface_brute_m2"] == 27.0
    assert nord["surface_ouvertures_m2"] == 2.88
    assert nord["surface_nette_m2"] == 24.12
    assert c.get(f"/api/projects/{pid}").json()["walls"] == d["walls"]


def test_analysis_is_deterministic_across_projects(chef):
    c, csrf = chef
    ids = [_create(c, csrf, b"meme contenu", f"p{i}.pdf") for i in range(2)]
    res = [c.post(f"/api/projects/{i}/analyse", headers=csrf).json() for i in ids]
    assert _shape(res[0]) == _shape(res[1])


def test_analysis_persists_after_restart(settings, chef):
    c, csrf = chef
    pid = _create(c, csrf)
    c.post(f"/api/projects/{pid}/analyse", headers=csrf)
    init_db(settings)
    d = c.get(f"/api/projects/{pid}").json()
    assert d["status"] == "a_optimiser" and d["walls"]


# --- Idempotence et garde-fous ---------------------------------------------
def test_second_analysis_refused_without_duplicating_walls(chef):
    c, csrf = chef
    pid = _create(c, csrf, F3_CONTENT)
    assert c.post(f"/api/projects/{pid}/analyse", headers=csrf).status_code == 200
    r = c.post(f"/api/projects/{pid}/analyse", headers=csrf)
    assert r.status_code == 409 and r.json()["code"] == "transition_interdite"
    with session_scope() as s:
        assert s.query(Wall).count() == 6


def test_analysis_refused_from_any_later_status(chef):
    c, csrf = chef
    with session_scope() as s:
        for st in ("a_optimiser", "a_valider", "valide", "en_production", "termine"):
            s.add(Project(nom=st, status=st, plan_path="x/y.pdf"))
    for pid in range(1, 6):
        assert c.post(f"/api/projects/{pid}/analyse", headers=csrf).status_code == 409


def test_missing_plan_file_refused_and_project_unchanged(settings, chef):
    c, csrf = chef
    pid = _create(c, csrf)
    for f in settings.uploads_dir.rglob("*.pdf"):
        f.unlink()
    r = c.post(f"/api/projects/{pid}/analyse", headers=csrf)
    assert r.status_code == 409 and "introuvable" in r.json()["detail"]
    assert c.get(f"/api/projects/{pid}").json()["status"] == "a_analyser"


def test_failing_analyzer_leaves_project_untouched(app, chef):
    class Broken:
        name = "broken"

        def analyse(self, file):
            raise RuntimeError("SELECT secret FROM interne")

    app.state.plan_analyzer = Broken()
    c, csrf = chef
    pid = _create(c, csrf)
    r = c.post(f"/api/projects/{pid}/analyse", headers=csrf)
    assert r.status_code == 422 and r.json()["code"] == "analyse_echouee"
    assert "SELECT" not in r.text
    assert c.get(f"/api/projects/{pid}").json()["status"] == "a_analyser"
    with session_scope() as s:
        assert s.query(Wall).count() == 0


def test_invalid_geometry_from_analyzer_persists_nothing(app, chef):
    class Bad:
        name = "bad"

        def analyse(self, file):
            return ProjectGeometry((WallGeometry("ok", 3000, 2500),
                                    WallGeometry("ko", 1000, 1000, False,
                                                 (OpeningGeometry("porte", 2000, 500),))))

    app.state.plan_analyzer = Bad()
    c, csrf = chef
    pid = _create(c, csrf)
    assert c.post(f"/api/projects/{pid}/analyse", headers=csrf).status_code == 422
    with session_scope() as s:
        assert s.query(Wall).count() == 0 and s.query(Opening).count() == 0
        assert s.get(Project, pid).status == "a_analyser"


def test_rollback_when_persistence_fails_midway(chef, monkeypatch):
    """Erreur après la transition : le statut ne doit pas avoir changé."""
    from brikia.services import analysis

    def boom(*a, **k):
        raise RuntimeError("panne")

    monkeypatch.setattr(analysis, "Wall", boom)
    c, csrf = chef
    pid = _create(c, csrf)
    from fastapi.testclient import TestClient
    r = TestClient(c.app, raise_server_exceptions=False, cookies=c.cookies).post(
        f"/api/projects/{pid}/analyse", headers=csrf)
    assert r.status_code == 500
    monkeypatch.undo()
    assert c.get(f"/api/projects/{pid}").json()["status"] == "a_analyser"


# --- Permissions ------------------------------------------------------------
def test_operator_cannot_analyse(chef, oper):
    c, csrf = chef
    pid = _create(c, csrf)
    o, ocsrf = oper
    r = o.post(f"/api/projects/{pid}/analyse", headers=ocsrf)
    assert r.status_code == 403
    assert c.get(f"/api/projects/{pid}").json()["status"] == "a_analyser"


def test_unauthenticated_and_unknown_project(client, chef):
    assert client.post("/api/projects/1/analyse").status_code == 401
    c, csrf = chef
    assert c.post("/api/projects/999/analyse", headers=csrf).status_code == 404


# --- Phase 2 : provenance de l'analyse conservée et exposée -------------------------
def test_analysis_source_and_notes_are_stored_and_exposed(chef):
    c, csrf = chef
    pid = _create(c, csrf, F3_CONTENT)
    before = c.get(f"/api/projects/{pid}").json()
    assert before["analysis_source"] is None and before["analysis_notes"] is None
    d = c.post(f"/api/projects/{pid}/analyse", headers=csrf).json()
    assert d["analysis_source"] == "simulated"
    assert d["analysis_notes"][0].startswith("Format PDF") and "SIMULÉE" in d["analysis_notes"][0]
    assert c.get(f"/api/projects/{pid}").json()["analysis_notes"] == d["analysis_notes"]
    assert c.get("/api/projects").json()[0]["analysis_source"] == "simulated"


def test_real_mode_without_module_refuses_and_leaves_project_untouched(app, chef):
    from brikia.adapters.analyzers.base import AnalyzerUnavailable
    from brikia.adapters.analyzers.dispatch import ExtensionPlanAnalyzer

    def missing():
        raise AnalyzerUnavailable("IFC", "ifcopenshell")

    app.state.plan_analyzer = ExtensionPlanAnalyzer("real", {".ifc": missing})
    c, csrf = chef
    pid = c.post("/api/projects", headers=csrf, data={"nom": "IFC réel"},
                 files={"fichier": ("p.ifc", io.BytesIO(b"ISO-10303-21;"))}).json()["id"]
    r = c.post(f"/api/projects/{pid}/analyse", headers=csrf)
    assert r.status_code == 422 and "n'est pas disponible" in r.json()["detail"]
    d = c.get(f"/api/projects/{pid}").json()
    assert d["status"] == "a_analyser" and d["walls"] == [] and d["analysis_source"] is None
