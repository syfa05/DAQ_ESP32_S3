"""categorie des moules et bibliotheque initiale

Revision ID: 0002
Revises: 0001
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

NAMING = {"ck": "ck_%(table_name)s_%(constraint_name)s"}

# Bibliothèque initiale (cahier des charges §16). Insérée une seule fois :
# un moule supprimé ensuite par le chef de projet ne réapparaît pas.
INITIAL_SHAPES = [
    ("BTC_STD", "BTC standard", "BTC autobloquante",
     "Corps de mur, emboîtement mâle-femelle", "standard"),
    ("BTC_ANGLE", "BTC d'angle", "BTC autobloquante",
     "Retours d'angle et abouts", "angle"),
    ("BTC_CHAINAGE", "BTC de chaînage", "BTC autobloquante",
     "Ferraillage vertical / micro-béton", "chainage"),
    ("BTC_LINTEAU", "BTC de linteau", "BTC autobloquante", "Ouvertures", "linteau"),
    ("PARP_STD", "Parpaing standard", "Parpaing autobloquant",
     "Fondations lourdes / murs haute densité", "standard"),
    ("PARP_ANGLE", "Parpaing d'angle", "Parpaing autobloquant",
     "Retours d'angle", "angle"),
]


def upgrade() -> None:
    with op.batch_alter_table("brick_shapes", naming_convention=NAMING) as batch_op:
        batch_op.add_column(sa.Column("categorie", sa.String(length=20),
                                      server_default="standard", nullable=False))
        batch_op.create_check_constraint(
            "categorie", "categorie IN ('standard', 'angle', 'chainage', 'linteau')")

    shapes = sa.table(
        "brick_shapes", sa.column("code"), sa.column("nom"), sa.column("produit"),
        sa.column("role"), sa.column("categorie"), sa.column("disponible"),
    )
    op.bulk_insert(shapes, [
        {"code": c, "nom": n, "produit": p, "role": r, "categorie": cat, "disponible": True}
        for c, n, p, r, cat in INITIAL_SHAPES
    ])


def downgrade() -> None:
    # Retire la bibliothèque insérée par upgrade() (échoue volontairement si
    # un moule est déjà référencé par un calepinage : FK RESTRICT).
    codes = ", ".join(repr(row[0]) for row in INITIAL_SHAPES)
    op.execute(f"DELETE FROM brick_shapes WHERE code IN ({codes})")
    with op.batch_alter_table("brick_shapes", naming_convention=NAMING) as batch_op:
        batch_op.drop_constraint("categorie", type_="check")
        batch_op.drop_column("categorie")
