"""decks: dono (user_id) + catálogo público (is_public) + permitir_promocao

Decks legados (criados quando flashcards era single-user/admin) viram
públicos e sem dono — são o catálogo inicial. slug deixa de ser único
global e passa a ser único por dono (dois usuários podem ter
"engenharia-civil").
"""
from alembic import op
import sqlalchemy as sa

revision = "e7a8b9c0d1f2"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "decks",
        sa.Column("user_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "decks",
        sa.Column("is_public", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "decks",
        sa.Column(
            "permitir_promocao", sa.Boolean(), nullable=False, server_default=sa.true()
        ),
    )
    op.create_index("ix_decks_user_id", "decks", ["user_id"])
    # slug único global → único por dono
    op.drop_index("ix_decks_slug", table_name="decks")
    op.create_index("ix_decks_slug", "decks", ["slug"], unique=False)
    op.create_unique_constraint("uq_decks_user_slug", "decks", ["user_id", "slug"])
    # Legado: decks existentes eram visíveis a todos — viram catálogo público.
    op.execute("UPDATE decks SET is_public = true")


def downgrade() -> None:
    op.drop_constraint("uq_decks_user_slug", "decks", type_="unique")
    op.drop_index("ix_decks_slug", table_name="decks")
    op.create_index("ix_decks_slug", "decks", ["slug"], unique=True)
    op.drop_index("ix_decks_user_id", table_name="decks")
    op.drop_column("decks", "permitir_promocao")
    op.drop_column("decks", "is_public")
    op.drop_column("decks", "user_id")
