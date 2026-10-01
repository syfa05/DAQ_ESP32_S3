"""StepPlanAnalyzer sur des STEP synthétiques dont on connaît la géométrie exacte."""

import hashlib
from pathlib import Path

import pytest

pytest.importorskip("OCP")

from brikia.adapters.analyzers.base import PlanFile
from brikia.adapters.analyzers.step import StepOptions, StepPlanAnalyzer
from brikia.domain.errors import AnalysisFailed
from brikia.domain.geometry import validate_geometry
from step_factory import box, cut, flat_face, fuse, rotate_z, to_y_up, translate, wall, write


def analyse(tmp_path, shapes, unit="MM", name="t.step", **options):
    path = tmp_path / name
    write(path, shapes, unit)
    return StepPlanAnalyzer(StepOptions(**options)).analyse(_plan(path))


def _plan(path: Path) -> PlanFile:
    data = path.read_bytes()
    return PlanFile(path, path.name, path.suffix, len(data), hashlib.sha256(data).hexdigest())


def dims(geo):
    return [(w.nom, w.longueur_mm, w.hauteur_mm, w.is_corner,
             sorted((o.type, o.largeur_mm, o.hauteur_mm) for o in w.openings)) for w in geo.walls]


# --- murs ---------------------------------------------------------------------------
def test_single_wall(tmp_path):
    geo = analyse(tmp_path, [wall(0, 0, 5000)])
    assert dims(geo) == [("Niveau +0,00 m · Mur n°1", 5000, 2700, False, [])]
    assert geo.source == "step" and geo.notes[0].startswith("APPROXIMATION")
    validate_geometry(geo)


def test_window_hole_and_door_notch_become_openings(tmp_path):
    w = cut(wall(0, 0, 5000), box(1000, -300, 900, 1200, 600, 1000),      # fenêtre traversante 1200×1000, allège 900
            box(3000, -300, -10, 900, 600, 2110))                          # porte en encoche 900×2100
    geo = analyse(tmp_path, [w])
    assert dims(geo)[0][4] == [("fenetre", 1200, 1000), ("porte", 900, 2100)]
    assert geo.walls[0].net_area_mm2 == 5000 * 2700 - 1200 * 1000 - 900 * 2100
    validate_geometry(geo)


def test_raised_hole_near_the_floor_is_a_door_and_high_hole_a_window(tmp_path):
    w = cut(wall(0, 0, 6000), box(500, -300, 100, 900, 600, 2000), box(3000, -300, 1500, 800, 600, 600))
    assert dims(analyse(tmp_path, [w]))[0][4] == [("fenetre", 800, 600), ("porte", 900, 2000)]


def test_l_shaped_building_corners(tmp_path):
    geo = analyse(tmp_path, [wall(0, 0, 6000), wall(6000, 0, 4000, along="y"),
                             wall(0, 0, 4000, along="y", z=0)])
    assert sorted((w.longueur_mm, w.is_corner) for w in geo.walls) == [(4000, True), (4000, True), (6000, True)]


def test_aligned_and_t_walls_are_not_corners(tmp_path):
    geo = analyse(tmp_path, [wall(0, 0, 5000), wall(5000, 0, 5000), wall(2500, 100, 3000, along="y")])
    assert [w.is_corner for w in geo.walls] == [False, False, False]


def test_rotated_and_translated_wall_keeps_its_true_length_and_opening(tmp_path):
    w = translate(rotate_z(cut(wall(0, 0, 5000), box(1000, -300, 0, 900, 600, 2100)), 30), 12000, 7000)
    assert dims(analyse(tmp_path, [w]))[0][1:5] == (5000, 2700, False, [("porte", 900, 2100)])


def test_columns_slabs_and_massive_volumes_are_ignored_and_reported(tmp_path):
    shapes = [wall(0, 0, 5000), box(0, 500, 0, 300, 300, 2700),            # poteau
              box(-1000, -1000, -200, 9000, 7000, 200),                    # dalle
              box(20000, 0, 0, 4000, 4000, 3000)]                          # volume massif
    geo = analyse(tmp_path, shapes)
    assert len(geo.walls) == 1
    notes = " ".join(geo.notes)
    assert "poteaux" in notes and "dalles" in notes and "trop épais" in notes


# --- niveaux, unités, orientation ------------------------------------------------------
def test_levels_are_named_by_elevation_and_ordered(tmp_path):
    geo = analyse(tmp_path, [wall(0, 0, 4000, z=3000), wall(0, 0, 5000, z=0), wall(0, 2000, 3000, z=3010)])
    assert [w.nom for w in geo.walls] == ["Niveau +0,00 m · Mur n°1", "Niveau +3,00 m · Mur n°1", "Niveau +3,00 m · Mur n°2"]


@pytest.mark.parametrize("unit", ["M", "CM", "MM", "INCH"])
def test_file_units_are_converted_to_millimetres(tmp_path, unit):
    geo = analyse(tmp_path, [cut(wall(0, 0, 5000), box(1000, -300, 900, 1200, 600, 1000))], unit=unit)
    assert dims(geo)[0][1:3] == (5000, 2700)
    assert dims(geo)[0][4] == [("fenetre", 1200, 1000)]


