"""Persistência incremental de progresso em SQLite — habilita retomada.

Cada execução marca IDs já coletadas; um restart pula o que está pronto.
Mantido em SQLite (zero-config) para não acoplar ao Postgres principal.
"""

from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Iterable

from app.config import get_settings
from app.observability import get_logger

log = get_logger(__name__)


class ScrapeState:
    def __init__(self, db_path: Path | None = None) -> None:
        self.db_path = db_path or get_settings().scrape_state_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS coletadas (
                id INTEGER PRIMARY KEY,
                caderno_id INTEGER,
                ts INTEGER,
                status TEXT
            )
            """
        )
        self.conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_coletadas_caderno ON coletadas (caderno_id)"
        )
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS posicoes_coletadas (
                caderno_id INTEGER NOT NULL,
                posicao INTEGER NOT NULL,
                qid INTEGER,
                ts INTEGER,
                PRIMARY KEY (caderno_id, posicao)
            )
            """
        )
        self.conn.commit()

    def posicao_ja_coletada(self, caderno_id: int, posicao: int) -> bool:
        cur = self.conn.execute(
            "SELECT 1 FROM posicoes_coletadas WHERE caderno_id=? AND posicao=?",
            (caderno_id, posicao),
        )
        return cur.fetchone() is not None

    def marca_posicao(self, caderno_id: int, posicao: int, qid: int) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO posicoes_coletadas VALUES (?,?,?,strftime('%s','now'))",
            (caderno_id, posicao, qid),
        )
        self.conn.commit()

    def ja_coletada(self, qid: int) -> bool:
        cur = self.conn.execute(
            "SELECT status FROM coletadas WHERE id = ? AND status = 'ok'",
            (qid,),
        )
        return cur.fetchone() is not None

    def marca(self, qid: int, caderno_id: int | None, status: str = "ok") -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO coletadas (id, caderno_id, ts, status) VALUES (?, ?, ?, ?)",
            (qid, caderno_id, int(time.time()), status),
        )
        self.conn.commit()

    def contar(self, status: str = "ok") -> int:
        cur = self.conn.execute(
            "SELECT COUNT(*) FROM coletadas WHERE status = ?", (status,)
        )
        return int(cur.fetchone()[0])

    def contar_prefix(self, prefix: str) -> int:
        cur = self.conn.execute(
            "SELECT COUNT(*) FROM coletadas WHERE status LIKE ? || '%'", (prefix,)
        )
        return int(cur.fetchone()[0])

    def pendentes(self, ids: Iterable[int]) -> list[int]:
        ids_list = list(ids)
        if not ids_list:
            return []
        placeholders = ",".join("?" * len(ids_list))
        cur = self.conn.execute(
            f"SELECT id FROM coletadas WHERE id IN ({placeholders}) AND status = 'ok'",
            ids_list,
        )
        done = {row[0] for row in cur.fetchall()}
        return [i for i in ids_list if i not in done]

    def close(self) -> None:
        self.conn.close()
