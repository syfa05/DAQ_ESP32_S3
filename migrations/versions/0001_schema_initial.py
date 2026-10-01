"""schema initial

Revision ID: 0001
Revises: 
Create Date: 2026-09-30 09:22:30.327594
"""
from alembic import op
import sqlalchemy as sa


revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    
    op.create_table('brick_shapes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('code', sa.String(length=40), nullable=False),
    sa.Column('nom', sa.String(length=120), nullable=False),
    sa.Column('produit', sa.String(length=120), nullable=False),
    sa.Column('role', sa.String(length=255), nullable=False),
    sa.Column('forme', sa.String(length=60), nullable=True),
    sa.Column('longueur_mm', sa.Integer(), nullable=True),
    sa.Column('largeur_mm', sa.Integer(), nullable=True),
    sa.Column('hauteur_mm', sa.Integer(), nullable=True),
    sa.Column('disponible', sa.Boolean(), nullable=False),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_brick_shapes')),
    sa.UniqueConstraint('code', name=op.f('uq_brick_shapes_code'))
    )
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nom', sa.String(length=120), nullable=False),
    sa.Column('login', sa.String(length=64), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('role', sa.String(length=20), nullable=False),
    sa.Column('actif', sa.Boolean(), nullable=False),
    sa.CheckConstraint("role IN ('chef_projet', 'operateur')", name=op.f('ck_users_role')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_users')),
    sa.UniqueConstraint('login', name=op.f('uq_users_login'))
    )
    op.create_table('action_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(length=60), nullable=False),
    sa.Column('target_type', sa.String(length=40), nullable=False),
    sa.Column('target_id', sa.Integer(), nullable=True),
    sa.Column('details', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_action_logs_user_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_action_logs'))
    )
    with op.batch_alter_table('action_logs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_action_logs_action'), ['action'], unique=False)
        batch_op.create_index(batch_op.f('ix_action_logs_created_at'), ['created_at'], unique=False)
        batch_op.create_index(batch_op.f('ix_action_logs_user_id'), ['user_id'], unique=False)

    op.create_table('projects',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nom', sa.String(length=200), nullable=False),
    sa.Column('ville', sa.String(length=120), nullable=False),
    sa.Column('architecte', sa.String(length=120), nullable=False),
    sa.Column('plan_path', sa.String(length=500), nullable=True),
    sa.Column('plan_original_name', sa.String(length=255), nullable=True),
    sa.Column('plan_size', sa.Integer(), nullable=True),
    sa.Column('plan_sha256', sa.String(length=64), nullable=True),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('validated_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('a_analyser', 'a_optimiser', 'a_valider', 'valide', 'en_production', 'termine')", name=op.f('ck_projects_status')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_projects_created_by_id_users')),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_projects'))
    )
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_projects_status'), ['status'], unique=False)

    op.create_table('user_sessions',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('csrf_token', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], name=op.f('fk_user_sessions_user_id_users'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_user_sessions')),
    sa.UniqueConstraint('token_hash', name=op.f('uq_user_sessions_token_hash'))
    )
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_user_sessions_user_id'), ['user_id'], unique=False)

    op.create_table('layout_runs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('engine', sa.String(length=80), nullable=False),
    sa.Column('parameters', sa.JSON(), nullable=False),
    sa.Column('warnings', sa.JSON(), nullable=False),
    sa.Column('estimated_duration_min', sa.Integer(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_layout_runs_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_layout_runs'))
    )
    with op.batch_alter_table('layout_runs', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_layout_runs_project_id'), ['project_id'], unique=False)

    op.create_table('production_orders',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('lot_id', sa.String(length=36), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=20), nullable=False),
    sa.Column('created_by_id', sa.Integer(), nullable=True),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("status IN ('en_cours', 'termine', 'erreur')", name=op.f('ck_production_orders_status')),
    sa.ForeignKeyConstraint(['created_by_id'], ['users.id'], name=op.f('fk_production_orders_created_by_id_users')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_production_orders_project_id_projects'), ondelete='RESTRICT'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_production_orders')),
    sa.UniqueConstraint('lot_id', name=op.f('uq_production_orders_lot_id'))
    )
    with op.batch_alter_table('production_orders', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_production_orders_project_id'), ['project_id'], unique=False)
        batch_op.create_index('uq_production_orders_active_project', ['project_id'], unique=True, sqlite_where=sa.text("status = 'en_cours'"), postgresql_where=sa.text("status = 'en_cours'"))

    op.create_table('walls',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('project_id', sa.Integer(), nullable=False),
    sa.Column('nom', sa.String(length=120), nullable=False),
    sa.Column('longueur_mm', sa.Integer(), nullable=False),
    sa.Column('hauteur_mm', sa.Integer(), nullable=False),
    sa.Column('is_corner', sa.Boolean(), nullable=False),
    sa.CheckConstraint('hauteur_mm > 0', name=op.f('ck_walls_hauteur_pos')),
    sa.CheckConstraint('longueur_mm > 0', name=op.f('ck_walls_longueur_pos')),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], name=op.f('fk_walls_project_id_projects'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_walls'))
    )
    with op.batch_alter_table('walls', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_walls_project_id'), ['project_id'], unique=False)

    op.create_table('openings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('wall_id', sa.Integer(), nullable=False),
    sa.Column('type', sa.String(length=30), nullable=False),
    sa.Column('largeur_mm', sa.Integer(), nullable=False),
    sa.Column('hauteur_mm', sa.Integer(), nullable=False),
    sa.CheckConstraint('hauteur_mm > 0', name=op.f('ck_openings_hauteur_pos')),
    sa.CheckConstraint('largeur_mm > 0', name=op.f('ck_openings_largeur_pos')),
    sa.ForeignKeyConstraint(['wall_id'], ['walls.id'], name=op.f('fk_openings_wall_id_walls'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_openings'))
    )
    with op.batch_alter_table('openings', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_openings_wall_id'), ['wall_id'], unique=False)

    op.create_table('production_order_lines',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('order_id', sa.Integer(), nullable=False),
    sa.Column('brick_shape_id', sa.Integer(), nullable=False),
    sa.Column('target', sa.Integer(), nullable=False),
    sa.Column('produced', sa.Integer(), nullable=False),
    sa.CheckConstraint('produced >= 0 AND produced <= target', name=op.f('ck_production_order_lines_produced_range')),
    sa.CheckConstraint('target >= 0', name=op.f('ck_production_order_lines_target_nonneg')),
    sa.ForeignKeyConstraint(['brick_shape_id'], ['brick_shapes.id'], name=op.f('fk_production_order_lines_brick_shape_id_brick_shapes'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['order_id'], ['production_orders.id'], name=op.f('fk_production_order_lines_order_id_production_orders'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_production_order_lines')),
    sa.UniqueConstraint('order_id', 'brick_shape_id', name=op.f('uq_production_order_lines_order_id'))
    )
    with op.batch_alter_table('production_order_lines', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_production_order_lines_order_id'), ['order_id'], unique=False)

    op.create_table('wall_assignments',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('layout_run_id', sa.Integer(), nullable=False),
    sa.Column('wall_id', sa.Integer(), nullable=False),
    sa.Column('brick_shape_id', sa.Integer(), nullable=False),
    sa.Column('quantity', sa.Integer(), nullable=False),
    sa.CheckConstraint('quantity >= 0', name=op.f('ck_wall_assignments_quantity_nonneg')),
    sa.ForeignKeyConstraint(['brick_shape_id'], ['brick_shapes.id'], name=op.f('fk_wall_assignments_brick_shape_id_brick_shapes'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['layout_run_id'], ['layout_runs.id'], name=op.f('fk_wall_assignments_layout_run_id_layout_runs'), ondelete='CASCADE'),
    sa.ForeignKeyConstraint(['wall_id'], ['walls.id'], name=op.f('fk_wall_assignments_wall_id_walls'), ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_wall_assignments')),
    sa.UniqueConstraint('layout_run_id', 'wall_id', 'brick_shape_id', name=op.f('uq_wall_assignments_layout_run_id'))
    )
    with op.batch_alter_table('wall_assignments', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_wall_assignments_brick_shape_id'), ['brick_shape_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wall_assignments_layout_run_id'), ['layout_run_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_wall_assignments_wall_id'), ['wall_id'], unique=False)

    


def downgrade() -> None:
    
    with op.batch_alter_table('wall_assignments', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_wall_assignments_wall_id'))
        batch_op.drop_index(batch_op.f('ix_wall_assignments_layout_run_id'))
        batch_op.drop_index(batch_op.f('ix_wall_assignments_brick_shape_id'))

    op.drop_table('wall_assignments')
    with op.batch_alter_table('production_order_lines', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_production_order_lines_order_id'))

    op.drop_table('production_order_lines')
    with op.batch_alter_table('openings', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_openings_wall_id'))

    op.drop_table('openings')
    with op.batch_alter_table('walls', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_walls_project_id'))

    op.drop_table('walls')
    with op.batch_alter_table('production_orders', schema=None) as batch_op:
        batch_op.drop_index('uq_production_orders_active_project', sqlite_where=sa.text("status = 'en_cours'"), postgresql_where=sa.text("status = 'en_cours'"))
        batch_op.drop_index(batch_op.f('ix_production_orders_project_id'))

    op.drop_table('production_orders')
    with op.batch_alter_table('layout_runs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_layout_runs_project_id'))

    op.drop_table('layout_runs')
    with op.batch_alter_table('user_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_user_sessions_user_id'))

    op.drop_table('user_sessions')
    with op.batch_alter_table('projects', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_projects_status'))

    op.drop_table('projects')
    with op.batch_alter_table('action_logs', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_action_logs_user_id'))
        batch_op.drop_index(batch_op.f('ix_action_logs_created_at'))
        batch_op.drop_index(batch_op.f('ix_action_logs_action'))

    op.drop_table('action_logs')
    op.drop_table('users')
    op.drop_table('brick_shapes')
    
