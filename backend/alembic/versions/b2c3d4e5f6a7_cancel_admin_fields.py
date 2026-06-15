"""campos de cancelamento administrativo em assinaturas

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b2c3d4e5f6a7'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('assinaturas', sa.Column('cancel_motivo', sa.Text(), nullable=True))
    op.add_column('assinaturas', sa.Column('cancel_admin_uid', sa.String(length=64), nullable=True))
    op.add_column('assinaturas', sa.Column('cancel_em', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column('assinaturas', 'cancel_em')
    op.drop_column('assinaturas', 'cancel_admin_uid')
    op.drop_column('assinaturas', 'cancel_motivo')
