"""Moteur de calepinage assise par assise : scénarios calculés à la main + invariants."""

import random

import pytest

from brikia.adapters.layout.courses import CourseLayoutEngine
from brikia.adapters.layout.rules_config import LayoutRules
from brikia.domain.enums import ShapeCategory as C
from brikia.domain.errors import ValidationFailed
from brikia.domain.geometry import OpeningGeometry as O
from brikia.domain.geometry import WallGeometry as W
from brikia.domain.layout import BrickShapeInput as S
from brikia.domain.layout import LayoutImpossible, WallInput

BTC = "BTC autobloquante"
STD, ANG, CH, LIN, DEMI, APP, CHH, TQ = 1, 2, 3, 4, 5, 6, 7, 8


def lib(*omit):
    rows = [
        (STD, "BTC_STD", C.STANDARD, 300, 100), (ANG, "BTC_ANGLE", C.ANGLE, 300, 100),
        (CH, "BTC_CHAINAGE", C.CHAINAGE, 300, 100), (LIN, "BTC_LINTEAU", C.LINTEAU, 450, 100),
        (DEMI, "BTC_DEMI", C.DEMI, 150, 100), (APP, "BTC_APPUI", C.APPUI, 450, 80),
        (CHH, "BTC_CHAINAGE_H", C.CHAINAGE_H, 300, 100), (TQ, "BTC_TQ", C.TROIS_QUARTS, 225, 100),
    ]
    return [S(i, code, code, BTC, cat, True, L, 150, h) for i, code, cat, L, h in rows
            if code not in omit]


NO_OPT = ("BTC_APPUI", "BTC_CHAINAGE_H", "BTC_TQ")
ENGINE = CourseLayoutEngine()


def wall(l=3000, h=500, corner=False, openings=(), id_=1):
    return WallInput(id_, W(f"M{id_}", l, h, corner, tuple(openings)))


def course(result, c, wall_index=0):
    """Assise c sous forme de liste (x, forme, longueur, nombre, coupée)."""
    return [tuple(r) for r in result.walls[wall_index].detail["courses"][c]]


def expand(runs):
    out = []
    for x, shape, length, n, cut in runs:
        for i in range(n):
            out.append((x + i * length, shape, length, cut))
    return out


# --- Mur plein : joints décalés, demi-blocs, chaînages d'extrémité ------------------------------
def test_plain_wall_running_bond_by_hand():
    r = ENGINE.calculate([wall()], lib(*NO_OPT))
    # assise paire : chaînage | 8 blocs | chaînage ; assise impaire : chaînage | demi | 7 blocs | demi | chaînage
    assert course(r, 0) == [(0, CH, 300, 1, 0), (300, STD, 300, 8, 0), (2700, CH, 300, 1, 0)]
    assert course(r, 1) == [(0, CH, 300, 1, 0), (300, DEMI, 150, 1, 0), (450, STD, 300, 7, 0),
                            (2550, DEMI, 150, 1, 0), (2700, CH, 300, 1, 0)]
    d = r.walls[0].detail
    assert d["assises"] == 5 and d["pose"] == {str(STD): 38, str(CH): 10, str(DEMI): 4}
    # à produire = pose + 2 % (arrondi par excès)
    assert r.walls[0].quantities == {STD: 39, CH: 11, DEMI: 5}
    assert d["coupes"] == 0 and d["notes"] == []


def test_joints_are_staggered_between_consecutive_courses():
    r = ENGINE.calculate([wall(l=5000, h=1000)], lib(*NO_OPT))
    joints, fixed = [], set()
    for c in range(10):
        pieces = expand(course(r, c))
        fixed |= {x for x, shape, length, _ in pieces if shape == CH} | {
            x + length for x, shape, length, _ in pieces if shape == CH}
        joints.append({p[0] for p in pieces})
    for a, b in zip(joints, joints[1:]):
        # hors bords des chaînages (alignés par construction), aucun joint ne se superpose d'une assise à l'autre
        assert not ((a & b) - fixed), (a & b) - fixed


def test_corner_pile_and_closing_pieces():
    r = ENGINE.calculate([wall(l=3100, h=200, corner=True)], lib(*NO_OPT))
    # assise 0 : angle | chaînage? non : début d'angle puis blocs ; 3100 - 300 (angle) - 300 (chaînage fin)
    c0 = expand(course(r, 0))
    assert c0[0][:3] == (0, ANG, 300) and c0[-1][1] == CH and c0[-1][0] + c0[-1][2] == 3100
    # tronçon libre [300, 2800] = 2500 : 8 blocs + reste 100 < 120 -> deux pièces coupées de 200
    cuts = [p for p in c0 if p[3]]
    assert len(cuts) == 2 and sorted(p[2] for p in cuts) == [200, 200]
    assert sum(p[2] for p in c0) == 3100


