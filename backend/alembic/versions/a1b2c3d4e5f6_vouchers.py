"""vouchers PRO

Revision ID: a1b2c3d4e5f6
Revises: 0805015d119c
Create Date: 2026-06-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '0805015d119c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'vouchers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('codigo', sa.String(length=32), nullable=False),
        sa.Column('dias', sa.Integer(), nullable=False),
        sa.Column('criado_por_uid', sa.String(length=64), nullable=False),
        sa.Column('resgatado_por_uid', sa.String(length=64), nullable=True),
        sa.Column('resgatado_em', sa.DateTime(timezone=True), nullable=True),
        sa.Column('pro_ate', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_vouchers_codigo'), 'vouchers', ['codigo'], unique=True)
    op.create_index(op.f('ix_vouchers_criado_por_uid'), 'vouchers', ['criado_por_uid'], unique=False)
    op.create_index(op.f('ix_vouchers_resgatado_por_uid'), 'vouchers', ['resgatado_por_uid'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_vouchers_resgatado_por_uid'), table_name='vouchers')
    op.drop_index(op.f('ix_vouchers_criado_por_uid'), table_name='vouchers')
    op.drop_index(op.f('ix_vouchers_codigo'), table_name='vouchers')
    op.drop_table('vouchers')
