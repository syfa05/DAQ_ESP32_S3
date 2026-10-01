"""IfcPlanAnalyzer sur des IFC synthétiques dont on connaît exactement la géométrie."""

import hashlib
import os
import threading
from pathlib import Path

import pytest

pytest.importorskip("ifcopenshell")
pytest.importorskip("shapely")

from brikia.adapters.analyzers._native import silence_native_stdout
from brikia.adapters.analyzers.base import PlanFile
from brikia.adapters.analyzers.ifc import IfcPlanAnalyzer
from brikia.domain.errors import AnalysisFailed
from brikia.domain.geometry import validate_geometry
from ifc_factory import OpeningSpec as O
from ifc_factory import WallSpec as W
from ifc_factory import build


def analyse(tmp_path, walls, **kw):
    path = tmp_path / "t.ifc"
    build(path, walls, **kw)
    return IfcPlanAnalyzer().analyse(_plan(path))


def _plan(path: Path) -> PlanFile:
    data = path.read_bytes()
    return PlanFile(path, path.name, ".ifc", len(data), hashlib.sha256(data).hexdigest())


def dims(geo):
    return [(w.nom, w.longueur_mm, w.hauteur_mm, w.is_corner,
             [(o.type, o.largeur_mm, o.hauteur_mm) for o in w.openings]) for w in geo.walls]


# --- murs droits --------------------------------------------------------------------
def test_straight_wall_dimensions_in_mm(tmp_path):
    geo = analyse(tmp_path, [W("Façade", [(0, 0), (5, 0)], 2.7, 0.2)])
    assert dims(geo) == [("RDC · Façade n°1", 5000, 2700, False, [])]
    assert geo.source == "ifc" and "IfcOpenShell" in geo.notes[0]
    validate_geometry(geo)


def test_openings_take_their_type_from_the_filling_and_their_size_from_the_hole(tmp_path):
    geo = analyse(tmp_path, [W("Façade", [(0, 0), (6, 0)], 2.7, 0.3, openings=[
        O("door", 0.5, 0.9, 2.1), O("window", 2.5, 1.2, 1.0, sill=0.9), O("none", 4.5, 0.7, 2.0)])])
    (w,) = geo.walls
    assert sorted((o.type, o.largeur_mm, o.hauteur_mm) for o in w.openings) == [
        ("fenetre", 1200, 1000), ("ouverture", 700, 2000), ("porte", 900, 2100)]
    assert w.net_area_mm2 == 6000 * 2700 - (900 * 2100 + 1200 * 1000 + 700 * 2000)


def test_slab_opening_is_not_a_wall_opening(tmp_path):
    geo = analyse(tmp_path, [W("M", [(0, 0), (4, 0)])], extra_slab_opening=True)
    assert len(geo.walls) == 1 and geo.walls[0].openings == ()


@pytest.mark.parametrize("schema", ["IFC2X3", "IFC4", "IFC4X3_ADD2"])
def test_same_result_in_every_ifc_schema(tmp_path, schema):
    """Les exports du marché sont en IFC2X3 (Revit, ArchiCAD), IFC4 ou IFC4X3."""
    geo = analyse(tmp_path, [W("Façade", [(0, 0), (5, 0), (5, 3)], 2.7, 0.25, openings=[O("door", 1.0, 0.9, 2.1)])],
                  schema=schema)
    assert dims(geo) == [("RDC · Façade n°1.1", 5000, 2700, True, [("porte", 900, 2100)]),
                         ("RDC · Façade n°1.2", 3000, 2700, True, [])]
    assert schema.split("_")[0] in geo.notes[0]


# --- axes polygonaux, angles ---------------------------------------------------------
def test_polyline_axis_is_split_into_straight_walls_with_corners(tmp_path):
    geo = analyse(tmp_path, [W("Retour", [(0, 0), (4, 0), (4, 3)], 2.5, 0.2)])
    assert dims(geo) == [("RDC · Retour n°1.1", 4000, 2500, True, []),
                         ("RDC · Retour n°1.2", 3000, 2500, True, [])]
    assert any("découpé" in n for n in geo.notes)


def test_closed_contour_gives_four_corner_walls(tmp_path):
    geo = analyse(tmp_path, [W("Pièce", [(0, 0), (6, 0), (6, 4), (0, 4), (0, 0)])])
    assert sorted((w.longueur_mm, w.is_corner) for w in geo.walls) == [(4000, True), (4000, True), (6000, True), (6000, True)]


def test_aligned_walls_and_t_junctions_are_not_corners(tmp_path):
    geo = analyse(tmp_path, [W("A", [(0, 0), (5, 0)]), W("B", [(5, 0), (10, 0)]),     # alignés
                             W("Mur T", [(2.5, -4), (2.5, -0.1)])])                    # contre le milieu de A
    assert [w.is_corner for w in geo.walls] == [False, False, False]


def test_corners_never_connect_different_storeys(tmp_path):
    geo = analyse(tmp_path, [W("A", [(0, 0), (5, 0)], storey=0), W("B", [(5, 0), (5, 4)], storey=1)],
                  storeys=(("RDC", 0.0), ("R+1", 3.0)))
    assert [(w.nom, w.is_corner) for w in geo.walls] == [("RDC · A n°1", False), ("R+1 · B n°1", False)]


# --- unités, placements --------------------------------------------------------------
def test_millimetre_project_gives_the_same_result_as_metre_project(tmp_path):
    spec = lambda: [W("Façade", [(0, 0), (5, 0), (5, 3)], 2.7, 0.25, openings=[O("door", 1, 0.9, 2.1)], gross_factor=0.9)]  # noqa: E731
    metres = analyse(tmp_path, spec(), unit="METRE")
    mm = analyse(tmp_path, spec(), unit="MILLIMETRE")
    assert dims(metres) == dims(mm)
    assert dims(mm)[0][1:3] == (5000, 2430)


