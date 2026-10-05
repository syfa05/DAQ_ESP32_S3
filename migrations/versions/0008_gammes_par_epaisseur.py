"""gammes de moules par epaisseur de mur (BTC 100/200/300, parpaing 100/150/300) et choix de gamme par mur

Revision ID: 0008
Revises: 0007

Une « gamme » = un produit + une largeur de moule (= épaisseur de mur). Les moules ajoutés sont dérivés
des moules de base par proportion (largeur, longueur) : poids et coût de revient sont des ESTIMATIONS
modifiables dans l'application, comme le reste de la bibliothèque.
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

BTC, PARP = "BTC autobloquante", "Parpaing autobloquant"

# Moules de base (gammes existantes : BTC 150 mm, parpaing 200 mm) servant de modèle :
# suffixe, nom, rôle, catégorie, forme, L, h, poids (g), cadence, coût EUR
BASES = {
    BTC: (150, 300, [
        ("STD", "BTC standard (plein)", "Corps de mur, emboîtement mâle-femelle", "standard", "plein", 300, 100, 8550, 240, "0.30"),
        ("DEMI", "BTC demi-bloc", "Appareillage à joints décalés, fins de rang", "demi", "demi", 150, 100, 4275, 240, "0.17"),
        ("TROIS_QUARTS", "BTC trois-quarts (¾)", "Ajustement de rang", "trois_quarts", "trois-quarts", 225, 100, 6410, 240, "0.23"),
        ("ANGLE", "BTC d'angle 90°", "Retours d'angle et abouts", "angle", "angle 90", 300, 100, 8800, 120, "0.38"),
        ("CHAINAGE", "BTC de chaînage vertical", "Ferraillage vertical / micro-béton", "chainage", "chaînage vertical", 300, 100, 7200, 120, "0.34"),
        ("CHAINAGE_H", "BTC de chaînage horizontal (U)", "Ceinture, chaînage haut et bas", "chainage_h", "chaînage horizontal", 300, 100, 5800, 120, "0.36"),
        ("LINTEAU", "BTC de linteau", "Ouvertures", "linteau", "linteau", 450, 100, 12500, 60, "0.95"),
        ("APPUI", "BTC appui de fenêtre", "Appui avec pente d'écoulement", "appui", "appui", 450, 80, 10200, 90, "0.60"),
    ]),
    PARP: (200, 400, [
        ("STD", "Parpaing standard (creux)", "Fondations lourdes / murs haute densité", "standard", "creux", 400, 200, 17500, 300, "0.80"),
        ("DEMI", "Parpaing demi-bloc", "Appareillage à joints décalés", "demi", "demi", 200, 200, 9000, 300, "0.45"),
        ("TROIS_QUARTS", "Parpaing trois-quarts (¾)", "Ajustement de rang", "trois_quarts", "trois-quarts", 300, 200, 13000, 300, "0.65"),
        ("ANGLE", "Parpaing d'angle 90°", "Retours d'angle", "angle", "angle 90", 400, 200, 18500, 150, "0.95"),
        ("CHAINAGE", "Parpaing de chaînage vertical", "Poteau de chaînage coulé", "chainage", "chaînage vertical", 400, 200, 14500, 150, "0.90"),
        ("CHAINAGE_H", "Parpaing de chaînage horizontal (U)", "Ceinture coulée", "chainage_h", "chaînage horizontal", 400, 200, 13500, 150, "0.95"),
        ("LINTEAU", "Parpaing de linteau (U)", "Linteau coulé sur ouvertures", "linteau", "linteau", 400, 200, 15000, 100, "1.20"),
        ("APPUI", "Parpaing appui de fenêtre", "Appui avec pente d'écoulement", "appui", "appui", 500, 100, 19500, 100, "1.60"),
    ]),
}
# Nouvelles gammes : (produit, largeur mm, facteur de longueur appliqué aux longueurs de base)
NEW_FAMILIES = [(BTC, 100, 1.0), (BTC, 200, 4 / 3), (BTC, 300, 2.0),
                (PARP, 100, 1.0), (PARP, 150, 1.0), (PARP, 300, 1.0)]


def _round5(v: float) -> int:
    return int(round(v / 5.0)) * 5


def derived_library():
    """Moules des nouvelles gammes, dérivés des moules de base par proportion."""
    for produit, width, lscale in NEW_FAMILIES:
        base_width, _, rows = BASES[produit]
        prefix = "BTC" if produit == BTC else "PARP"
        for suffix, nom, role, cat, forme, length, height, poids, cad, cout in rows:
            k = (width / base_width) * lscale          # proportion de volume
            yield (f"{prefix}_{suffix}_{width}", f"{nom} — {width} mm", produit, role, cat, forme,
                   _round5(length * lscale), width, height, int(round(poids * k, -1)), cad,
                   f"{float(cout) * k:.2f}")


def upgrade() -> None:
    bind = op.get_bind()
    if "gamme" not in {c["name"] for c in sa.inspect(bind).get_columns("walls")}:
        with op.batch_alter_table("walls") as batch_op:
            batch_op.add_column(sa.Column("gamme", sa.String(length=80), nullable=True))
    for (code, nom, produit, role, cat, forme, L, l, h, poids, cad, cout) in derived_library():
        if bind.execute(sa.text("SELECT 1 FROM brick_shapes WHERE code = :c"), {"c": code}).first():
            continue
        bind.execute(sa.text(
            "INSERT INTO brick_shapes (code, nom, produit, role, categorie, forme, longueur_mm, "
            "largeur_mm, hauteur_mm, poids_g, cadence_par_heure, cout_unitaire_eur, disponible) "
            "VALUES (:c, :n, :pr, :r, :cat, :f, :L, :l, :h, :p, :cad, :cout, 1)"),
            {"c": code, "n": nom, "pr": produit, "r": role, "cat": cat, "f": forme, "L": L, "l": l,
             "h": h, "p": poids, "cad": cad, "cout": cout})


def downgrade() -> None:
    bind = op.get_bind()
    codes = [row[0] for row in derived_library()]
    marks = ",".join(f"'{c}'" for c in codes)
    bind.execute(sa.text(
        f"DELETE FROM brick_shapes WHERE code IN ({marks}) "
        "AND id NOT IN (SELECT brick_shape_id FROM wall_assignments) "
        "AND id NOT IN (SELECT brick_shape_id FROM production_order_lines)"))
    with op.batch_alter_table("walls") as batch_op:
        batch_op.drop_column("gamme")
