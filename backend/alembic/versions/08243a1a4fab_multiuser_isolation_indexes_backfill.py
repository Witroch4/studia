"""multiuser isolation indexes + backfill

Revision ID: 08243a1a4fab
Revises: 0805015d119c
Create Date: 2026-06-13 18:58:41.034269

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import pgvector.sqlalchemy


revision: str = '08243a1a4fab'
down_revision: Union[str, None] = '0805015d119c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    ddl = [
        "DROP INDEX IF EXISTS uq_questao_anotacoes_scope",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_questao_anotacoes_scope_uid "
        "ON questao_anotacoes (COALESCE(usuario_uid, ''), COALESCE(caderno_id, 0), questao_id)",
        "DROP INDEX IF EXISTS ix_questoes_favoritas_questao_id",
        "CREATE INDEX IF NOT EXISTS ix_questoes_favoritas_questao_id ON questoes_favoritas (questao_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_favorita_owner_questao "
        "ON questoes_favoritas (COALESCE(owner_uid, ''), questao_id)",
        "CREATE INDEX IF NOT EXISTS ix_cadernos_questoes_owner_uid ON cadernos_questoes (owner_uid)",
        "CREATE INDEX IF NOT EXISTS ix_questoes_favoritas_owner_uid ON questoes_favoritas (owner_uid)",
        "CREATE INDEX IF NOT EXISTS ix_questao_anotacoes_usuario_uid ON questao_anotacoes (usuario_uid)",
        "CREATE INDEX IF NOT EXISTS ix_calculadora_historico_usuario_uid ON calculadora_historico (usuario_uid)",
    ]
    for stmt in ddl:
        op.execute(stmt)

    # Backfill legados → admin mais antigo. Idempotente; só roda se "user" existir
    # (Better Auth) e houver admin. Cadernos DE GUIA ficam owner_uid=NULL.
    op.execute(
        """
        DO $$
        DECLARE admin_id text;
        BEGIN
          IF to_regclass('public."user"') IS NULL THEN RETURN; END IF;
          SELECT id INTO admin_id FROM "user" WHERE role = 'admin' ORDER BY "createdAt" LIMIT 1;
          IF admin_id IS NULL THEN RETURN; END IF;
          UPDATE cadernos_questoes SET owner_uid = admin_id
            WHERE owner_uid IS NULL AND id NOT IN
              (SELECT caderno_id FROM guia_cadernos WHERE caderno_id IS NOT NULL);
          UPDATE questoes_favoritas SET owner_uid = admin_id WHERE owner_uid IS NULL;
          UPDATE questao_anotacoes SET usuario_uid = admin_id WHERE usuario_uid IS NULL;
          UPDATE resolucoes SET usuario_uid = admin_id WHERE usuario_uid IS NULL;
          UPDATE calculadora_historico SET usuario_uid = admin_id WHERE usuario_uid IS NULL;
        END $$;
        """
    )


def downgrade() -> None:
    for idx in (
        "uq_questao_anotacoes_scope_uid",
        "uq_favorita_owner_questao",
        "ix_cadernos_questoes_owner_uid",
        "ix_questoes_favoritas_owner_uid",
        "ix_questao_anotacoes_usuario_uid",
        "ix_calculadora_historico_usuario_uid",
    ):
        op.execute(f"DROP INDEX IF EXISTS {idx}")
