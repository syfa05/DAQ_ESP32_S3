"""IFC réels fournis par l'utilisateur (exportés d'IFC Builder 2027.a), lus directement dans les ZIP."""

import time
import zipfile
from pathlib import Path

import pytest

pytest.importorskip("ifcopenshell")

import ifcopenshell
import ifcopenshell.util.element as E
import ifcopenshell.util.unit as U

from brikia.adapters.analyzers.base import PlanFile
from brikia.adapters.analyzers.ifc import IfcPlanAnalyzer
from brikia.domain.geometry import validate_geometry

FIXTURES = Path(__file__).parent / "fixtures"
# (zip, chemin de l'IFC dans le zip, murs IFC, murs droits, ouvertures, murs droits par niveau)
BUILDINGS = {
    "bureau": ("Bureau.zip", "Bureau/Bureau.ifc", 46, 94, 50,
               {"RDC": 21, "R+1": 24, "R+2": 25, "R+3": 20, "Toiture": 4}),
    "habitation": ("Batiment d'habitation.zip", "Batiment d'habitation/Batiment d'habitation.ifc",
                   112, 277, 127,
                   {"Rez-de-Chaussée": 30, "R+1": 58, "R+2": 69, "R+3": 74, "R+4": 46}),
}


@pytest.fixture(scope="session")
def real_ifc(tmp_path_factory):
    cache: dict[str, Path] = {}

    def get(key: str) -> Path:
        zip_name, member, *_ = BUILDINGS[key]
        if key not in cache:
            archive = FIXTURES / zip_name
            if not archive.exists():
                pytest.skip(f"{zip_name} absent")
            out = tmp_path_factory.mktemp(key)
            with zipfile.ZipFile(archive) as zf:
                cache[key] = Path(zf.extract(member, out))
        return cache[key]

    return get


def _analyse(path: Path):
    started = time.perf_counter()
    geo = IfcPlanAnalyzer().analyse(PlanFile(path, path.name, ".ifc", path.stat().st_size, "x"))
    return geo, time.perf_counter() - started


@pytest.mark.parametrize("key", BUILDINGS)
def test_counts_and_validity(real_ifc, key):
    _, _, n_ifc, n_walls, n_openings, per_level = BUILDINGS[key]
    geo, seconds = _analyse(real_ifc(key))
    validate_geometry(geo)                       # aucune ouverture plus grande que son mur, net > 0
    assert geo.source == "ifc" and len(geo.walls) == n_walls
    assert sum(len(w.openings) for w in geo.walls) == n_openings
    assert seconds < 30
    from collections import Counter
    assert dict(Counter(w.nom.split(" · ")[0] for w in geo.walls)) == per_level
    assert len({w.nom for w in geo.walls}) == len(geo.walls)          # noms uniques
    assert any(w.is_corner for w in geo.walls) and any(not w.is_corner for w in geo.walls)
    assert all(o.largeur_mm <= w.longueur_mm and o.hauteur_mm <= w.hauteur_mm for w in geo.walls for o in w.openings)
    assert all(200 <= w.hauteur_mm <= 12000 and 150 <= w.longueur_mm for w in geo.walls)
    assert f"{n_ifc} mur(s) IFC" in geo.notes[0]


@pytest.mark.parametrize("key", BUILDINGS)
def test_surfaces_match_the_quantities_authored_in_the_file(real_ifc, key):
    """Contrôle indépendant : les surfaces brute et nette recalculées par BrikIA
    doivent égaler celles que l'auteur du modèle a enregistrées (Qto_WallBaseQuantities)."""
    path = real_ifc(key)
    geo, _ = _analyse(path)
    model = ifcopenshell.open(str(path))
    scale = U.calculate_unit_scale(model, "AREAUNIT")
    gross = net = 0.0
    for wall in model.by_type("IfcWall"):
        q = E.get_psets(wall, qtos_only=True).get("Qto_WallBaseQuantities", {})
        gross += (q.get("GrossSideArea") or 0) * scale
        net += (q.get("NetSideArea") or 0) * scale
    ours_gross = sum(w.gross_area_mm2 for w in geo.walls) / 1e6
    ours_net = sum(w.net_area_mm2 for w in geo.walls) / 1e6
    assert ours_gross == pytest.approx(gross, rel=0.005)
    assert ours_net == pytest.approx(net, rel=0.005)


def test_full_pipeline_on_the_real_bureau_file(chef, real_ifc):
    """Import par l'API -> analyse réelle -> calepinage -> BOM -> validation."""
    c, csrf = chef
    path = real_ifc("bureau")
    r = c.post("/api/projects", headers=csrf, data={"nom": "Bureau réel"},
               files={"fichier": ("Bureau.ifc", path.read_bytes())})
    assert r.status_code == 201, r.text
    pid = r.json()["id"]
    d = c.post(f"/api/projects/{pid}/analyse", headers=csrf).json()
    assert d["status"] == "a_optimiser" and d["analysis_source"] == "ifc" and len(d["walls"]) == 94
    assert "Lecture IFC réelle" in d["analysis_notes"][0]
    assert "SIMULÉE" not in " ".join(d["analysis_notes"])
    lay = c.post(f"/api/projects/{pid}/calepinage", headers=csrf)
    assert lay.status_code == 200, lay.text
    bom = lay.json()["bom"]
    assert bom["total_blocs"] > 10_000 and bom["total_blocs"] == sum(l["quantite_totale"] for l in bom["lignes"])
    assert c.post(f"/api/projects/{pid}/validation", headers=csrf).json()["status"] == "valide"


def test_corrupt_ifc_upload_is_a_clear_422_and_project_unchanged(chef):
    c, csrf = chef
    pid = c.post("/api/projects", headers=csrf, data={"nom": "Cassé"},
                 files={"fichier": ("plan.ifc", b"ISO-10303-21;\nceci est tronque")}).json()["id"]
    r = c.post(f"/api/projects/{pid}/analyse", headers=csrf)
    assert r.status_code == 422 and r.json()["code"] == "analyse_echouee"
    assert "IFC" in r.json()["detail"] and "Traceback" not in r.text
    d = c.get(f"/api/projects/{pid}").json()
    assert d["status"] == "a_analyser" and d["walls"] == [] and d["analysis_source"] is None
