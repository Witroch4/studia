"""cronograma

Revision ID: f1a2b3c4d5e6
Revises: b2c3d4e5f6a7
Create Date: 2026-06-15 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'b2c3d4e5f6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'cronogramas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('usuario_uid', sa.String(length=64), nullable=False),
        sa.Column('caderno_id', sa.Integer(), nullable=False),
        sa.Column('data_inicio', sa.Date(), nullable=False),
        sa.Column('data_prova', sa.Date(), nullable=False),
        sa.Column('rebaseline_em', sa.Date(), nullable=True),
        sa.Column('dias_folga', sa.JSON(), nullable=False),
        sa.Column('buffer_dias', sa.Integer(), nullable=False),
        sa.Column('incluir_revisao', sa.Boolean(), nullable=False),
        sa.Column('incluir_discursivas', sa.Boolean(), nullable=False),
        sa.Column('incluir_simulados', sa.Boolean(), nullable=False),
        sa.Column('discursivas_por_semana', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['caderno_id'], ['cadernos_questoes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('usuario_uid', 'caderno_id', name='uq_cronograma_user_caderno'),
    )
    op.create_index(op.f('ix_cronogramas_usuario_uid'), 'cronogramas', ['usuario_uid'], unique=False)
    op.create_index(op.f('ix_cronogramas_caderno_id'), 'cronogramas', ['caderno_id'], unique=False)
    op.create_table(
        'cronograma_discursivas',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cronograma_id', sa.Integer(), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('tema', sa.Text(), nullable=False),
        sa.Column('tipo', sa.String(length=64), nullable=False),
        sa.Column('qtd', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('nota', sa.Float(), nullable=True),
        sa.Column('reescrita', sa.Boolean(), nullable=False),
        sa.Column('observacoes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['cronograma_id'], ['cronogramas.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_cronograma_discursivas_cronograma_id'), 'cronograma_discursivas', ['cronograma_id'], unique=False)
    op.create_table(
        'cronograma_simulados',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('cronograma_id', sa.Integer(), nullable=False),
        sa.Column('data', sa.Date(), nullable=False),
        sa.Column('tipo', sa.String(length=64), nullable=False),
        sa.Column('objetivas_planejadas', sa.Integer(), nullable=False),
        sa.Column('meta_objetiva', sa.Integer(), nullable=False),
        sa.Column('resultado_objetiva', sa.Integer(), nullable=True),
        sa.Column('discursiva_planejada', sa.Integer(), nullable=False),
        sa.Column('resultado_discursiva', sa.Float(), nullable=True),
        sa.Column('observacoes', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['cronograma_id'], ['cronogramas.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_cronograma_simulados_cronograma_id'), 'cronograma_simulados', ['cronograma_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_cronograma_simulados_cronograma_id'), table_name='cronograma_simulados')
    op.drop_table('cronograma_simulados')
    op.drop_index(op.f('ix_cronograma_discursivas_cronograma_id'), table_name='cronograma_discursivas')
    op.drop_table('cronograma_discursivas')
    op.drop_index(op.f('ix_cronogramas_caderno_id'), table_name='cronogramas')
    op.drop_index(op.f('ix_cronogramas_usuario_uid'), table_name='cronogramas')
    op.drop_table('cronogramas')
