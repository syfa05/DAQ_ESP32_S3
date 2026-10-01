"""moules etendus (dimensions, poids, cadence, cout) et parametres de chiffrage

Revision ID: 0005
Revises: 0004

Les valeurs de la bibliothèque sont des ESTIMATIONS de départ, choisies pour le projet ;
elles se modifient à tout moment depuis l'application (page Moules / Tarifs).
Poids = volume × masse volumique approximative (BTC ≈ 1 900 kg/m³, parpaing creux ≈ 1 100 kg/m³
apparent), arrondi ; coûts = coût de revient estimé par bloc en EUR.
"""
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

NAMING = {"ck": "ck_%(table_name)s_%(constraint_name)s"}

OLD_CATEGORIES = ("standard", "angle", "chainage", "linteau")
NEW_CATEGORIES = OLD_CATEGORIES + (
    "demi", "appui", "creux", "trois_quarts", "angle_135", "te", "chainage_h",
    "pignon", "acrotere", "special")

BTC, PARP = "BTC autobloquante", "Parpaing autobloquant"

# code, nom, produit, rôle, catégorie, forme, L, l, h (mm), poids (g), cadence/h, coût EUR
LIBRARY = [
    ("BTC_STD", "BTC standard (plein)", BTC, "Corps de mur, emboîtement mâle-femelle", "standard", "plein", 300, 150, 100, 8550, 240, "0.30"),
    ("BTC_CREUX", "BTC creux (allégé)", BTC, "Murs porteurs légers, passage de gaines", "creux", "creux", 300, 150, 100, 7270, 240, "0.27"),
    ("BTC_DEMI", "BTC demi-bloc", BTC, "Appareillage à joints décalés, fins de rang", "demi", "demi", 150, 150, 100, 4275, 240, "0.17"),
    ("BTC_TROIS_QUARTS", "BTC trois-quarts (¾)", BTC, "Ajustement de rang", "trois_quarts", "trois-quarts", 225, 150, 100, 6410, 240, "0.23"),
    ("BTC_ANGLE", "BTC d'angle 90°", BTC, "Retours d'angle et abouts", "angle", "angle 90", 300, 150, 100, 8800, 120, "0.38"),
    ("BTC_ANGLE_135", "BTC d'angle 135°", BTC, "Angles ouverts (pans coupés)", "angle_135", "angle 135", 300, 150, 100, 8700, 120, "0.42"),
    ("BTC_TE", "BTC en T", BTC, "Jonction mur porteur / refend", "te", "T", 300, 150, 100, 12800, 90, "0.50"),
    ("BTC_CHAINAGE", "BTC de chaînage vertical", BTC, "Ferraillage vertical / micro-béton", "chainage", "chaînage vertical", 300, 150, 100, 7200, 120, "0.34"),
    ("BTC_CHAINAGE_H", "BTC de chaînage horizontal (U)", BTC, "Ceinture, chaînage haut et bas", "chainage_h", "chaînage horizontal", 300, 150, 100, 5800, 120, "0.36"),
    ("BTC_LINTEAU", "BTC de linteau", BTC, "Ouvertures", "linteau", "linteau", 450, 150, 100, 12500, 60, "0.95"),
    ("BTC_APPUI", "BTC appui de fenêtre", BTC, "Appui avec pente d'écoulement", "appui", "appui", 450, 150, 80, 10200, 90, "0.60"),
    ("BTC_PIGNON", "BTC de pignon (rampant)", BTC, "Rampants de pignon, pente 22°", "pignon", "pignon", 300, 150, 100, 6800, 90, "0.40"),
    ("BTC_ACROTERE", "BTC d'acrotère", BTC, "Couronnement des murs, débord 25 mm", "acrotere", "acrotère", 300, 200, 100, 11400, 90, "0.65"),
    ("PARP_STD", "Parpaing standard (creux)", PARP, "Fondations lourdes / murs haute densité", "standard", "creux", 400, 200, 200, 17500, 300, "0.80"),
    ("PARP_DEMI", "Parpaing demi-bloc", PARP, "Appareillage à joints décalés", "demi", "demi", 200, 200, 200, 9000, 300, "0.45"),
    ("PARP_TROIS_QUARTS", "Parpaing trois-quarts (¾)", PARP, "Ajustement de rang", "trois_quarts", "trois-quarts", 300, 200, 200, 13000, 300, "0.65"),
    ("PARP_ANGLE", "Parpaing d'angle 90°", PARP, "Retours d'angle", "angle", "angle 90", 400, 200, 200, 18500, 150, "0.95"),
    ("PARP_ANGLE_135", "Parpaing d'angle 135°", PARP, "Angles ouverts", "angle_135", "angle 135", 400, 200, 200, 18200, 150, "1.05"),
    ("PARP_CHAINAGE", "Parpaing de chaînage vertical", PARP, "Poteau de chaînage coulé", "chainage", "chaînage vertical", 400, 200, 200, 14500, 150, "0.90"),
    ("PARP_CHAINAGE_H", "Parpaing de chaînage horizontal (U)", PARP, "Ceinture coulée", "chainage_h", "chaînage horizontal", 400, 200, 200, 13500, 150, "0.95"),
    ("PARP_LINTEAU", "Parpaing de linteau (U)", PARP, "Linteau coulé sur ouvertures", "linteau", "linteau", 400, 200, 200, 15000, 100, "1.20"),
    ("PARP_APPUI", "Parpaing appui de fenêtre", PARP, "Appui avec pente d'écoulement", "appui", "appui", 500, 200, 100, 19500, 100, "1.60"),
    ("PARP_ACROTERE", "Parpaing d'acrotère", PARP, "Couronnement des murs", "acrotere", "acrotère", 400, 250, 100, 14000, 120, "1.30"),
]