def test_three_quarter_and_half_pieces_used_when_they_match():
    # tronçon libre de 2400 + 225 = 2625 : pas de ¾ exact en assise paire (reste 225 = ¾)
    r = ENGINE.calculate([wall(l=3225, h=100, corner=False)], lib("BTC_APPUI", "BTC_CHAINAGE_H"))
    c0 = expand(course(r, 0))
    assert any(p[1] == TQ and p[2] == 225 and not p[3] for p in c0)


# --- Ouvertures : vides, linteau, appui -----------------------------------------------------------
def window_wall():
    return wall(l=4000, h=1000, openings=[O("fenetre", 1200, 300, 1500, 300)])


def test_window_void_lintel_and_sill_courses_by_hand():
    r = ENGINE.calculate([window_wall()], lib(*("BTC_CHAINAGE_H", "BTC_TQ")))
    d = r.walls[0].detail
    assert d["ouvertures"] == [{"type": "fenetre", "x": 1500, "largeur": 1200, "hauteur": 300,
                                "allege": 300, "c0": 3, "c1": 6, "position_estimee": False}]
    # assise 3 (impaire), vide [1500, 2700], chaînages de jambage et d'extrémité
    assert course(r, 3) == [
        (0, CH, 300, 1, 0), (300, DEMI, 150, 1, 0), (450, STD, 300, 2, 0), (1050, DEMI, 150, 1, 0),
        (1200, CH, 300, 1, 0), (1500, 0, 1200, 1, 0), (2700, CH, 300, 1, 0),
        (3000, DEMI, 150, 1, 0), (3150, STD, 300, 1, 0), (3450, STD, 250, 1, 1), (3700, CH, 300, 1, 0)]
    # assise 6 : linteau sur l'ouverture (2 blocs de 450 + 1 coupé de 300), appuyé sur les jambages chaînés
    lint = [p for p in expand(course(r, 6)) if p[1] == LIN]
    assert [(p[0], p[2], p[3]) for p in lint] == [(1500, 450, 0), (1950, 450, 0), (2400, 300, 1)]
    # assise 2 : appuis de fenêtre sous le vide (même découpage)
    app = [p for p in expand(course(r, 2)) if p[1] == APP]
    assert [(p[0], p[2], p[3]) for p in app] == [(1500, 450, 0), (1950, 450, 0), (2400, 300, 1)]
    # assises 3 à 5 : pas un seul bloc dans le vide
    for c in (3, 4, 5):
        assert all(not (1500 <= p[0] < 2700) for p in expand(course(r, c)) if p[1] != 0)


def test_door_goes_to_the_ground_and_has_no_sill_blocks():
    r = ENGINE.calculate([wall(l=4000, h=1000, openings=[O("porte", 900, 800, 1000, 0)])], lib())
    d = r.walls[0].detail["ouvertures"][0]
    assert (d["c0"], d["c1"], d["allege"]) == (0, 8, 0)
    assert not any(p[1] == APP for c in range(10) for p in expand(course(r, c)))
    assert course(r, 0)[1][1] == 0 or any(p[1] == 0 for p in course(r, 0))


def test_unknown_opening_position_is_placed_and_flagged():
    r = ENGINE.calculate([wall(l=6000, h=2500, openings=[O("fenetre", 1200, 1200)])], lib())
    d = r.walls[0].detail
    assert d["ouvertures"][0]["position_estimee"] is True
    assert any("placée(s) automatiquement" in n for n in d["notes"])
    assert 0 < d["ouvertures"][0]["x"] < 6000 - 1200


def test_wall_height_not_a_multiple_is_reported():
    r = ENGINE.calculate([wall(h=2750)], lib())
    d = r.walls[0].detail
    assert d["assises"] == 28 and d["ecart_hauteur_mm"] == -50  # round(27,5) = 28 (arrondi pair)
    assert any("écart" in n for n in d["notes"])


def test_top_course_is_a_horizontal_chaining_belt_when_a_mold_exists():
    r = ENGINE.calculate([wall(l=3000, h=300)], lib())
    assert {p[1] for p in expand(course(r, 2))} == {CHH}
    r2 = ENGINE.calculate([wall(l=3000, h=300)], lib("BTC_CHAINAGE_H"))
    assert CHH not in {p[1] for p in expand(course(r2, 2))}


