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
    tc_rate_per_sec: float = 2.0
    tc_max_concurrency: int = 4
    # Modo humano — substitui rate_per_sec por delays log-normais
    # com pausas longas ocasionais (efeito "lendo a questão", "café")
    tc_human_mode: bool = False
    tc_human_short_min: float = 3.0
    tc_human_short_max: float = 9.0
    tc_human_pause_chance: float = 0.18   # 18% das req: pausa "lendo" 12-35s
    tc_human_break_chance: float = 0.04   # 4% das req: pausa "café" 60-180s
    tc_human_burst_pause_every: int = 40  # a cada N reqs: pausa 3-6min
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
