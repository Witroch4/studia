"""guia_fila (fila serial de coleta de guias)"""
from alembic import op
import sqlalchemy as sa

revision = "e1f2a3b4c5d6"
down_revision = "d9f0a1b2c3e4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "guia_fila",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("url", sa.String(length=512), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="queued"),
        sa.Column("guia_id", sa.Integer(), nullable=True),
        sa.Column("iniciado_em", sa.DateTime(), nullable=True),
        sa.Column("finalizado_em", sa.DateTime(), nullable=True),
        sa.Column("tentativas", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("erro", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["guia_id"], ["guias.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_guia_fila_status", "guia_fila", ["status"])


def downgrade() -> None:
    op.drop_index("ix_guia_fila_status", table_name="guia_fila")
    op.drop_table("guia_fila")