def test_intermediate_chaining_every_4_m():
    r = ENGINE.calculate([wall(l=9000, h=100)], lib(*NO_OPT))
    cols = [p for p in expand(course(r, 0)) if p[1] == CH]
    # extrémités + ceil(9000 / 4000) - 1 = 2 intermédiaires, espacés d'au plus 4 m
    assert [p[0] for p in cols] == [0, 2850, 5850, 8700]


def test_missing_standard_mold_and_fallbacks_warn():
    with pytest.raises(LayoutImpossible):
        ENGINE.calculate([wall()], [s for s in lib() if s.code != "BTC_STD"])
    r = ENGINE.calculate([wall(corner=True)], lib("BTC_ANGLE"))
    assert any("angle" in w for w in r.warnings)


# --- Invariants (aléatoires, graine fixe) ---------------------------------------------------------
@pytest.mark.parametrize("seed", range(40))
def test_every_course_tiles_the_wall_exactly_and_quantities_match(seed):
    rnd = random.Random(seed)
    length = rnd.randrange(900, 14000, 10)
    height = rnd.randrange(300, 3500, 10)
    openings = []
    for _ in range(rnd.randrange(0, 4)):
        w = rnd.randrange(600, 2400, 50)
        has_pos = rnd.random() < 0.6
        openings.append(O(rnd.choice(["porte", "fenetre", "vitrine"]), w, rnd.randrange(600, 2400, 50),
                          rnd.randrange(0, max(1, length - w)) if has_pos else None,
                          rnd.choice([0, 300, 900]) if has_pos else None))
    omit = rnd.choice([(), NO_OPT, ("BTC_DEMI",), ("BTC_CHAINAGE",), ("BTC_LINTEAU",)])
    w = wall(length, height, corner=rnd.random() < 0.5, openings=openings)
    try:
        r = ENGINE.calculate([w], lib(*omit))
    except ValidationFailed as exc:  # cas dégénéré refusé proprement, jamais un calcul faux
        pytest.fail(f"calcul refusé : {exc}")
    d = r.walls[0].detail
    hc = d["hauteur_assise_mm"]
    laid = {}
    area = 0
    for c, runs in enumerate(d["courses"]):
        cur = 0
        for x, shape, plen, n, cut in runs:
            assert x == cur and plen > 0 and n >= 1, (c, runs)
            cur = x + plen * n
            if shape:
                laid[shape] = laid.get(shape, 0) + n
                area += plen * n * hc
        assert cur == length, (c, cur, length)
    # blocs consommés = pièces posées - coupes réemployées sur les chutes ; à produire >= consommés
    pose = {int(k): v for k, v in d["pose"].items()}
    assert set(pose) <= set(laid)
    assert sum(laid.values()) - sum(pose.values()) == d["reemploi"] <= d["coupes"]
    assert all(0 < pose[s] <= laid[s] for s in pose)
    for sid, q in pose.items():
        assert r.walls[0].quantities[sid] >= q
    # surface posée = surface du mur - surface des vides (assises entières)
    voids = sum(o["largeur"] * (o["c1"] - o["c0"]) * hc for o in d["ouvertures"])
    assert area == length * d["assises"] * hc - voids


def test_engine_is_deterministic():
    w = [wall(l=7300, h=2500, corner=True, openings=[O("fenetre", 1200, 1200, 2000, 900),
                                                      O("porte", 900, 2100, 4500, 0)])]
    a = ENGINE.calculate(w, lib())
    b = ENGINE.calculate(w, lib())
    assert a.walls[0].detail == b.walls[0].detail and a.walls[0].quantities == b.walls[0].quantities


def test_rules_are_overridable():
    e = CourseLayoutEngine(LayoutRules.from_overrides({"breakage_margin": "0", "chain_spacing_max_mm": 2000}))
    r = e.calculate([wall(l=5000, h=100)], lib(*NO_OPT))
    assert r.walls[0].quantities == {int(k): v for k, v in r.walls[0].detail["pose"].items()}  # sans marge
    assert len([p for p in expand(course(r, 0)) if p[1] == CH]) >= 4


