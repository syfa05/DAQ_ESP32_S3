"""DxfPlanAnalyzer : cas synthétiques (géométrie connue) puis plans réels fournis par l'utilisateur."""

import hashlib
import math
from pathlib import Path

import pytest

ezdxf = pytest.importorskip("ezdxf")

from brikia.adapters.analyzers.base import PlanFile
from brikia.adapters.analyzers.dxf import DxfOptions, DxfPlanAnalyzer
from brikia.domain.errors import AnalysisFailed
from brikia.domain.geometry import validate_geometry

FIXTURES = Path(__file__).parent / "fixtures" / "dxf"


def plan(path: Path) -> PlanFile:
    data = path.read_bytes()
    return PlanFile(path, path.name, ".dxf", len(data), hashlib.sha256(data).hexdigest())


def make(tmp_path, *, insunits=4, lines=(), polys=(), name="t.dxf"):
    """lines : (calque, (x0, y0), (x1, y1)) ; polys : (calque, [points], fermée)."""
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = insunits
    msp = doc.modelspace()
    for layer, a, b in lines:
        if layer not in doc.layers:
            doc.layers.add(layer)
        msp.add_line(a, b, dxfattribs={"layer": layer})
    for layer, pts, closed in polys:
        if layer not in doc.layers:
            doc.layers.add(layer)
        msp.add_lwpolyline(pts, close=closed, dxfattribs={"layer": layer})
    path = tmp_path / name
    doc.saveas(path)
    return path


def wall(layer, x0, y0, x1, y1, t=200.0):
    """Les deux faces d'un mur horizontal ou vertical d'axe (x0,y0)-(x1,y1) et d'épaisseur t."""
    if y0 == y1:
        return [(layer, (x0, y0 - t / 2), (x1, y1 - t / 2)), (layer, (x0, y0 + t / 2), (x1, y1 + t / 2))]
    return [(layer, (x0 - t / 2, y0), (x1 - t / 2, y1)), (layer, (x0 + t / 2, y0), (x1 + t / 2, y1))]


def run(path, **opts):
    return DxfPlanAnalyzer(DxfOptions(**opts)).analyse(plan(path))


def summary(geo):
    return [(w.nom, w.longueur_mm, w.is_corner, [(o.type, o.largeur_mm, o.hauteur_mm) for o in w.openings])
            for w in geo.walls]


# --- murs ---------------------------------------------------------------------------
def test_two_parallel_faces_make_one_wall_with_default_height(tmp_path):
    geo = run(make(tmp_path, lines=wall("WALL", 0, 0, 5000, 0)))
    assert summary(geo) == [("Wall n°1", 5000, False, [])]
    assert geo.walls[0].hauteur_mm == 2700 and geo.source == "dxf"
    assert geo.notes[0].startswith("APPROXIMATION") and "2700 mm" in geo.notes[0]
    validate_geometry(geo)


def test_height_defaults_are_configurable(tmp_path):
    path = make(tmp_path, lines=wall("WALL", 0, 0, 5000, 0) + [("DOOR", (1000, 0), (1900, 0))])
    geo = run(path, wall_height_mm=3000, door_height_mm=2200)
    assert geo.walls[0].hauteur_mm == 3000 and geo.walls[0].openings[0].hauteur_mm == 2200


def test_l_junction_uses_axis_lengths_and_flags_both_walls(tmp_path):
    """Face extérieure plus longue que la face intérieure aux angles : la longueur retenue est celle de l'axe."""
    lines = [("WALL", (-100, -100), (5000, -100)), ("WALL", (100, 100), (5000, 100)),     # mur horizontal
             ("WALL", (-100, -100), (-100, 4000)), ("WALL", (100, 100), (100, 4000))]      # mur vertical
    geo = run(make(tmp_path, lines=lines))
    assert sorted((w.longueur_mm, w.is_corner) for w in geo.walls) == [(4000, True), (5000, True)]


def test_closed_room_has_four_corner_walls(tmp_path):
    outer = [(0, 0), (6000, 0), (6000, 4000), (0, 4000)]
    inner = [(200, 200), (5800, 200), (5800, 3800), (200, 3800)]
    geo = run(make(tmp_path, polys=[("MUR", outer, True), ("MUR", inner, True)]))
    assert len(geo.walls) == 4 and all(w.is_corner for w in geo.walls)
    assert sorted(w.longueur_mm for w in geo.walls) == [3800, 3800, 5800, 5800]


