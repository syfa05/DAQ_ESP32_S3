import json
from decimal import Decimal

import pytest

from brikia.adapters.layout.rule_based import DefaultRuleBasedLayoutEngine
from brikia.adapters.layout.rules_config import LayoutRules
from brikia.domain.enums import ShapeCategory as C
from brikia.domain.bom import BomRow, build_bom
from brikia.domain.geometry import OpeningGeometry as O
from brikia.domain.geometry import WallGeometry as W
from brikia.domain.layout import BrickShapeInput as S
from brikia.domain.layout import LayoutImpossible, WallInput

BTC, PARP = "BTC autobloquante", "Parpaing autobloquant"


def shapes(**unavailable):
    """Même bibliothèque que la migration ; ``unavailable`` : codes à désactiver."""
    base = [
        (1, "BTC_STD", BTC, C.STANDARD), (2, "BTC_ANGLE", BTC, C.ANGLE),
        (3, "BTC_CHAINAGE", BTC, C.CHAINAGE), (4, "BTC_LINTEAU", BTC, C.LINTEAU),
        (5, "PARP_STD", PARP, C.STANDARD), (6, "PARP_ANGLE", PARP, C.ANGLE),
    ]
    return [S(i, code, code, prod, cat, code not in unavailable) for i, code, prod, cat in base]


def wall(id_=1, l=4000, h=2500, corner=False, openings=()):
    return WallInput(id_, W(f"M{id_}", l, h, corner, tuple(openings)))


ENGINE = DefaultRuleBasedLayoutEngine()


def q(result, i=0):
    return result.walls[i].quantities


# --- Murs : valeurs calculées à la main (voir docstring du moteur) -------------
def test_plain_wall_without_opening():
    # 4000×2500 : brut ceil(10 000 000/21 600)=463 ; ×1,05 -> 487 ;
    # chaînage ceil(48,7)=49 ; standard 438.
    r = ENGINE.calculate([wall()], shapes())
    assert q(r) == {1: 438, 3: 49}
    assert sum(q(r).values()) == 487
    assert r.warnings == ()
    assert r.indicators == {"demi_blocs_estimes": 30}  # ceil(487 × 6 %)


def test_wall_with_door_adds_lintel_blocks():
    # porte 900×2100 : net 8 110 000 -> 376 -> 395 ; linteau ceil(1300/240)=6 ;
    # corps 389 ; chaînage 39 ; standard 350.
    r = ENGINE.calculate([wall(openings=[O("porte", 900, 2100)])], shapes())
    assert q(r) == {1: 350, 3: 39, 4: 6}
    assert sum(q(r).values()) == 395


def test_corner_wall_adds_corner_stack():
    # 28 assises -> 28 blocs d'angle ; corps 459 ; chaînage 46 ; standard 413.
    r = ENGINE.calculate([wall(corner=True)], shapes())
    assert q(r) == {1: 413, 2: 28, 3: 46}
    assert sum(q(r).values()) == 487  # l'angle est prélevé sur le total


def test_ceiling_helps_never_undercounts():
    """Jamais moins de blocs que la surface nette ne l'exige."""
    r = ENGINE.calculate([wall(l=1234, h=1111)], shapes())
    assert sum(q(r).values()) * 240 * 90 >= 1234 * 1111


def test_no_negative_quantities_when_corner_and_lintel_exceed_total():
    tiny = wall(l=500, h=2700, corner=True, openings=[O("porte", 400, 2000)])
    r = ENGINE.calculate([tiny], shapes())
    assert all(v > 0 for v in q(r).values())
    # net 550 000 -> 28 blocs ; angle 30 + linteau ceil(800/240)=4 dépassent le total
    assert q(r) == {2: 30, 4: 4}  # corps ramené à 0, aucune quantité négative


def test_multiple_walls_are_independent_and_ordered():
    r = ENGINE.calculate([wall(1), wall(2, corner=True)], shapes())
    assert [w.wall_id for w in r.walls] == [1, 2]
    assert q(r, 0) == {1: 438, 3: 49} and q(r, 1) == {1: 413, 2: 28, 3: 46}


def test_deterministic():
    ws = [wall(1), wall(2, corner=True, openings=[O("fenetre", 1200, 1200)])]
    assert ENGINE.calculate(ws, shapes()) == ENGINE.calculate(ws, shapes())


