"""Configuração centralizada via pydantic-settings.

Segue o padrão witdev-platform-core: única classe Settings com todas as
variáveis tipadas. Carrega .env automaticamente.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    environment: str = "development"
    log_level: str = "INFO"

    # TecConcursos
    tc_base: str = "https://www.tecconcursos.com.br"
    tc_email: str | None = None
    tc_password: str | None = None
    tc_storage_state_path: Path = Path("./storage_state.json")
    tc_rate_per_sec: float = 0.5          # default conservador (era 2.0 — disparou anti-bot)
    tc_max_concurrency: int = 1           # default sequencial (era 4 — fatal pra anti-bot)
    # Modo humano "balanceado" — alvo ~3h para 876 reqs.
    # Curva: maioria 3-7s, alguns "lendo" 8-18s, poucos "longa" 25-50s,
    # raros "café" 60-120s. Sem burst-pauses violentas.
    tc_human_mode: bool = True            # ON por default (já que falamos com TC)
    tc_human_short_min: float = 3.0
    tc_human_short_max: float = 7.0
    tc_human_long_chance: float = 0.18    # 18%: pausa curta 8-18s
    tc_human_long_min: float = 8.0
    tc_human_long_max: float = 18.0
    tc_human_pause_chance: float = 0.05   # 5%: pausa "longa" 25-50s
    tc_human_pause_min: float = 25.0
    tc_human_pause_max: float = 50.0
    tc_human_break_chance: float = 0.02   # 2%: pausa "café" 60-120s
    tc_human_break_min: float = 60.0
    tc_human_break_max: float = 120.0
    tc_human_burst_pause_every: int = 150 # a cada 150 reqs: pausa 60-120s
    tc_human_burst_pause_min: float = 60.0
    tc_human_burst_pause_max: float = 120.0
    tc_user_agent: str = (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    )

    # Persistência
    database_url: str = (
        "postgresql+asyncpg://postgres:postgres@localhost:5433/studia"
    )
    scrape_state_path: Path = Path("./scrape_state.db")
    discovery_dump_dir: Path = Path("./discovery")

    # TaskIQ/NATS studIA
    nats_servers: str = "nats://nats:4222"
    taskiq_result_redis_url: str = "redis://redis:6379/2"
    taskiq_idempotency_redis_url: str = "redis://redis:6379/2"
    taskiq_idempotency_ttl_seconds: int = 604800
    taskiq_studia_stream: str = "TASKIQ_STUDIA"
    taskiq_studia_default_subject: str = "taskiq.studia.default"
    taskiq_studia_low_subject: str = "taskiq.studia.low"
    taskiq_studia_default_durable: str = "studia-default-workers"
    taskiq_studia_low_durable: str = "studia-low-workers"
    taskiq_studia_default_pull_batch: int = 1
    # 1 = serial: o limite real é o anti-bot do TC; paralelizar queima a sessão
    taskiq_studia_default_max_ack_pending: int = 1
    taskiq_studia_low_pull_batch: int = 1
    taskiq_studia_low_max_ack_pending: int = 5
    taskiq_studia_ack_wait_seconds: int = 600
    taskiq_studia_requeue_stale_seconds: int = 120
    taskiq_studia_max_deliver: int = 3
    taskiq_studia_image_target_active: int = 5
    tc_page_size: int = 200
    # Sessão queimada é recuperável via relogin automático — cooldown curto
    tc_block_401_452_seconds: int = 1800
    tc_block_403_429_seconds: int = 7200

    @property
    def nats_servers_list(self) -> list[str]:
        return [
            server.strip()
            for server in self.nats_servers.split(",")
            if server.strip()
        ]

    # Meili: indexação incremental por página (auto-reindex durante a coleta).
    # Vêm do /opt/studia/.env (MEILI_URL/MEILI_KEY). Se ausentes, o push é pulado.
    meili_url: str | None = None
    meili_key: str | None = None

    # Futuro: integração com platform-api
    backend_url: str | None = None
    platform_api_key: str | None = None

    # ─── Residential Proxy WitDev (para rodar em SSH/datacenter) ──────
    # Quando setado, TODAS as conexões TC saem pelo IP residencial de casa.
    # Doc: /home/wital/witdev-platform-core/proxy-residencial/docs/WITDEV-PROXY-API.md
    # Formato canônico: socks5h://tc-scraper:${RP_SERVICE_SECRET}@residential-proxy:1080
    residential_proxy_url: str | None = None

    # ─── /imprimir scraper safety (anti-403/429) ──────────────────────
    # Defaults conservadores. Pode subir mais via env vars na produção.
    imprimir_pause_min: float = 4.0       # seg entre páginas (mín)
    imprimir_pause_max: float = 7.0       # seg entre páginas (máx)
    imprimir_burst_every: int = 20        # a cada N páginas, pausa burst
    imprimir_burst_min: float = 25.0
    imprimir_burst_max: float = 50.0
    imprimir_block_pause: float = 180.0   # pausa 3min em 403/429


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