@pytest.mark.parametrize("slope_mm", [0.8, -0.8])
def test_slightly_tilted_faces_on_both_sides_of_the_axis_still_pair(tmp_path, slope_mm):
    """Bruit de dessin : deux faces quasi horizontales dont les angles sont de signes opposés."""
    lines = [("WALL", (0, 0), (5000, slope_mm)), ("WALL", (0, 200), (5000, 200 - slope_mm)),
             ("WALL", (0, 3000), (0.5, 8000)), ("WALL", (200, 3000), (200 - 0.5, 8000))]   # quasi vertical
    geo = run(make(tmp_path, lines=lines))
    assert sorted(w.longueur_mm for w in geo.walls) == [5000, 5000]
    assert not any("un seul trait" in n for n in geo.notes)


def test_neighbouring_walls_are_not_merged_into_a_false_thick_wall(tmp_path):
    """Faces à 0, 100, 400, 500 : deux murs de 100 (pas un mur de 300 entre les deux)."""
    lines = wall("WALL", 0, 50, 4000, 50, 100) + wall("WALL", 0, 450, 4000, 450, 100)
    geo = run(make(tmp_path, lines=lines))
    assert [w.longueur_mm for w in geo.walls] == [4000, 4000]


def test_wall_drawn_with_a_single_line_is_kept_and_flagged(tmp_path):
    geo = run(make(tmp_path, lines=[("PARTITION", (0, 0), (3000, 0))]))
    assert [w.longueur_mm for w in geo.walls] == [3000]
    assert any("un seul trait" in n for n in geo.notes)


def test_faces_too_thin_or_too_far_apart_are_not_paired(tmp_path):
    lines = [("WALL", (0, 0), (3000, 0)), ("WALL", (0, 20), (3000, 20)),            # 20 mm : trop mince
             ("WALL", (0, 5000), (3000, 5000)), ("WALL", (0, 5900), (3000, 5900))]  # 900 mm : trop épais
    geo = run(make(tmp_path, lines=lines))
    assert len(geo.walls) == 4 and sum("un seul trait" in n for n in geo.notes) == 1


def test_walls_inside_blocks_are_found(tmp_path):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    block = doc.blocks.new("MURBLOC")
    for _, a, b in wall("0", 0, 0, 4000, 0):
        block.add_line(a, b, dxfattribs={"layer": "0"})
    doc.layers.add("MURS")
    doc.modelspace().add_blockref("MURBLOC", (1000, 500), dxfattribs={"layer": "MURS"})
    p = tmp_path / "b.dxf"
    doc.saveas(p)
    assert summary(run(p)) == [("Murs n°1", 4000, False, [])]


def test_arcs_on_wall_layers_are_ignored_with_a_note(tmp_path):
    doc = ezdxf.new("R2010")
    doc.header["$INSUNITS"] = 4
    doc.layers.add("WALL")
    msp = doc.modelspace()
    for _, a, b in wall("WALL", 0, 0, 4000, 0):
        msp.add_line(a, b, dxfattribs={"layer": "WALL"})
    msp.add_arc((2000, 2000), 500, 0, 90, dxfattribs={"layer": "WALL"})
    p = tmp_path / "a.dxf"
    doc.saveas(p)
    geo = run(p)
    assert len(geo.walls) == 1 and any("arc" in n for n in geo.notes)


# --- ouvertures -----------------------------------------------------------------------
def test_door_and_window_markers_become_openings_with_default_heights(tmp_path):
    lines = wall("WALL", 0, 0, 6000, 0, 200) + [
        ("DOOR", (500, 0), (1400, 0)), ("DOOR", (500, 100), (500, -100)), ("DOOR", (1400, 100), (1400, -100)),  # repère + jambages
        ("WINDOW", (3000, 0), (4500, 0))]
    geo = run(make(tmp_path, lines=lines))
    (w,) = geo.walls
    assert sorted((o.type, o.largeur_mm, o.hauteur_mm) for o in w.openings) == [("fenetre", 1500, 1200), ("porte", 900, 2100)]
    validate_geometry(geo)


