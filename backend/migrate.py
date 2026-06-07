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
        # 1) Habilitar extensão pgvector
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

        # 2) Criar tabelas que não existem
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("""
            CREATE UNIQUE INDEX IF NOT EXISTS uq_questao_anotacoes_scope
            ON questao_anotacoes (COALESCE(usuario_id, 0), COALESCE(caderno_id, 0), questao_id)
        """))

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


if __name__ == "__main__":
    asyncio.run(migrate())
