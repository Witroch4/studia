"""Supervisor da fila de coleta de guias.

Loop em processo separado (imagem do backend): a cada `GUIA_SUPERVISOR_INTERVAL`
segundos chama `guia_service.guia_supervisor_tick`, que garante 1 guia coletando
por vez com cooldown entre guias. Roda como serviço `studia-guia-supervisor`
(replicas: 1).
"""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone


def carregar_config() -> dict:
    return {
        "cooldown_s": int(os.getenv("GUIA_COOLDOWN_SECONDS", "900")),
        "interval": int(os.getenv("GUIA_SUPERVISOR_INTERVAL", "30")),
        "max_coleta_s": int(os.getenv("GUIA_MAX_COLETA_SECONDS", "21600")),
        "max_tentativas": int(os.getenv("GUIA_RESOLVE_MAX_TENTATIVAS", "3")),
    }


async def loop() -> None:
    import guia_service
    from database import async_session

    cfg = carregar_config()
    print(f"guia_supervisor iniciado: {cfg}", flush=True)
    while True:
        try:
            async with async_session() as db:
                agora = datetime.now(timezone.utc).replace(tzinfo=None)
                out = await guia_service.guia_supervisor_tick(
                    db,
                    agora=agora,
                    cooldown_s=cfg["cooldown_s"],
                    max_coleta_s=cfg["max_coleta_s"],
                    max_tentativas=cfg["max_tentativas"],
                )
                await db.commit()
            if out.get("acao") not in (None, "nada", "aguardando"):
                print(f"guia_supervisor.tick {out}", flush=True)
        except Exception as exc:  # noqa: BLE001 — loop nunca morre por 1 falha
            print(f"guia_supervisor.erro {exc!r}", flush=True)
        await asyncio.sleep(max(cfg["interval"], 5))


if __name__ == "__main__":
    asyncio.run(loop())