def test_duplicate_markers_of_one_window_count_once(tmp_path):
    lines = wall("WALL", 0, 0, 6000, 0, 200) + [("WINDOW", (3000, y), (4500, y)) for y in (-30, 0, 30)]
    geo = run(make(tmp_path, lines=lines))
    assert len(geo.walls[0].openings) == 1


def test_perpendicular_jamb_lines_are_not_openings_nor_orphans(tmp_path):
    lines = wall("WALL", 0, 0, 6000, 0, 300) + [
        ("DOOR", (500, 0), (1400, 0)), ("DOOR", (500, 150), (500, -150)), ("DOOR", (1400, 150), (1400, -150))]
    geo = run(make(tmp_path, lines=lines))
    assert len(geo.walls[0].openings) == 1 and not any("sans mur" in n for n in geo.notes)


def test_marker_on_no_wall_is_reported_and_walls_are_kept(tmp_path):
    lines = wall("WALL", 0, 0, 6000, 0) + [("DOOR", (500, 3000), (1400, 3000))]
    geo = run(make(tmp_path, lines=lines))
    assert len(geo.walls) == 1 and geo.walls[0].openings == ()
    assert any("sans mur correspondant" in n for n in geo.notes)


def test_vertical_wall_opening(tmp_path):
    lines = wall("WALL", 0, 0, 0, 5000) + [("DOOR", (0, 1000), (0, 1900))]
    geo = run(make(tmp_path, lines=lines))
    assert summary(geo)[0][3] == [("porte", 900, 2100)]


# --- unités ---------------------------------------------------------------------------
@pytest.mark.parametrize(("insunits", "scale", "expected_note"), [
    (4, 1.0, "(en-tête du fichier)"),                          # mm déclarés, dessin en mm
    (6, 0.001, "(en-tête du fichier)"),                        # m déclarés, dessin en m
    (4, 0.001, "annonce « mm »"),                              # dessin en mètres mais en-tête faux (cas réel IFC Builder)
    (0, 0.001, "ne précise pas l'unité"),                      # en-tête absent
    (5, 0.1, "(en-tête du fichier)"),                          # cm
])
def test_unit_detection_gives_the_same_walls_whatever_the_declared_unit(tmp_path, insunits, scale, expected_note):
    lines = [(lay, (a[0] * scale, a[1] * scale), (b[0] * scale, b[1] * scale))
             for lay, a, b in wall("WALL", 0, 0, 8000, 0, 200) + wall("WALL", 8000, 0, 8000, 6000, 200)]
    geo = run(make(tmp_path, insunits=insunits, lines=lines))
    assert sorted(w.longueur_mm for w in geo.walls) == [6000, 8000]
    assert expected_note in geo.notes[1]


def test_absurd_dimensions_are_refused(tmp_path):
    with pytest.raises(AnalysisFailed) as e:
        run(make(tmp_path, insunits=4, lines=wall("WALL", 0, 0, 5e9, 0)))
    assert "incompatibles avec un bâtiment" in e.value.message


# --- calques / erreurs ----------------------------------------------------------------
def test_no_wall_layer_lists_the_layers_found(tmp_path):
    with pytest.raises(AnalysisFailed) as e:
        run(make(tmp_path, lines=[("COTATIONS", (0, 0), (5000, 0)), ("TEXTE", (0, 10), (5000, 10))]))
    assert "COTATIONS" in e.value.message and "BRIKIA_DXF_WALL_LAYERS" in e.value.message


def test_wall_layers_are_configurable(tmp_path):
    path = make(tmp_path, lines=wall("XY-STRUCT", 0, 0, 5000, 0))
    with pytest.raises(AnalysisFailed):
        run(path)
    assert len(run(path, wall_layers="struct").walls) == 1


def test_wall_layers_present_but_nothing_usable(tmp_path):
    with pytest.raises(AnalysisFailed) as e:
        # deux traits courts et éloignés : emprise plausible, mais ni vis-à-vis ni mur filaire (< 1 m)
        run(make(tmp_path, lines=[("WALL", (0, 0), (600, 0)), ("WALL", (5000, 5000), (5600, 5000))]))
    assert "Aucun mur exploitable" in e.value.message


@pytest.mark.parametrize("content", [b"", b"pas du DXF du tout", b"AC1018\x00\x00binaire dwg"])
def test_corrupt_or_dwg_files_give_a_clear_error(tmp_path, content):
    p = tmp_path / "x.dxf"
    p.write_bytes(content)
    with pytest.raises(AnalysisFailed) as e:
        DxfPlanAnalyzer().analyse(plan(p))
    assert ("illisible" in e.value.message) and "DWG" in e.value.message


