"""forum_professores: forum_tipo + persona_nome em questao_comentarios

Revision ID: b8e4f1a2c3d6
Revises: 6cfa560c5346
Create Date: 2026-06-26
"""
from alembic import op
import sqlalchemy as sa

revision = "b8e4f1a2c3d6"
down_revision = "6cfa560c5346"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "questao_comentarios",
        sa.Column("forum_tipo", sa.String(16), nullable=False, server_default="alunos"),
    )
    op.create_index(
        "ix_questao_comentarios_forum_tipo", "questao_comentarios", ["forum_tipo"]
    )
    op.add_column(
        "questao_comentarios",
        sa.Column("persona_nome", sa.String(64), nullable=True),
    )


def downgrade() -> None:
    op.drop_index("ix_questao_comentarios_forum_tipo", table_name="questao_comentarios")
    op.drop_column("questao_comentarios", "persona_nome")
    op.drop_column("questao_comentarios", "forum_tipo")
