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