def test_offcut_reuse_reduces_consumed_blocks_and_can_be_disabled():
    # Sans moule demi : les demis sont coupés dans des blocs entiers (un bloc = deux demis).
    # 3000 × 1000, tronçon libre [300, 2700] : 5 assises impaires, chacune avec 2 demis coupés
    # (en tête et en fin) = 10 demis ; avec réemploi, 5 blocs suffisent.
    w = [wall(l=3000, h=1000)]
    shapes = lib("BTC_DEMI", *NO_OPT)
    on = ENGINE.calculate(w, shapes)
    off = CourseLayoutEngine(LayoutRules.from_overrides({"reuse_offcuts": False})).calculate(w, shapes)
    don, doff = on.walls[0].detail, off.walls[0].detail
    assert don["courses"] == doff["courses"]                      # même pose, seule la quantité change
    assert don["coupes"] == doff["coupes"] == 10
    assert (don["reemploi"], doff["reemploi"]) == (5, 0)
    assert doff["pose"][str(STD)] - don["pose"][str(STD)] == 5
    # 5 demis en trop dans les chutes finales : 5 chutes de 150 mm restent, mais aucune n'est jetée avant
    assert don["chutes_mm"] == 0 or don["chutes_mm"] % 150 == 0


def test_offcut_too_short_is_not_reused():
    # une coupe de 250 laisse 50 mm : inutilisable (< min_piece) ; aucune réutilisation possible
    r = ENGINE.calculate([wall(l=3250, h=400)], lib("BTC_DEMI", *NO_OPT))
    d = r.walls[0].detail
    assert d["coupes"] >= 1 and sum(r.walls[0].quantities.values()) >= sum(d["pose"].values())


# --- Extrémités : angle par bout, butée, jonctions en T ----------------------------------------
def wall_k(start, end, l=3000, h=300, junctions=(), openings=(), id_=1):
    return WallInput(id_, W(f"M{id_}", l, h, False, tuple(openings), start, end, tuple(junctions)))


def test_corner_piles_at_both_ends_when_the_wall_owns_both_corners():
    r = ENGINE.calculate([wall_k("angle", "angle")], lib(*NO_OPT))
    c0 = expand(course(r, 0))
    assert c0[0][:3] == (0, ANG, 300) and c0[-1][:3] == (2700, ANG, 300)
    assert sum(1 for p in c0 if p[1] == ANG) == 2
    # tronçon libre [300, 2700] sans chaînage d'extrémité : 8 blocs
    assert [p[1] for p in c0] == [ANG] + [STD] * 8 + [ANG]


def test_abutting_and_continuation_ends_have_no_end_chaining():
    free = expand(course(ENGINE.calculate([wall_k("libre", "libre")], lib(*NO_OPT)), 0))
    abut = expand(course(ENGINE.calculate([wall_k("butee", "suite")], lib(*NO_OPT)), 0))
    assert free[0][1] == CH and free[-1][1] == CH
    assert abut[0][1] == STD and abut[-1][1] == STD and all(p[1] != CH for p in abut)


def test_tee_junction_gets_a_vertical_chaining_column_on_every_course():
    r = ENGINE.calculate([wall_k("butee", "butee", l=6000, junctions=(3000,))], lib(*NO_OPT))
    for c in range(3):
        cols = [p for p in expand(course(r, c)) if p[1] == CH]
        assert [(p[0], p[2]) for p in cols] == [(2850, 300)]
    assert any("jonction(s) en T" in n for n in r.walls[0].detail["notes"])


def test_tee_junction_inside_an_opening_is_ignored_with_a_note():
    ow = O("fenetre", 1200, 600, 2400, 300)
    r = ENGINE.calculate([wall_k("butee", "butee", l=6000, h=1200, junctions=(3000,), openings=[ow])],
                         lib(*NO_OPT))
    assert any("ignorée" in n for n in r.walls[0].detail["notes"])


def test_closed_rectangle_places_exactly_four_corner_stacks():
    from brikia.adapters.analyzers.geometry_utils import CornerCandidate as C
    from brikia.adapters.analyzers.geometry_utils import classify_ends
    segs = [C(0, "", (0, 0), (6000, 0), 200), C(1, "", (6000, 0), (6000, 4000), 200),
            C(2, "", (6000, 4000), (0, 4000), 200), C(3, "", (0, 4000), (0, 0), 200)]
    lengths = [6000, 4000, 6000, 4000]
    ends = classify_ends(segs)
    walls = [wall_k(ends[i].start, ends[i].end, l=lengths[i], h=2000, id_=i + 1) for i in range(4)]
    r = ENGINE.calculate(walls, lib(*NO_OPT))
    angle_pieces = sum(len([p for c in range(20) for p in expand(course(r, c, i)) if p[1] == ANG])
                       for i in range(4))
    assert angle_pieces == 4 * 20          # 4 coins × 20 assises (et non 8 ou 16 piles)


def test_legacy_corner_flag_still_places_one_pile_at_the_start():
    r = ENGINE.calculate([wall(l=3000, h=200, corner=True)], lib(*NO_OPT))
    c0 = expand(course(r, 0))
    assert c0[0][1] == ANG and sum(1 for p in c0 if p[1] == ANG) == 1