# --- Disponibilité des moules -------------------------------------------------
def test_unavailable_preferred_product_falls_back_with_warning():
    r = ENGINE.calculate([wall(corner=True)], shapes(BTC_ANGLE=1))
    assert q(r) == {1: 413, 6: 28, 3: 46}  # angle -> PARP_ANGLE
    assert len(r.warnings) == 1 and "Parpaing autobloquant" in r.warnings[0]


def test_standard_body_switches_product_with_warning():
    r = ENGINE.calculate([wall()], shapes(BTC_STD=1))
    assert q(r) == {5: 438, 3: 49}
    assert any("PARP_STD" in w for w in r.warnings)


def test_missing_category_falls_back_to_standard_mold():
    r = ENGINE.calculate([wall(corner=True)], shapes(BTC_ANGLE=1, PARP_ANGLE=1))
    assert q(r) == {1: 413 + 28, 3: 46}  # angle fusionné dans le standard
    assert any("à la place" in w for w in r.warnings)


def test_missing_lintel_and_chainage_molds():
    r = ENGINE.calculate([wall(openings=[O("porte", 900, 2100)])],
                         shapes(BTC_LINTEAU=1, BTC_CHAINAGE=1))
    assert q(r) == {1: 395}
    assert len(r.warnings) == 2


def test_no_standard_mold_makes_layout_impossible():
    with pytest.raises(LayoutImpossible) as e:
        ENGINE.calculate([wall()], shapes(BTC_STD=1, PARP_STD=1))
    assert "standard" in e.value.message


def test_unneeded_unavailable_mold_is_harmless():
    r = ENGINE.calculate([wall()], shapes(BTC_LINTEAU=1, BTC_ANGLE=1))
    assert r.warnings == () and q(r) == {1: 438, 3: 49}


def test_warning_emitted_once_across_walls():
    r = ENGINE.calculate([wall(1, corner=True), wall(2, corner=True)], shapes(BTC_ANGLE=1))
    assert len(r.warnings) == 1


def test_empty_wall_list():
    r = ENGINE.calculate([], shapes())
    assert r.walls == () and r.estimated_duration_min == 0 and r.indicators == {}


# --- Durée de démonstration -------------------------------------------------------
def test_duration_uses_demo_rates_and_changeovers():
    # 438/240 h = 109,5 min ; 49/120 h = 24,5 min ; + 2 moules × 30 min = 194.
    assert ENGINE.calculate([wall()], shapes()).estimated_duration_min == 194


def test_duration_uses_rate_of_the_shape_actually_used():
    r = ENGINE.calculate([wall(corner=True)], shapes(BTC_ANGLE=1, PARP_ANGLE=1))
    # 441 standards (110,25 min) + 46 chaînage (23 min) + 2 × 30 = ceil(193,25)
    assert r.estimated_duration_min == 194


# --- Règles configurables et identifiées comme temporaires --------------------------
def test_rules_are_configurable_and_recorded():
    e = DefaultRuleBasedLayoutEngine(LayoutRules.from_overrides(
        {"waste_margin": "0", "chainage_ratio": "0"}))
    assert q(e.calculate([wall()], shapes())) == {1: 463}
    p = ENGINE.calculate([wall()], shapes()).parameters
    assert p["temporaire"] is True and p["waste_margin"] == "0.05"
    json.dumps(p)  # sérialisable pour l'audit


def test_rules_from_file_and_unknown_key(tmp_path):
    f = tmp_path / "rules.json"
    f.write_text(json.dumps({"lintel_bearing_mm": 300,
                             "production_rate_per_hour": {"standard": 100}}))
    r = LayoutRules.from_file(f)
    assert r.lintel_bearing_mm == 300
    assert r.production_rate_per_hour["standard"] == Decimal(100)
    assert r.production_rate_per_hour["angle"] == Decimal(120)  # fusion, pas remplacement
    with pytest.raises(ValueError):
        LayoutRules.from_overrides({"inconnue": 1})


def test_decimal_margin_has_no_float_artifact():
    """100 × 1,05 vaut exactement 105 (en float : 105,00000000000001 -> 106)."""
    e = DefaultRuleBasedLayoutEngine(LayoutRules.from_overrides(
        {"chainage_ratio": "0"}))
    # face de bloc = 240×90 ; mur de 100 faces exactement : 2400 × 900
    r = e.calculate([wall(l=2400, h=900)], shapes())
    assert sum(q(r).values()) == 105


