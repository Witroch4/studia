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
