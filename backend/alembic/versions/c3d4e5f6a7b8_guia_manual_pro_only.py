"""guia manual (tc ids nullable) + pro_only

Revision ID: c3d4e5f6a7b8
Revises: f1a2b3c4d5e6
Create Date: 2026-06-16 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c3d4e5f6a7b8'
down_revision: Union[str, None] = 'f1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guias manuais não vêm do TC: ids do TC passam a ser opcionais.
    op.alter_column('guias', 'tc_guia_id', existing_type=sa.Integer(), nullable=True)
    op.alter_column(
        'guia_cadernos', 'tc_caderno_id', existing_type=sa.BigInteger(), nullable=True
    )
    # Guia restrito a PRO. server_default só p/ popular linhas existentes.
    op.add_column(
        'guias',
        sa.Column('pro_only', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.alter_column('guias', 'pro_only', server_default=None)


def downgrade() -> None:
    op.drop_column('guias', 'pro_only')
    op.alter_column(
        'guia_cadernos', 'tc_caderno_id', existing_type=sa.BigInteger(), nullable=False
    )
    op.alter_column('guias', 'tc_guia_id', existing_type=sa.Integer(), nullable=False)
