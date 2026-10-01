import io
import xml.dom.minidom
from decimal import Decimal

import pytest

from brikia.domain.errors import ValidationFailed
from brikia.domain.moldplan import mold_sheet, to_svg
from brikia.domain.pricing import PricingParams, QuoteInput, compute_quote

P = PricingParams(Decimal("655.957"), Decimal("20"), Decimal("18"), Decimal("0"))


def _q(code, qty, cost, shape_id=1):
    return QuoteInput(shape_id, code, code, "standard", qty, None if cost is None else Decimal(cost))


# --- Calcul (valeurs vérifiées à la main) ----------------------------------------------------
def test_quote_by_hand_both_currencies():
    q = compute_quote([_q("STD", 100, "0.30"), _q("ANG", 7, "0.38", 2)], P)
    std, ang = q["lignes"]
    # 0,30 × 1,2 = 0,36 € ; × 655,957 = 236,14 -> 236 FCFA
    assert (std["prix_unitaire_eur"], std["total_eur"]) == ("0.36", "36.00")
    assert (std["prix_unitaire_fcfa"], std["total_fcfa"]) == ("236", "23600")
    # 0,38 × 1,2 = 0,456 -> 0,46 € (arrondi commercial) ; 299,12 -> 299 FCFA
    assert (ang["prix_unitaire_eur"], ang["total_eur"]) == ("0.46", "3.22")
    assert (ang["prix_unitaire_fcfa"], ang["total_fcfa"]) == ("299", "2093")
    assert q["eur"] == {"materiel_ht": "39.22", "frais_fixes": "0.00", "total_ht": "39.22",
                        "tva": "7.06", "total_ttc": "46.28"}
    assert q["fcfa"] == {"materiel_ht": "25693", "frais_fixes": "0", "total_ht": "25693",
                         "tva": "4625", "total_ttc": "30318"}
    assert q["cout_revient_eur"] == "32.66" and q["estimatif"] is True


def test_fixed_fees_converted_and_included_before_vat():
    q = compute_quote([_q("STD", 100, "0.30")], PricingParams(
        Decimal("655.957"), Decimal("20"), Decimal("18"), Decimal("10")))
    assert q["eur"]["frais_fixes"] == "10.00" and q["fcfa"]["frais_fixes"] == "6560"
    assert q["eur"]["total_ht"] == "46.00" and q["eur"]["tva"] == "8.28"
    assert q["fcfa"]["total_ht"] == "30160" and q["fcfa"]["total_ttc"] == "35589"  # 30160 + 5429 (5428,8)


def test_missing_cost_is_flagged_not_priced():
    q = compute_quote([_q("STD", 10, "0.30"), _q("NOCOST", 5, None, 2)], P)
    assert q["lignes"][1]["chiffre"] is False
    assert "NOCOST" in q["avertissements"][0]
    assert q["eur"]["materiel_ht"] == "3.60"


@pytest.mark.parametrize("kw", [dict(taux_fcfa_par_eur=Decimal(0)), dict(marge_pct=Decimal(-1)),
                                dict(tva_pct=Decimal(101)), dict(frais_fixes_eur=Decimal(-5))])
def test_invalid_parameters_refused(kw):
    base = dict(taux_fcfa_par_eur=Decimal("655.957"), marge_pct=Decimal(20), tva_pct=Decimal(18),
                frais_fixes_eur=Decimal(0))
    with pytest.raises(ValidationFailed):
        compute_quote([], PricingParams(**{**base, **kw}))


# --- Plans de moules -------------------------------------------------------------------------
CATS = ["standard", "creux", "demi", "trois_quarts", "angle", "angle_135", "te", "chainage",
        "chainage_h", "linteau", "appui", "pignon", "acrotere", "special"]


@pytest.mark.parametrize("cat", CATS)
def test_every_category_produces_valid_svg_with_dimensions(cat):
    svg = to_svg(mold_sheet("X", "Moule <test> & co", "BTC", cat, None, 300, 150, 100, 8550))
    xml.dom.minidom.parseString(svg)  # XML bien formé (le « < » et le « & » sont échappés)
    assert "300" in svg and "100" in svg and "INDICATIVE" in svg and "VUE 3D" in svg
    assert svg.count("<polygon") >= 4


