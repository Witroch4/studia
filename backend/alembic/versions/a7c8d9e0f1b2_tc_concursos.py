"""tc_concursos + tc_concurso_arquivos (metadados de concursos coletados da fonte externa)"""
from alembic import op
import sqlalchemy as sa

revision = "a7c8d9e0f1b2"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tc_concursos",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("concurso_id_externo", sa.BigInteger(), nullable=False),
        sa.Column("edital_id_externo", sa.BigInteger(), nullable=True),
        sa.Column("nome_completo", sa.Text(), nullable=False),
        sa.Column("url_concurso", sa.String(length=512), nullable=False),
        sa.Column("banca_nome", sa.Text(), nullable=True),
        sa.Column("orgao_sigla", sa.String(length=128), nullable=True),
        sa.Column("orgao_nome", sa.Text(), nullable=True),
        sa.Column("edital_nome", sa.Text(), nullable=True),
        sa.Column("ano", sa.Integer(), nullable=True),
        sa.Column("data_aplicacao", sa.DateTime(), nullable=True),
        sa.Column("escolaridade", sa.String(length=64), nullable=True),
        sa.Column("raw_json", sa.JSON(), nullable=True),
        sa.Column("criado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "atualizado_em",
            sa.DateTime(),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_tc_concursos_concurso_id_externo", "tc_concursos", ["concurso_id_externo"], unique=True
    )

    op.create_table(
        "tc_concurso_arquivos",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("concurso_id", sa.BigInteger(), nullable=False),
        sa.Column("tipo", sa.String(length=64), nullable=False),
        sa.Column("arquivo_id_externo", sa.BigInteger(), nullable=False),
        sa.Column("uuid", sa.String(length=64), nullable=False),
        sa.Column("nome_arquivo", sa.Text(), nullable=False),
        sa.Column("minio_object_key", sa.String(length=512), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=True),
        sa.Column("tamanho_bytes", sa.BigInteger(), nullable=True),
        sa.Column("baixado_em", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["concurso_id"], ["tc_concursos.id"], ondelete="CASCADE"),
        sa.UniqueConstraint(
            "concurso_id", "arquivo_id_externo", name="uq_tc_concurso_arquivo"
        ),
    )
    op.create_index(
        "ix_tc_concurso_arquivos_concurso_id", "tc_concurso_arquivos", ["concurso_id"]
    )
    op.create_index("ix_tc_concurso_arquivos_uuid", "tc_concurso_arquivos", ["uuid"])


def downgrade() -> None:
    op.drop_index("ix_tc_concurso_arquivos_uuid", table_name="tc_concurso_arquivos")
    op.drop_index("ix_tc_concurso_arquivos_concurso_id", table_name="tc_concurso_arquivos")
    op.drop_table("tc_concurso_arquivos")
    op.drop_index("ix_tc_concursos_concurso_id_externo", table_name="tc_concursos")
    op.drop_table("tc_concursos")
