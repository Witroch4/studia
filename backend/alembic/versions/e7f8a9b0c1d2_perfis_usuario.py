"""perfis_usuario (apelido do fórum, avatar e visibilidade do perfil)"""
from alembic import op
import sqlalchemy as sa

revision = "e7f8a9b0c1d2"
down_revision = "a7c8d9e0f1b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "perfis_usuario",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("owner_uid", sa.String(length=64), nullable=False),
        sa.Column("apelido", sa.String(length=32), nullable=True),
        sa.Column("avatar_key", sa.String(length=128), nullable=True),
        sa.Column("perfil_publico", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("mostrar_estatisticas", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("mostrar_foto", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
    )
    op.create_index(
        "ix_perfis_usuario_owner_uid", "perfis_usuario", ["owner_uid"], unique=True
    )
    op.create_index(
        "ix_perfis_usuario_apelido", "perfis_usuario", ["apelido"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_perfis_usuario_apelido", table_name="perfis_usuario")
    op.drop_index("ix_perfis_usuario_owner_uid", table_name="perfis_usuario")
    op.drop_table("perfis_usuario")
