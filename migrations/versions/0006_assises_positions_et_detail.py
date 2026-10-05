"""position des ouvertures et detail du calepinage assise par assise

Revision ID: 0006
Revises: 0005
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def _cols(table: str) -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    # Idempotente (voir 0005 : SQLite n'a pas de DDL transactionnel).
    have = _cols("openings")
    with op.batch_alter_table("openings") as batch_op:
        if "x_mm" not in have:
            batch_op.add_column(sa.Column("x_mm", sa.Integer(), nullable=True))
        if "sill_mm" not in have:
            batch_op.add_column(sa.Column("sill_mm", sa.Integer(), nullable=True))
    if "detail" not in _cols("layout_runs"):
        with op.batch_alter_table("layout_runs") as batch_op:
            batch_op.add_column(sa.Column("detail", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("layout_runs") as batch_op:
        batch_op.drop_column("detail")
    with op.batch_alter_table("openings") as batch_op:
        batch_op.drop_column("sill_mm")
        batch_op.drop_column("x_mm")
