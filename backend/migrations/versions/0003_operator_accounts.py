"""operator accounts

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-27 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('operator_users',
    sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
    sa.Column('username', sa.String(length=64), nullable=False),
    sa.Column('display_name', sa.String(length=120), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('operator_sessions',
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ip', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['operator_users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('token_hash')
    )
    with op.batch_alter_table('operator_sessions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_operator_sessions_user_id'), ['user_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_operator_sessions_expires_at'), ['expires_at'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('operator_sessions', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_operator_sessions_expires_at'))
        batch_op.drop_index(batch_op.f('ix_operator_sessions_user_id'))
    op.drop_table('operator_sessions')
    op.drop_table('operator_users')