def test_rotated_and_translated_wall_keeps_true_length_and_opening_width(tmp_path):
    geo = analyse(tmp_path, [W("Oblique", [(0, 0), (5, 0)], 2.7, 0.2, origin=(10, 5), rotation_deg=30,
                               openings=[O("door", 1.0, 0.8, 2.1)])])
    assert dims(geo) == [("RDC · Oblique n°1", 5000, 2700, False, [("porte", 800, 2100)])]


# --- hauteur ------------------------------------------------------------------------
def test_height_follows_the_files_gross_side_area_when_plausible(tmp_path):
    """Mur recoupé par un toit : surface brute du fichier = 80 % de L × H."""
    geo = analyse(tmp_path, [W("Pignon", [(0, 0), (5, 0)], 2.7, 0.2, gross_factor=0.8)])
    assert geo.walls[0].hauteur_mm == 2160
    assert not any("Hauteur issue de la géométrie" in n for n in geo.notes)


def test_implausible_quantity_falls_back_to_geometry_height(tmp_path):
    geo = analyse(tmp_path, [W("Bizarre", [(0, 0), (5, 0)], 2.7, 0.2, gross_factor=3.0)])
    assert geo.walls[0].hauteur_mm == 2700
    assert any("Hauteur issue de la géométrie" in n for n in geo.notes)


# --- robustesse ---------------------------------------------------------------------
def test_wall_without_axis_length_is_rebuilt_from_its_volume(tmp_path):
    geo = analyse(tmp_path, [W("Sans axe", [(0, 0), (5, 0)], with_axis=False)])
    assert dims(geo)[0][1:4] == (5000, 2700, False)
    assert any("sans axe exploitable" in n for n in geo.notes)


def test_opening_wider_than_its_wall_is_clamped_to_the_wall(tmp_path):
    geo = analyse(tmp_path, [W("Petit", [(0, 0), (2, 0)], 2.5, 0.2, openings=[O("window", -0.2, 2.4, 1.0, sill=1.0)])])
    (o,) = geo.walls[0].openings
    assert (o.largeur_mm, o.hauteur_mm) == (2000, 1000)   # largeur ramenée à celle du mur
    assert any("ramenée" in n for n in geo.notes)
    validate_geometry(geo)


def test_walls_entirely_filled_by_openings_stay_valid(tmp_path):
    geo = analyse(tmp_path, [W("Vitrine", [(0, 0), (2, 0)], 2.5, 0.2, openings=[O("window", 0.0, 2.0, 2.5)])])
    validate_geometry(geo)   # net > 0 : l'ouverture qui occupe tout le mur est retirée
    assert geo.walls[0].net_area_mm2 > 0


def test_tiny_segments_are_dropped(tmp_path):
    geo = analyse(tmp_path, [W("Tige", [(0, 0), (3, 0), (3, 0.1)])])
    assert [w.longueur_mm for w in geo.walls] == [3000]
    assert any("moins de 150 mm" in n for n in geo.notes)


def test_same_named_walls_are_numbered_and_levels_ordered_by_elevation(tmp_path):
    geo = analyse(tmp_path, [W("Cloison", [(0, 0), (3, 0)], storey=1), W("Cloison", [(0, 2), (3, 2)], storey=1),
                             W("Cloison", [(0, 0), (3, 0)], storey=0)],
                  storeys=(("RDC", 0.0), ("R+1", 3.0)))
    assert [w.nom for w in geo.walls] == ["RDC · Cloison n°1", "R+1 · Cloison n°1", "R+1 · Cloison n°2"]


def test_analysis_is_deterministic(tmp_path):
    walls = [W("A", [(0, 0), (5, 0), (5, 4)], openings=[O("door", 1)]), W("B", [(0, 4), (5, 4)])]
    assert analyse(tmp_path, walls) == analyse(tmp_path, walls)


# --- erreurs en français, fichier inchangé ----------------------------------------------
def test_file_without_walls_is_refused(tmp_path):
    with pytest.raises(AnalysisFailed) as e:
        analyse(tmp_path, [])
    assert "Aucun mur" in e.value.message


def test_walls_without_geometry_are_refused(tmp_path):
    with pytest.raises(AnalysisFailed) as e:
        analyse(tmp_path, [W("Fantôme", with_body=False, with_axis=False)])
    assert "géométrie exploitable" in e.value.message


@pytest.mark.parametrize("content", [b"", b"ceci n'est pas un IFC", b"ISO-10303-21;\nHEADER;\nFILE_SCHEMA(('IFC4'));\n"])
def test_corrupt_files_give_a_clear_error(tmp_path, content):
    path = tmp_path / "x.ifc"
    path.write_bytes(content)
    with pytest.raises(AnalysisFailed) as e:
        IfcPlanAnalyzer().analyse(_plan(path))
    assert "illisible" in e.value.message or "Aucun mur" in e.value.message


# --- sortie standard ------------------------------------------------------------------
def test_native_stdout_is_silenced_then_restored(capfd):
    with silence_native_stdout():
        os.write(1, b"BRUIT NATIF\n")
    os.write(1, b"VISIBLE\n")
    out = capfd.readouterr().out
    assert "BRUIT NATIF" not in out and "VISIBLE" in out


def test_concurrent_silencing_never_leaves_stdout_redirected(capfd):
    def work():
        for _ in range(20):
            with silence_native_stdout():
                os.write(1, b"x")
    threads = [threading.Thread(target=work) for _ in range(6)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    os.write(1, b"APRES\n")
    assert "APRES" in capfd.readouterr().out
