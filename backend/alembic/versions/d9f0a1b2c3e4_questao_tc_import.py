"""questao_tc_imports (marcador anti-rescrape de comentários do TC)"""
from alembic import op
import sqlalchemy as sa

revision = "d9f0a1b2c3e4"
down_revision = "b8e4f1a2c3d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "questao_tc_imports",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("questao_id", sa.BigInteger(), nullable=False),
        sa.Column("quadro", sa.String(length=16), nullable=False),
        sa.Column("count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fetched_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["questao_id"], ["questoes.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("questao_id", "quadro", name="uq_tc_import_questao_quadro"),
    )
    op.create_index("ix_questao_tc_imports_questao_id", "questao_tc_imports", ["questao_id"])


def downgrade() -> None:
    op.drop_index("ix_questao_tc_imports_questao_id", table_name="questao_tc_imports")
    op.drop_table("questao_tc_imports")
