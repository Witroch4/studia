"""Coleta múltiplos cadernos em sequência com pausas e retomada.

Pensado pra rodar em SSH/produção por HORAS sem intervenção:
  - Carrega lista de URLs/IDs de um JSON
  - Coleta cada caderno via tc_imprimir.scrape_caderno_imprimir
  - Pausa LONGA entre cadernos (3-8min, simula intervalo "humano")
  - Em block_recover ≥3 abandona aquele caderno e segue
  - Estado salvo em SQLite (retomada idempotente via id_externo UNIQUE)
  - Logs estruturados em JSON pra parse posterior

Uso:
    docker run --rm -v $PWD/state:/state -e DATABASE_URL=... studia-scraper \\
      python scripts/scrape_lote.py /state/cadernos.json

Onde cadernos.json é:
    [
      {"url": "https://www.tecconcursos.com.br/questoes/cadernos/95872872", "nome": "PETROBRAS_geral"},
      {"url": "95872884", "nome": "OUTRO"},
      ...
    ]
"""

from __future__ import annotations

import asyncio
import json
import os
import random
import re
import sys
from datetime import datetime
from pathlib import Path

from app.auth import login_and_save_state
from app.observability import configure_logging, get_logger
from app.scrapers.tc_imprimir import scrape_caderno_imprimir

configure_logging()
log = get_logger(__name__)

_RE_ID = re.compile(r"/cadernos/(\d+)")


def extrai_id(s: str) -> int:
    s = s.strip()
    if s.isdigit():
        return int(s)
    m = _RE_ID.search(s)
    if not m:
        raise ValueError(f"URL/ID inválido: {s!r}")
    return int(m.group(1))


async def main(json_path: Path) -> None:
    cadernos = json.loads(json_path.read_text(encoding="utf-8"))
    log.info("lote.start", arquivo=str(json_path), n_cadernos=len(cadernos))

    # Login fresh no início
    log.info("lote.login_inicial")
    await login_and_save_state(headless=True)

    relatorio = []
    for i, c in enumerate(cadernos, 1):
        caderno_id = extrai_id(c["url"])
        nome = c.get("nome", f"caderno_{caderno_id}")

        log.info("lote.caderno_inicio", n=i, total=len(cadernos), caderno=caderno_id, nome=nome)

        ts_inicio = datetime.utcnow().isoformat()
        try:
            res = await scrape_caderno_imprimir(caderno_id)
            status = "ok"
        except Exception as e:  # noqa: BLE001
            log.error("lote.caderno_falhou", caderno=caderno_id, err=str(e))
            res = {"ok": 0, "erro": 1, "paginas": 0}
            status = f"falhou: {type(e).__name__}"

        relatorio.append({
            "ordem": i,
            "caderno_id": caderno_id,
            "nome": nome,
            "ts_inicio": ts_inicio,
            "ts_fim": datetime.utcnow().isoformat(),
            "status": status,
            "ok": res.get("ok", 0),
            "erro": res.get("erro", 0),
            "block_recover": res.get("block_recover", 0),
            "paginas": res.get("paginas", 0),
        })

        # Persistir relatório a cada caderno (recovery se crashar)
        # Em /state pq /app/scripts pode estar read-only no container
        state_dir = Path(os.environ.get("SCRAPE_STATE_PATH", "/state/scrape_state.db")).parent
        report_path = state_dir / f"{json_path.stem}.relatorio.json"
        try:
            report_path.write_text(json.dumps(relatorio, indent=2, ensure_ascii=False), encoding="utf-8")
            log.info("lote.relatorio_salvo", file=str(report_path))
        except Exception as e:  # noqa: BLE001
            log.warning("lote.relatorio_falhou", err=str(e))

        # Pausa "humana" entre cadernos (3-8min, ou 1-2min se foi rapidinho)
        if i < len(cadernos):
            wait = random.uniform(180, 480) if res.get("paginas", 0) > 30 else random.uniform(60, 120)
            log.info("lote.pausa_entre_cadernos", wait_s=round(wait, 1))
            await asyncio.sleep(wait)

    log.info("lote.fim", relatorio=relatorio)
    print("\n" + "=" * 60)
    print(f"LOTE CONCLUÍDO — relatório em {report_path}")
    print("=" * 60)
    for r in relatorio:
        print(f"  {r['ordem']}. {r['nome']} (#{r['caderno_id']}) — "
              f"{r['ok']} ok, {r['erro']} erro, status={r['status']}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("uso: python scripts/scrape_lote.py <cadernos.json>")
        sys.exit(2)
    asyncio.run(main(Path(sys.argv[1])))
