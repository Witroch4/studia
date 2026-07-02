"""concursos: dono (user_id) + catálogo público (is_public)

Concursos legados (importados quando a feature era um pool global) viram
públicos e sem dono, para continuarem visíveis a todos.
"""
from alembic import op
import sqlalchemy as sa

revision = "d5e6f7a8b9c0"
down_revision = "a4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "concursos",
        sa.Column("user_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "concursos",
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_concursos_user_id", "concursos", ["user_id"])
    # Legado: tudo que existia era visível a todos — vira catálogo público.
    op.execute("UPDATE concursos SET is_public = true")


def downgrade() -> None:
    op.drop_index("ix_concursos_user_id", table_name="concursos")
    op.drop_column("concursos", "is_public")
    op.drop_column("concursos", "user_id")