# --- API : tarifs, devis, moules, rapport ----------------------------------------------------
F3 = b"f3-2"


def _project(c, csrf, validate=False):
    pid = c.post("/api/projects", headers=csrf, data={"nom": "Villa Test"},
                 files={"fichier": ("p.pdf", io.BytesIO(F3))}).json()["id"]
    c.post(f"/api/projects/{pid}/analyse", headers=csrf)
    assert c.post(f"/api/projects/{pid}/calepinage", headers=csrf).status_code == 200
    if validate:
        assert c.post(f"/api/projects/{pid}/validation", headers=csrf).status_code == 200
    return pid


def test_default_tariffs_and_chef_only(chef, oper):
    c, csrf = chef
    t = c.get("/api/tarifs").json()
    assert (t["taux_fcfa_par_eur"], t["marge_pct"], t["tva_pct"], t["frais_fixes_eur"]) == (
        "655.957", "20", "18", "0")
    o, ocsrf = oper
    assert o.get("/api/tarifs").status_code == 403
    assert o.put("/api/tarifs", headers=ocsrf, json=t).status_code == 403


def test_update_tariffs_validated_and_audited(chef, session):
    from brikia.services import audit
    c, csrf = chef
    bad = c.put("/api/tarifs", headers=csrf, json={"taux_fcfa_par_eur": "0", "marge_pct": "20",
                                                   "tva_pct": "18", "frais_fixes_eur": "0"})
    assert bad.status_code == 422
    ok = c.put("/api/tarifs", headers=csrf, json={"taux_fcfa_par_eur": "650", "marge_pct": "25.5",
                                                  "tva_pct": "19.25", "frais_fixes_eur": "100"})
    assert ok.status_code == 200 and ok.json()["marge_pct"] == "25.5"
    assert c.get("/api/tarifs").json()["taux_fcfa_par_eur"] == "650"
    entry = audit.list_entries(session, target_type="pricing")[0]
    assert entry.action == "pricing.update" and entry.details["marge_pct"] == {"avant": "20", "apres": "25.5"}


def test_live_quote_then_frozen_at_validation(chef):
    c, csrf = chef
    pid = _project(c, csrf)
    live = c.get(f"/api/projects/{pid}/devis").json()
    assert live["fige"] is False and live["avertissements"] == []
    assert all(ln["chiffre"] for ln in live["lignes"])
    total_before = live["fcfa"]["total_ttc"]

    assert c.post(f"/api/projects/{pid}/validation", headers=csrf).status_code == 200
    frozen = c.get(f"/api/projects/{pid}/devis").json()
    assert frozen["fige"] is True and frozen["fcfa"]["total_ttc"] == total_before

    # Les tarifs changent : le projet validé garde son devis, un autre projet utilise le nouveau tarif.
    c.put("/api/tarifs", headers=csrf, json={"taux_fcfa_par_eur": "655.957", "marge_pct": "50",
                                             "tva_pct": "18", "frais_fixes_eur": "0"})
    assert c.get(f"/api/projects/{pid}/devis").json()["fcfa"]["total_ttc"] == total_before
    pid2 = _project(c, csrf)
    assert c.get(f"/api/projects/{pid2}/devis").json()["fcfa"]["total_ttc"] != total_before


def test_devis_reserved_to_chef_and_needs_layout(chef, oper):
    c, csrf = chef
    pid = _project(c, csrf)
    o, _ = oper
    assert o.get(f"/api/projects/{pid}/devis").status_code == 403
    empty = c.post("/api/projects", headers=csrf, data={"nom": "Vide"},
                   files={"fichier": ("p.pdf", io.BytesIO(b"x"))}).json()["id"]
    assert c.get(f"/api/projects/{empty}/devis").status_code == 404