# --- BOM ---------------------------------------------------------------------------
def test_build_bom_groups_by_shape_in_stable_order():
    rows = [
        BomRow(2, "M2", 3, "BTC_CHAINAGE", "Ch", BTC, "chainage", 5),
        BomRow(1, "M1", 1, "BTC_STD", "Std", BTC, "standard", 10),
        BomRow(2, "M2", 1, "BTC_STD", "Std", BTC, "standard", 7),
        BomRow(1, "M1", 3, "BTC_CHAINAGE", "Ch", BTC, "chainage", 2),
    ]
    bom = build_bom(rows)
    assert [ln.code for ln in bom] == ["BTC_STD", "BTC_CHAINAGE"]
    assert bom[0].total == 17 and bom[0].per_wall == [(1, "M1", 10), (2, "M2", 7)]
    assert bom[1].total == 7


# --- Dimensions des moules, demi-blocs et appuis (calculs faits à la main) ----------------------
def lib(extra=()):
    """Bibliothèque avec dimensions : BTC 300×150×100, linteau 450, appui 450, demi 150."""
    rows = [
        (1, "BTC_STD", BTC, C.STANDARD, 300, 150, 100), (2, "BTC_CHAINAGE", BTC, C.CHAINAGE, 300, 150, 100),
        (3, "BTC_LINTEAU", BTC, C.LINTEAU, 450, 150, 100), (4, "BTC_ANGLE", BTC, C.ANGLE, 300, 150, 100),
        *extra,
    ]
    return [S(i, code, code, prod, cat, True, L, l, h) for i, code, prod, cat, L, l, h in rows]


def test_block_dimensions_come_from_the_standard_mold():
    # 4000×2500 : face 300×100 = 30 000 -> ceil(333,33) = 334 ; ×1,05 -> 351 ; chaînage 36.
    r = ENGINE.calculate([wall()], lib())
    assert q(r) == {1: 315, 2: 36} and sum(q(r).values()) == 351
    assert r.parameters["block_length_mm"] == 300 and r.parameters["block_height_mm"] == 100
    assert r.parameters["dimensions_depuis_les_moules"] is True


def test_corner_courses_use_mold_height():
    # 2500 / 100 = 25 assises -> 25 blocs d'angle (et non 28 avec la brique par défaut de 90 mm).
    r = ENGINE.calculate([wall(corner=True)], lib())
    assert q(r)[4] == 25


def test_demi_blocks_become_a_real_quantity_when_a_mold_exists():
    demi = (5, "BTC_DEMI", BTC, C.DEMI, 150, 150, 100)
    r = ENGINE.calculate([wall()], lib([demi]))
    # corps 351 ; chaînage 36 ; demi ceil(351 × 6 %) = 22 ; standard 293.
    assert q(r) == {1: 293, 2: 36, 5: 22} and sum(q(r).values()) == 351
    assert "demi_blocs_estimes" not in r.indicators


def test_sills_use_mold_length_and_are_taken_from_the_total():
    extra = [(5, "BTC_DEMI", BTC, C.DEMI, 150, 150, 100), (6, "BTC_APPUI", BTC, C.APPUI, 450, 150, 80)]
    w = wall(openings=[O("fenetre", 1200, 1200)])
    # net 8 560 000 -> 286 -> 301 ; linteau ceil(1600/450)=4 ; appui ceil(1200/450)=3 ;
    # corps 294 ; chaînage 30 ; demi 18 ; standard 246.
    r = ENGINE.calculate([w], lib(extra))
    assert q(r) == {1: 246, 2: 30, 3: 4, 5: 18, 6: 3} and sum(q(r).values()) == 301
    # Une porte n'a pas d'appui.
    r2 = ENGINE.calculate([wall(openings=[O("porte", 900, 2100)])], lib(extra))
    assert 6 not in q(r2)


def test_optional_molds_of_another_product_are_ignored():
    parp_demi = (5, "PARP_DEMI", PARP, C.DEMI, 200, 200, 200)
    r = ENGINE.calculate([wall()], lib([parp_demi]))
    assert 5 not in q(r) and "demi_blocs_estimes" in r.indicators


def test_mold_cadence_overrides_category_rate_in_duration():
    base = lib()
    fast = [S(s.id, s.code, s.nom, s.produit, s.categorie, True, s.longueur_mm, s.largeur_mm,
              s.hauteur_mm, 100_000) for s in base]
    slow = ENGINE.calculate([wall()], base).estimated_duration_min
    assert ENGINE.calculate([wall()], fast).estimated_duration_min < slow
