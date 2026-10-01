"""Migration 0005 : conserve les moules/valeurs existants, ajoute la bibliothèque étendue."""

import sqlite3

from alembic import command

from brikia.migrate import alembic_config, upgrade


def test_upgrade_from_0004_keeps_custom_values_and_adds_library(settings):
    cfg = alembic_config(settings)
    settings.ensure_dirs()
    command.upgrade(cfg, "0004")
    con = sqlite3.connect(settings.db_path)
    # Le chef a déjà saisi des dimensions pour BTC_STD et supprimé PARP_ANGLE.
    con.execute("UPDATE brick_shapes SET longueur_mm = 250, largeur_mm = 125, hauteur_mm = 95 "
                "WHERE code = 'BTC_STD'")
    con.execute("DELETE FROM brick_shapes WHERE code = 'PARP_ANGLE'")
    con.commit()
    con.close()

    upgrade(settings)

    con = sqlite3.connect(settings.db_path)
    rows = {r[0]: r for r in con.execute(
        "SELECT code, longueur_mm, largeur_mm, hauteur_mm, poids_g, cout_unitaire_eur FROM brick_shapes")}
    assert rows["BTC_STD"][1:4] == (250, 125, 95)  # valeur saisie conservée
    assert rows["BTC_STD"][4] == 8550 and rows["BTC_STD"][5] == "0.30"  # poids/coût ajoutés
    assert "BTC_TE" in rows and "PARP_ACROTERE" in rows
    assert rows["PARP_ANGLE"][1] == 400  # ré-ajouté par la bibliothèque étendue (plus de doublon)
    assert len(rows) == 23
    assert con.execute("SELECT taux_fcfa_par_eur, marge_pct, tva_pct FROM pricing_settings").fetchone() == (
        "655.957", "20", "18")
    con.close()


def test_downgrade_then_upgrade_roundtrip(settings):
    upgrade(settings)
    cfg = alembic_config(settings)
    command.downgrade(cfg, "0004")
    con = sqlite3.connect(settings.db_path)
    assert con.execute("SELECT count(*) FROM brick_shapes").fetchone()[0] == 6
    assert "pricing_settings" not in {r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    command.upgrade(cfg, "head")