def _check(values: tuple[str, ...]) -> str:
    return "categorie IN (" + ", ".join(f"'{v}'" for v in values) + ")"


def upgrade() -> None:
    with op.batch_alter_table("brick_shapes", naming_convention=NAMING) as batch_op:
        batch_op.add_column(sa.Column("poids_g", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cadence_par_heure", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("cout_unitaire_eur", sa.String(length=40), nullable=True))
        batch_op.drop_constraint("categorie", type_="check")
        batch_op.create_check_constraint("categorie", _check(NEW_CATEGORIES))

    with op.batch_alter_table("projects") as batch_op:
        batch_op.add_column(sa.Column("devis", sa.JSON(), nullable=True))

    op.create_table(
        "pricing_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("taux_fcfa_par_eur", sa.String(length=40), nullable=False),
        sa.Column("marge_pct", sa.String(length=40), nullable=False),
        sa.Column("tva_pct", sa.String(length=40), nullable=False),
        sa.Column("frais_fixes_eur", sa.String(length=40), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.CheckConstraint("id = 1", name=op.f("ck_pricing_settings_singleton")),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"],
                                name=op.f("fk_pricing_settings_updated_by_id_users")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pricing_settings")),
    )
    bind = op.get_bind()
    bind.execute(sa.text(
        "INSERT INTO pricing_settings (id, taux_fcfa_par_eur, marge_pct, tva_pct, frais_fixes_eur, "
        "updated_at) VALUES (1, '655.957', '20', '18', '0', :now)"), {"now": datetime.now(UTC)})

    # Bibliothèque : complète les moules existants (sans écraser une valeur déjà saisie)
    # et ajoute ceux qui n'existent pas encore.
    for (code, nom, produit, role, cat, forme, L, l, h, poids, cad, cout) in LIBRARY:
        row = bind.execute(sa.text("SELECT id FROM brick_shapes WHERE code = :c"), {"c": code}).first()
        if row:
            bind.execute(sa.text(
                "UPDATE brick_shapes SET forme = COALESCE(forme, :f), "
                "longueur_mm = COALESCE(longueur_mm, :L), largeur_mm = COALESCE(largeur_mm, :l), "
                "hauteur_mm = COALESCE(hauteur_mm, :h), poids_g = :p, cadence_par_heure = :cad, "
                "cout_unitaire_eur = :cout WHERE code = :c"),
                {"c": code, "f": forme, "L": L, "l": l, "h": h, "p": poids, "cad": cad, "cout": cout})
        else:
            bind.execute(sa.text(
                "INSERT INTO brick_shapes (code, nom, produit, role, categorie, forme, longueur_mm, "
                "largeur_mm, hauteur_mm, poids_g, cadence_par_heure, cout_unitaire_eur, disponible) "
                "VALUES (:c, :n, :pr, :r, :cat, :f, :L, :l, :h, :p, :cad, :cout, 1)"),
                {"c": code, "n": nom, "pr": produit, "r": role, "cat": cat, "f": forme, "L": L,
                 "l": l, "h": h, "p": poids, "cad": cad, "cout": cout})


def downgrade() -> None:
    bind = op.get_bind()
    # Retire les moules ajoutés par cette migration s'ils ne sont pas utilisés ; ceux qui le sont
    # restent, ramenés à la catégorie « standard » (seules les 4 catégories d'origine existent avant).
    originals = ("BTC_STD", "BTC_ANGLE", "BTC_CHAINAGE", "BTC_LINTEAU", "PARP_STD", "PARP_ANGLE")
    marks = ",".join(f"'{c}'" for c in originals)
    bind.execute(sa.text(
        f"DELETE FROM brick_shapes WHERE code NOT IN ({marks}) "
        "AND id NOT IN (SELECT brick_shape_id FROM wall_assignments) "
        "AND id NOT IN (SELECT brick_shape_id FROM production_order_lines)"))
    bind.execute(sa.text(
        "UPDATE brick_shapes SET categorie = 'standard' "
        "WHERE categorie NOT IN ('standard','angle','chainage','linteau')"))
    op.drop_table("pricing_settings")
    with op.batch_alter_table("projects") as batch_op:
        batch_op.drop_column("devis")
    with op.batch_alter_table("brick_shapes", naming_convention=NAMING) as batch_op:
        batch_op.drop_constraint("categorie", type_="check")
        batch_op.create_check_constraint("categorie", _check(OLD_CATEGORIES))
        batch_op.drop_column("cout_unitaire_eur")
        batch_op.drop_column("cadence_par_heure")
        batch_op.drop_column("poids_g")
