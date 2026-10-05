"""source et notes de l'analyse

Revision ID: 0004
Revises: 0003
"""
import json

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

LEGACY_NOTE = ("Analyse SIMULÉE (phase 1) : le contenu du plan n'a pas été lu. "
               "Relancer une analyse n'est pas possible : réimportez le plan pour une lecture réelle.")


def upgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(sa.Column("analysis_source", sa.String(length=20), nullable=True))
        batch_op.add_column(sa.Column("analysis_notes", sa.JSON(), nullable=True))

    # Les projets déjà analysés l'ont été par le simulateur de la phase 1.
    op.get_bind().execute(
        sa.text("UPDATE projects SET analysis_source = 'simulated', analysis_notes = :notes "
                "WHERE status != 'a_analyser'"),
        {"notes": json.dumps([LEGACY_NOTE])},
    )


def downgrade() -> None:
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.drop_column("analysis_notes")
        batch_op.drop_column("analysis_source")
