"""nature des extremites des murs, jonctions en T, epaisseur, marquage des corrections manuelles

Revision ID: 0007
Revises: 0006
"""
import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    have = _cols("walls")
    with op.batch_alter_table("walls") as batch_op:
        if "start_kind" not in have:
            batch_op.add_column(sa.Column("start_kind", sa.String(length=10), nullable=True))
        if "end_kind" not in have:
            batch_op.add_column(sa.Column("end_kind", sa.String(length=10), nullable=True))
        if "junctions_mm" not in have:
            batch_op.add_column(sa.Column("junctions_mm", sa.JSON(), nullable=True))
        if "thickness_mm" not in have:
            batch_op.add_column(sa.Column("thickness_mm", sa.Integer(), nullable=True))
        if "manuel" not in have:
            batch_op.add_column(sa.Column("manuel", sa.Boolean(), nullable=False, server_default=sa.false()))
    if "manuel" not in _cols("openings"):
        with op.batch_alter_table("openings") as batch_op:
            batch_op.add_column(sa.Column("manuel", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("openings") as batch_op:
        batch_op.drop_column("manuel")
    with op.batch_alter_table("walls") as batch_op:
        for col in ("manuel", "thickness_mm", "junctions_mm", "end_kind", "start_kind"):
            batch_op.drop_column(col)
