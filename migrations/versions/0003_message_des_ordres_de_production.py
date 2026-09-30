"""message des ordres de production

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-30 09:42:11.714371
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:

    with op.batch_alter_table('production_orders', schema=None) as batch_op:
        batch_op.add_column(sa.Column('message', sa.String(length=255), nullable=True))




def downgrade() -> None:

    with op.batch_alter_table('production_orders', schema=None) as batch_op:
        batch_op.drop_column('message')


