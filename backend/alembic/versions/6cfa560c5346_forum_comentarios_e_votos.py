"""forum comentarios e votos

Revision ID: 6cfa560c5346
Revises: c3d4e5f6a7b8
Create Date: 2026-06-26 09:08:55.178128

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '6cfa560c5346'
down_revision: Union[str, None] = 'c3d4e5f6a7b8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Nova tabela: comentario_votos ────────────────────────────────────────
    op.create_table(
        'comentario_votos',
        sa.Column('id', sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column('comentario_id', sa.BigInteger(), nullable=False),
        sa.Column('usuario_uid', sa.String(length=64), nullable=False),
        sa.Column('valor', sa.SmallInteger(), nullable=False),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['comentario_id'], ['questao_comentarios.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('comentario_id', 'usuario_uid', name='uq_voto_comentario_usuario'),
    )
    op.create_index(
        op.f('ix_comentario_votos_comentario_id'),
        'comentario_votos', ['comentario_id'], unique=False,
    )
    op.create_index(
        op.f('ix_comentario_votos_usuario_uid'),
        'comentario_votos', ['usuario_uid'], unique=False,
    )

    # ── Novos campos em questao_comentarios ──────────────────────────────────
    op.add_column(
        'questao_comentarios',
        sa.Column('origem', sa.String(length=16), server_default='studia', nullable=False),
    )
    op.add_column(
        'questao_comentarios',
        sa.Column('owner_uid', sa.String(length=64), nullable=True),
    )
    op.add_column(
        'questao_comentarios',
        sa.Column('parent_id', sa.BigInteger(), nullable=True),
    )
    op.add_column(
        'questao_comentarios',
        sa.Column('score', sa.Integer(), server_default='0', nullable=False),
    )
    op.add_column(
        'questao_comentarios',
        sa.Column('edited_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'questao_comentarios',
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
    )

    # ── Índices nos novos campos ─────────────────────────────────────────────
    op.create_index(
        op.f('ix_questao_comentarios_origem'),
        'questao_comentarios', ['origem'], unique=False,
    )
    op.create_index(
        op.f('ix_questao_comentarios_owner_uid'),
        'questao_comentarios', ['owner_uid'], unique=False,
    )
    op.create_index(
        op.f('ix_questao_comentarios_parent_id'),
        'questao_comentarios', ['parent_id'], unique=False,
    )
    op.create_index(
        op.f('ix_questao_comentarios_score'),
        'questao_comentarios', ['score'], unique=False,
    )

    # ── FK auto-referencial parent_id → id (CASCADE) ─────────────────────────
    op.create_foreign_key(
        'fk_questao_comentarios_parent_id',
        'questao_comentarios',
        'questao_comentarios',
        ['parent_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    # ── Remover FK e índices de questao_comentarios ──────────────────────────
    op.drop_constraint(
        'fk_questao_comentarios_parent_id', 'questao_comentarios', type_='foreignkey',
    )
    op.drop_index(op.f('ix_questao_comentarios_score'), table_name='questao_comentarios')
    op.drop_index(op.f('ix_questao_comentarios_parent_id'), table_name='questao_comentarios')
    op.drop_index(op.f('ix_questao_comentarios_owner_uid'), table_name='questao_comentarios')
    op.drop_index(op.f('ix_questao_comentarios_origem'), table_name='questao_comentarios')
    op.drop_column('questao_comentarios', 'deleted_at')
    op.drop_column('questao_comentarios', 'edited_at')
    op.drop_column('questao_comentarios', 'score')
    op.drop_column('questao_comentarios', 'parent_id')
    op.drop_column('questao_comentarios', 'owner_uid')
    op.drop_column('questao_comentarios', 'origem')

    # ── Remover tabela comentario_votos ──────────────────────────────────────
    op.drop_index(op.f('ix_comentario_votos_usuario_uid'), table_name='comentario_votos')
    op.drop_index(op.f('ix_comentario_votos_comentario_id'), table_name='comentario_votos')
    op.drop_table('comentario_votos')
