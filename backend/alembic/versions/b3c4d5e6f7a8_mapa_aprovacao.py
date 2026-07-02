# backend/alembic/versions/b3c4d5e6f7a8_mapa_aprovacao.py
"""mapa da aprovação: edital_extracoes + mapas_aprovacao + mapa_itens

Revision ID: b3c4d5e6f7a8
Revises: e7f8a9b0c1d2
"""
import sqlalchemy as sa
from alembic import op

revision = "b3c4d5e6f7a8"
# Linearizada após perfis_usuario (feature paralela mergeada antes) — evita duas heads.
down_revision = "e7f8a9b0c1d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "edital_extracoes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("concurso_id", sa.BigInteger(),
                  sa.ForeignKey("tc_concursos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pendente"),
        sa.Column("dados", sa.JSON(), nullable=True),
        sa.Column("modelo_usado", sa.String(128), nullable=True),
        sa.Column("prompt_versao", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("erro_msg", sa.Text(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("atualizado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_edital_extracoes_concurso_id", "edital_extracoes",
                    ["concurso_id"], unique=True)

    op.create_table(
        "mapas_aprovacao",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("usuario_uid", sa.String(64), nullable=False),
        sa.Column("concurso_id", sa.BigInteger(),
                  sa.ForeignKey("tc_concursos.id", ondelete="CASCADE"), nullable=False),
        sa.Column("extracao_id", sa.Integer(),
                  sa.ForeignKey("edital_extracoes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cargo_nome", sa.String(512), nullable=False),
        sa.Column("cargo_dados", sa.JSON(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("usuario_uid", "concurso_id", "cargo_nome",
                            name="uq_mapa_user_concurso_cargo"),
    )
    op.create_index("ix_mapas_aprovacao_usuario_uid", "mapas_aprovacao", ["usuario_uid"])
    op.create_index("ix_mapas_aprovacao_concurso_id", "mapas_aprovacao", ["concurso_id"])

    op.create_table(
        "mapa_itens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("mapa_id", sa.Integer(),
                  sa.ForeignKey("mapas_aprovacao.id", ondelete="CASCADE"), nullable=False),
        sa.Column("materia_nome", sa.String(512), nullable=False),
        sa.Column("assunto_texto", sa.Text(), nullable=False),
        sa.Column("ordem", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(16), nullable=False, server_default="nao_visto"),
        sa.Column("materia_id", sa.Integer(),
                  sa.ForeignKey("materias.id", ondelete="SET NULL"), nullable=True),
        sa.Column("caderno_id", sa.Integer(),
                  sa.ForeignKey("cadernos_questoes.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_mapa_itens_mapa_id", "mapa_itens", ["mapa_id"])


def downgrade() -> None:
    op.drop_table("mapa_itens")
    op.drop_table("mapas_aprovacao")
    op.drop_table("edital_extracoes")