def test_mold_cost_visible_to_chef_only_and_audited(chef, oper, session):
    from brikia.services import audit
    c, csrf = chef
    assert c.get("/api/moulds/1").json()["cout_unitaire_eur"] == "0.30"
    o, _ = oper
    assert o.get("/api/moulds/1").json()["cout_unitaire_eur"] is None
    assert all(m["cout_unitaire_eur"] is None for m in o.get("/api/moulds").json())
    r = c.put("/api/moulds/1", headers=csrf, json={"cout_unitaire_eur": "0.35", "poids_g": 9000})
    assert r.status_code == 200 and r.json()["cout_unitaire_eur"] == "0.35"
    e = audit.list_entries(session, target_type="brick_shape")[0]
    assert e.details["modifications"]["cout_unitaire_eur"] == {"avant": "0.30", "apres": "0.35"}
    assert c.put("/api/moulds/1", headers=csrf, json={"cout_unitaire_eur": "-1"}).status_code == 422


def test_all_library_molds_have_a_valid_plan(chef):
    c, _ = chef
    shapes = c.get("/api/moulds").json()
    assert len(shapes) == 23
    for s in shapes:
        r = c.get(f"/api/moulds/{s['id']}/plan.svg")
        assert r.status_code == 200 and r.headers["content-type"].startswith("image/svg+xml"), s["code"]
        xml.dom.minidom.parseString(r.text)
        assert s["code"] in r.text


def test_plan_requires_dimensions_and_login(client, chef):
    c, csrf = chef
    sid = c.post("/api/moulds", headers=csrf, json={"code": "SANSDIM", "nom": "x", "produit": "p",
                                                     "categorie": "special"}).json()["id"]
    r = c.get(f"/api/moulds/{sid}/plan.svg")
    assert r.status_code == 422 and "dimensions" in r.text
    assert client.get("/api/moulds/1/plan.svg").status_code == 401


def _pdf_text(data: bytes) -> str:
    from pypdf import PdfReader
    reader = PdfReader(io.BytesIO(data))
    return "\n".join(p.extract_text() for p in reader.pages), len(reader.pages)


def test_report_pdf_for_chef_contains_prices_and_mold_sheets(chef):
    c, csrf = chef
    pid = _project(c, csrf, validate=True)
    r = c.get(f"/api/projects/{pid}/rapport.pdf")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert r.content.startswith(b"%PDF") and "rapport-" in r.headers["content-disposition"]
    text, pages = _pdf_text(r.content)
    for expected in ("Rapport général du projet", "Villa Test", "ANALYSE SIMULÉE", "Nomenclature",
                     "BTC_STD", "Chiffrage estimatif", "FCFA", "Total TTC", "FIGÉ", "Signatures",
                     "INDICATIVE"):
        assert expected in text, expected
    assert pages >= 6  # texte + une fiche par moule utilisé (BTC_STD, ANGLE, CHAINAGE, LINTEAU, DEMI, APPUI)


def test_report_pdf_for_operator_has_no_prices(chef, oper):
    c, csrf = chef
    pid = _project(c, csrf, validate=True)
    o, _ = oper
    r = o.get(f"/api/projects/{pid}/rapport.pdf")
    assert r.status_code == 200
    text, _ = _pdf_text(r.content)
    assert "Nomenclature" in text and "Chiffrage" not in text and "FCFA" not in text


def test_report_without_layout_still_generated(chef):
    c, csrf = chef
    pid = c.post("/api/projects", headers=csrf, data={"nom": "Vide"},
                 files={"fichier": ("p.pdf", io.BytesIO(b"x"))}).json()["id"]
    r = c.get(f"/api/projects/{pid}/rapport.pdf")
    text, _ = _pdf_text(r.content)
    assert r.status_code == 200 and "Aucun calepinage" in text


def test_report_unknown_project_and_anonymous(client, chef):
    c, _ = chef
    assert c.get("/api/projects/999/rapport.pdf").status_code == 404
    assert client.get("/api/projects/1/rapport.pdf").status_code == 401
