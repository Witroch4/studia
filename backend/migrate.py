"""
Migração simples: garante que todas as tabelas e colunas do models.py existam no banco.

- Cria tabelas novas via create_all (não altera existentes)
- Detecta colunas faltantes e adiciona via ALTER TABLE
- Idempotente: pode rodar quantas vezes quiser

Uso: python migrate.py
"""

import asyncio

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateTable

from database import engine
from models import Base


def get_column_sql(table, column):
    """Gera o tipo SQL de uma coluna a partir do modelo SQLAlchemy."""
    col = table.columns[column]
    col_type = col.type.compile(dialect=engine.dialect)

    parts = [f'"{column}" {col_type}']

    if col.nullable:
        parts.append("NULL")
    else:
        if col.server_default is not None:
            parts.append("NOT NULL")

    if col.server_default is not None:
        parts.append(f"DEFAULT {col.server_default.arg.text}")

    return " ".join(parts)


async def migrate():
    async with engine.begin() as conn:
        # 1) Habilitar extensão pgvector apenas no Postgres
        if engine.dialect.name == "postgresql":
            await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        # 2) Criar tabelas que não existem (índices por-usuário ficam no passo 4,
        #    pois dependem de colunas adicionadas no passo 3).
        await conn.run_sync(Base.metadata.create_all)

        # 3) Detectar colunas faltantes em tabelas existentes
        def _inspect(sync_conn):
            insp = inspect(sync_conn)
            existing = {}
            for table_name in insp.get_table_names():
                cols = {c["name"] for c in insp.get_columns(table_name)}
                existing[table_name] = cols
            return existing

        existing = await conn.run_sync(_inspect)

        alter_stmts = []
        for table_name, table in Base.metadata.tables.items():
            if table_name not in existing:
                continue  # tabela nova, já foi criada pelo create_all
            model_cols = set(table.columns.keys())
            db_cols = existing[table_name]
            missing = model_cols - db_cols

            for col_name in missing:
                col = table.columns[col_name]
                col_type = col.type.compile(dialect=engine.dialect)

                nullable = "NULL" if col.nullable else "NOT NULL"
                default = ""
                if col.server_default is not None:
                    default = f" DEFAULT {col.server_default.arg.text}"

                fk = ""
                if col.foreign_keys:
                    fk_obj = list(col.foreign_keys)[0]
                    target = fk_obj.target_fullname
                    ondelete = f" ON DELETE {fk_obj.ondelete}" if fk_obj.ondelete else ""
                    fk = f' REFERENCES {target.split(".")[0]}({target.split(".")[1]}){ondelete}'

                stmt = f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{col_name}" {col_type}{default}{fk}'
                if col.nullable:
                    stmt += " NULL"
                alter_stmts.append(stmt)

        if alter_stmts:
            print(f"Aplicando {len(alter_stmts)} ALTER(s):")
            for stmt in alter_stmts:
                print(f"  -> {stmt}")
                await conn.execute(text(stmt))
            print("Migrações aplicadas!")
        else:
            print("Banco já está atualizado.")

        # 4) Isolamento multiusuário (idempotente). Substitui os índices únicos
        #    single-tenant (que bloqueiam dois usuários no mesmo recurso) pelos
        #    por-usuário e faz backfill dos dados legados → admin mais antigo.
        #    Postgres-only (dev/prod usam Postgres; testes usam create_all direto).
        if engine.dialect.name == "postgresql":
            await _migrar_isolamento(conn)


async def _migrar_isolamento(conn) -> None:
    # 4a) Índices únicos por usuário (drop dos antigos single-tenant).
    ddl = [
        # Anotações: escopo por usuario_uid (antes era COALESCE(usuario_id,0)).
        "DROP INDEX IF EXISTS uq_questao_anotacoes_scope",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_questao_anotacoes_scope_uid "
        "ON questao_anotacoes (COALESCE(usuario_uid, ''), COALESCE(caderno_id, 0), questao_id)",
        # Favoritas: trocar UNIQUE(questao_id) por UNIQUE(owner_uid, questao_id).
        "DROP INDEX IF EXISTS ix_questoes_favoritas_questao_id",
        "CREATE INDEX IF NOT EXISTS ix_questoes_favoritas_questao_id ON questoes_favoritas (questao_id)",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_favorita_owner_questao "
        "ON questoes_favoritas (COALESCE(owner_uid, ''), questao_id)",
        # Índices de filtro por dono/usuário (perf das listagens por usuário).
        "CREATE INDEX IF NOT EXISTS ix_cadernos_questoes_owner_uid ON cadernos_questoes (owner_uid)",
        "CREATE INDEX IF NOT EXISTS ix_questoes_favoritas_owner_uid ON questoes_favoritas (owner_uid)",
        "CREATE INDEX IF NOT EXISTS ix_questao_anotacoes_usuario_uid ON questao_anotacoes (usuario_uid)",
        "CREATE INDEX IF NOT EXISTS ix_calculadora_historico_usuario_uid ON calculadora_historico (usuario_uid)",
    ]
    for stmt in ddl:
        await conn.execute(text(stmt))

    # 4b) Backfill dos legados → admin mais antigo. Só roda se a tabela "user"
    #     (Better Auth) existir e houver admin. Tudo idempotente (WHERE ... IS NULL).
    tem_user = (await conn.execute(text('SELECT to_regclass(\'public."user"\')'))).scalar()
    if not tem_user:
        print('Backfill pulado: tabela "user" ausente (Better Auth não criou ainda).')
        return
    admin_id = (
        await conn.execute(
            text('SELECT id FROM "user" WHERE role = \'admin\' ORDER BY "createdAt" LIMIT 1')
        )
    ).scalar()
    if not admin_id:
        print("Backfill pulado: nenhum admin encontrado.")
        return

    # Cadernos pessoais legados → admin. Cadernos DE GUIA ficam owner_uid=NULL
    # (catálogo compartilhado, acessado via aba Guias; nunca em "Minhas Pastas").
    await conn.execute(
        text(
            "UPDATE cadernos_questoes SET owner_uid = :a "
            "WHERE owner_uid IS NULL AND id NOT IN "
            "(SELECT caderno_id FROM guia_cadernos WHERE caderno_id IS NOT NULL)"
        ),
        {"a": admin_id},
    )
    for tabela, col in (
        ("questoes_favoritas", "owner_uid"),
        ("questao_anotacoes", "usuario_uid"),
        ("resolucoes", "usuario_uid"),
        ("calculadora_historico", "usuario_uid"),
    ):
        await conn.execute(
            text(f"UPDATE {tabela} SET {col} = :a WHERE {col} IS NULL"), {"a": admin_id}
        )
    print(f"Backfill multiusuário aplicado (admin={admin_id}).")


if __name__ == "__main__":
    asyncio.run(migrate())