def test_determinism(tmp_path):
    path = make(tmp_path, lines=wall("WALL", 0, 0, 6000, 0) + wall("WALL", 6000, 0, 6000, 4000) + [("DOOR", (500, 0), (1400, 0))])
    assert run(path) == run(path)


def test_options_come_from_settings():
    from brikia.config import Settings

    s = Settings(_env_file=None, dxf_wall_height_mm=3100, dxf_wall_layers="struct")
    o = DxfOptions.from_settings(s)
    assert o.wall_height_mm == 3100 and o.wall_layers == "struct" and o.door_height_mm == 2100


# --- plans réels (IFC Builder) ---------------------------------------------------------
REAL = {
    # fichier : (murs, portes, fenêtres) — les portes/fenêtres doivent égaler le nombre de repères dessinés
    "Demo - Single-family house (Template F0).dxf": (16, 5, 3),
    "Demo - Restaurant (Template F0).dxf": (13, 4, 2),
    "Demo - One-storey office building (Template F0).dxf": (25, 13, 6),
    "Demo - Hotel (Template F1-F2-F3).dxf": (60, 12, 8),
    "Demo - Two-storey office building (Template F1).dxf": (36, 10, 8),
}


@pytest.mark.parametrize("name", REAL)
def test_real_plans(name):
    n_walls, n_doors, n_windows = REAL[name]
    path = FIXTURES / name
    geo = run(path)
    validate_geometry(geo)
    assert len(geo.walls) == n_walls
    types = [o.type for w in geo.walls for o in w.openings]
    assert (types.count("porte"), types.count("fenetre")) == (n_doors, n_windows)
    # Contrôle indépendant : autant d'ouvertures que de repères de porte/fenêtre dessinés.
    msp = ezdxf.readfile(path).modelspace()
    assert n_doors == sum(1 for e in msp if e.dxf.layer == "DOOR" and e.dxftype() == "POLYLINE")
    assert n_windows == sum(1 for e in msp if e.dxf.layer == "WINDOW" and e.dxftype() == "POLYLINE")
    assert "mètres" in geo.notes[1]          # l'en-tête annonce « mm » à tort : unité corrigée
    assert any(w.is_corner for w in geo.walls)
    assert not any("sans mur correspondant" in n for n in geo.notes)
    assert all(w.longueur_mm >= 300 for w in geo.walls)


@pytest.mark.parametrize("name", [n for n in REAL if "Single" not in n])
def test_external_walls_follow_the_slab_outline(name):
    """La longueur des murs extérieurs reconstitués = périmètre de la dalle dessinée dans le plan (à 2 %)."""
    path = FIXTURES / name
    geo = run(path)
    external = sum(w.longueur_mm for w in geo.walls if w.nom.startswith("Mur extérieur")) / 1000
    perimeters = []
    for e in ezdxf.readfile(path).modelspace():
        if e.dxf.layer in ("FLOOR_SLAB", "SCREED") and e.dxftype() == "POLYLINE" and e.is_closed:
            pts = [tuple(v.dxf.location)[:2] for v in e.vertices]
            perimeters.append(sum(math.dist(a, b) for a, b in zip(pts, pts[1:] + pts[:1])))
    assert external == pytest.approx(max(perimeters), rel=0.02)


def test_full_pipeline_on_a_real_dxf(chef):
    c, csrf = chef
    data = (FIXTURES / "Demo - Restaurant (Template F0).dxf").read_bytes()
    pid = c.post("/api/projects", headers=csrf, data={"nom": "Restaurant DXF"},
                 files={"fichier": ("restaurant.dxf", data)}).json()["id"]
    d = c.post(f"/api/projects/{pid}/analyse", headers=csrf).json()
    assert d["analysis_source"] == "dxf" and len(d["walls"]) == 13
    assert d["analysis_notes"][0].startswith("APPROXIMATION")
    lay = c.post(f"/api/projects/{pid}/calepinage", headers=csrf)
    assert lay.status_code == 200 and lay.json()["bom"]["total_blocs"] > 1000
    assert c.post(f"/api/projects/{pid}/validation", headers=csrf).json()["status"] == "valide"