Y_UP_BUILDING = lambda: [to_y_up(wall(0, 0, 6000)), to_y_up(wall(0, 4000, 6000)),          # noqa: E731
                         to_y_up(wall(0, 0, 4000, along="y")), to_y_up(wall(6000, 0, 4000, along="y"))]


def test_y_up_model_is_detected_automatically_when_the_evidence_is_strong(tmp_path):
    geo = analyse(tmp_path, Y_UP_BUILDING())
    assert sorted((w.longueur_mm, w.hauteur_mm, w.is_corner) for w in geo.walls) == [
        (4000, 2700, True), (4000, 2700, True), (6000, 2700, True), (6000, 2700, True)]
    assert any("Axe vertical du fichier : Y (détecté automatiquement)" in n for n in geo.notes)


def test_up_axis_can_be_forced_by_configuration(tmp_path):
    geo = analyse(tmp_path, Y_UP_BUILDING(), up_axis="y")
    assert len(geo.walls) == 4 and any("Y (configuration)" in n for n in geo.notes)
    z_only = analyse(tmp_path, [wall(0, 0, 5000)], up_axis="z")
    assert len(z_only.walls) == 1 and not any("Axe vertical" in n for n in z_only.notes)


def test_a_z_up_model_is_never_switched_to_y(tmp_path):
    """Un bâtiment Z vertical dont les murs sont surtout orientés selon Y ne doit pas basculer."""
    geo = analyse(tmp_path, [wall(0, 0, 5000, along="y"), wall(3000, 0, 5000, along="y"), wall(6000, 0, 5000, along="y"),
                             wall(0, 0, 6000)])
    assert len(geo.walls) == 4 and not any("Axe vertical" in n for n in geo.notes)


def test_slabs_seen_edge_on_are_not_mistaken_for_walls(tmp_path):
    with pytest.raises(AnalysisFailed):
        analyse(tmp_path, [box(0, 0, 0, 8000, 6000, 200), box(0, 0, 3000, 8000, 6000, 200)])


# --- erreurs en français -------------------------------------------------------------------
def test_file_without_any_wall_lists_what_was_ignored(tmp_path):
    with pytest.raises(AnalysisFailed) as e:
        analyse(tmp_path, [box(0, 0, 0, 8000, 6000, 200)])
    assert "Aucun mur reconnu" in e.value.message and "dalles" in e.value.message


def test_a_fused_l_shaped_wall_is_not_recognised_and_explained(tmp_path):
    with pytest.raises(AnalysisFailed) as e:
        analyse(tmp_path, [fuse(wall(0, 0, 5000), wall(5000, 0, 5000, along="y"))])
    assert "trop épais" in e.value.message or "distinct" in e.value.message


def test_surfaces_only_file(tmp_path):
    with pytest.raises(AnalysisFailed) as e:
        analyse(tmp_path, [flat_face()])
    assert "aucun solide" in e.value.message


@pytest.mark.parametrize("content", [b"", b"ceci n'est pas un STEP", b"ISO-10303-21;\nHEADER;\ntronque"])
def test_corrupt_files_give_a_clear_error(tmp_path, content):
    p = tmp_path / "x.step"
    p.write_bytes(content)
    with pytest.raises(AnalysisFailed) as e:
        StepPlanAnalyzer().analyse(_plan(p))
    assert "illisible" in e.value.message


def test_determinism(tmp_path):
    shapes = [cut(wall(0, 0, 5000), box(1000, -300, 900, 1200, 600, 1000)), wall(5000, 0, 4000, along="y")]
    assert analyse(tmp_path, shapes) == analyse(tmp_path, shapes, name="t2.step")


# --- intégration -------------------------------------------------------------------------
def test_dispatcher_routes_step_and_stp_to_the_real_analyzer(tmp_path):
    from brikia.adapters.analyzers.dispatch import build_plan_analyzer
    from brikia.config import Settings

    d = build_plan_analyzer(Settings(_env_file=None))
    for ext in (".step", ".stp"):
        path = tmp_path / f"t{ext}"
        write(path, [wall(0, 0, 5000)])
        assert d.analyse(_plan(path)).source == "step"


def test_full_pipeline_with_a_step_upload(chef, tmp_path):
    c, csrf = chef
    path = tmp_path / "petit_batiment.stp"
    write(path, [cut(wall(0, 0, 8000), box(1000, -300, 900, 1200, 600, 1000), box(4000, -300, -10, 900, 600, 2110)),
                 wall(8000, 0, 6000, along="y"), wall(0, 6000, 8000), wall(0, 0, 6000, along="y")])
    pid = c.post("/api/projects", headers=csrf, data={"nom": "STEP"},
                 files={"fichier": ("petit_batiment.stp", path.read_bytes())}).json()["id"]
    d = c.post(f"/api/projects/{pid}/analyse", headers=csrf).json()
    assert d["analysis_source"] == "step" and len(d["walls"]) == 4
    assert sum(len(w["openings"]) for w in d["walls"]) == 2
    assert c.post(f"/api/projects/{pid}/calepinage", headers=csrf).status_code == 200
