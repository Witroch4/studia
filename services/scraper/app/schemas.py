"""Schemas Pydantic v2 — contratos REAIS da API TecConcursos.

Schema obtido via captura de XHR ao vivo em 2026-05-27 sobre o caderno
94947327. Endpoint canônico:

    GET /api/cadernos/{caderno_id}/questoes/{posicao}

Retorna `{"questao": {...}}` com 40+ campos achatados (banca/órgão/cargo
vêm como string solta, não objeto aninhado).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class _ApiBase(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True)


class QuestaoApi(_ApiBase):
    # IDs e posição
    idQuestao: int
    numeroQuestaoAtual: int | None = None
    # Conteúdo
    enunciado: str | None = None
    alternativas: list[str] = []
    # Gabarito
    numeroAlternativaCorreta: int | None = None   # 1..5 (A..E)
    alternativaSelecionada: int | None = None
    correcaoQuestao: bool | None = None
    gabaritoPreliminar: bool | None = None
    # Tipo
    tipoQuestao: str | None = None                # MULTIPLA_ESCOLHA, ...
    formatoQuestao: str | None = None             # OBJETIVA, ...
    # Taxonomia flat
    bancaSigla: str | None = None
    bancaUrl: str | None = None
    orgaoSigla: str | None = None
    orgaoNome: str | None = None
    orgaoUrl: str | None = None
    cargoSigla: str | None = None
    concursoId: int | None = None
    concursoArea: str | None = None
    concursoEspecialidade: str | None = None
    concursoAno: int | None = None
    concursoEdicao: str | None = None
    urlConcurso: str | None = None
    idMateria: int | None = None
    nomeMateria: str | None = None
    materiaUrl: str | None = None
    idAssunto: int | None = None
    nomeAssunto: str | None = None
    assuntoUrl: str | None = None
    # Status
    anulada: bool = False
    desatualizada: bool = False
    status: int | None = None


# ─── Erros operacionais ──────────────────────────────────────────


class SessionExpired(Exception):
    """Sessão TC expirou — renovar storage_state via auth.login_and_save."""


class RateLimited(Exception):
    def __init__(self, retry_after: int = 60) -> None:
        super().__init__(f"rate limited; retry after {retry_after}s")
        self.retry_after = retry_after


class AccessBlocked(Exception):
    """HTTP 403/451 — bloqueio explícito do servidor."""


class CaptchaChallenge(Exception):
    """Resposta indicou captcha; resolver manualmente."""


def letra_from_numero(n: int | None) -> str | None:
    """Converte numeroAlternativaCorreta (1..5) em letra (A..E)."""
    if n is None or n < 1 or n > 26:
        return None
    return chr(ord("A") + n - 1)
