"""Shapes Pydantic do JSON extraído do edital (Mapa da Aprovação).

A IA pode devolver lixo parcial: tudo aqui é tolerante — campo ausente vira
None/lista vazia, tipo de evento fora do vocabulário vira "outro", data fora
do ISO vira None. NUNCA levantar por campo opcional malformado.
"""
from __future__ import annotations

import math
import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIPOS_EVENTO = {"inscricao", "isencao", "prova", "recurso", "resultado", "homologacao", "outro"}


def _data_iso_ou_none(v: object) -> Optional[str]:
    s = str(v).strip() if v is not None else ""
    return s if _ISO_DATE.match(s) else None


def _str_ou_none(v: object) -> Optional[str]:
    """Campo str opcional: null vira None, qualquer outro tipo vira str()."""
    if v is None:
        return None
    return str(v).strip() or None


def _str_vazia(v: object) -> str:
    """Campo str obrigatório-com-default (titulo/nome/materia): null vira ""."""
    if v is None:
        return ""
    return str(v).strip()


def _int_ou_none(v: object) -> Optional[int]:
    s = str(v).strip() if v is not None else ""
    try:
        return int(s)
    except ValueError:
        pass
    try:
        # JSON costuma trazer float inteiro ("10.0") onde se espera int.
        return int(float(s))
    except (ValueError, OverflowError):
        return None


def _float_ou_none(v: object) -> Optional[float]:
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    # inf/-inf/nan não são JSON estrito (coluna JSON não aceita).
    return f if math.isfinite(f) else None


def _lista_de_str(v: object) -> list[str]:
    """Lista de strings tolerante: não-lista vira [], item não-string vira str()."""
    if not isinstance(v, list):
        return []
    return [str(item).strip() for item in v if item is not None]


def _lista_de_dicts(v: object) -> list[dict]:
    """Lista de sub-modelos tolerante: não-lista vira [], item não-dict é descartado."""
    if not isinstance(v, list):
        return []
    return [item for item in v if isinstance(item, dict)]


def _dict_ou_vazio(v: object) -> dict:
    """Modelo aninhado tolerante: não-dict vira {} (todos os campos no default)."""
    return v if isinstance(v, dict) else {}


class EventoEdital(BaseModel):
    titulo: str = ""
    data_inicio: Optional[str] = None
    data_fim: Optional[str] = None
    tipo: str = "outro"

    @field_validator("titulo", mode="before")
    @classmethod
    def _titulo(cls, v: object) -> str:
        return _str_vazia(v)

    @field_validator("tipo", mode="before")
    @classmethod
    def _tipo(cls, v: object) -> str:
        s = str(v or "").strip().lower()
        return s if s in TIPOS_EVENTO else "outro"

    @field_validator("data_inicio", "data_fim", mode="before")
    @classmethod
    def _datas(cls, v: object) -> Optional[str]:
        return _data_iso_ou_none(v)


class MateriaProgramatica(BaseModel):
    materia: str = ""
    assuntos: list[str] = Field(default_factory=list)

    @field_validator("materia", mode="before")
    @classmethod
    def _materia(cls, v: object) -> str:
        return _str_vazia(v)

    @field_validator("assuntos", mode="before")
    @classmethod
    def _assuntos(cls, v: object) -> list[str]:
        return _lista_de_str(v)


class EtapaCargo(BaseModel):
    nome: str = ""
    carater: Optional[str] = None

    @field_validator("nome", mode="before")
    @classmethod
    def _nome(cls, v: object) -> str:
        return _str_vazia(v)

    @field_validator("carater", mode="before")
    @classmethod
    def _carater(cls, v: object) -> Optional[str]:
        return _str_ou_none(v)


class DistribuicaoQuestoes(BaseModel):
    materia: str = ""
    quantidade: Optional[int] = None
    peso: Optional[float] = None

    @field_validator("materia", mode="before")
    @classmethod
    def _materia(cls, v: object) -> str:
        return _str_vazia(v)

    @field_validator("quantidade", mode="before")
    @classmethod
    def _quantidade(cls, v: object) -> Optional[int]:
        return _int_ou_none(v)

    @field_validator("peso", mode="before")
    @classmethod
    def _peso(cls, v: object) -> Optional[float]:
        return _float_ou_none(v)


class CargoEdital(BaseModel):
    nome: str = ""
    escolaridade: Optional[str] = None
    # Editais escrevem "CR", "2 + CR", "R$ 6.500,00" — strings livres.
    vagas: Optional[str] = None
    salario: Optional[str] = None
    requisitos: Optional[str] = None
    jornada: Optional[str] = None
    conteudo_programatico: list[MateriaProgramatica] = Field(default_factory=list)
    etapas: list[EtapaCargo] = Field(default_factory=list)
    distribuicao_questoes: list[DistribuicaoQuestoes] = Field(default_factory=list)

    @field_validator("nome", mode="before")
    @classmethod
    def _nome(cls, v: object) -> str:
        return _str_vazia(v)

    @field_validator(
        "escolaridade", "vagas", "salario", "requisitos", "jornada", mode="before"
    )
    @classmethod
    def _opcionais(cls, v: object) -> Optional[str]:
        return _str_ou_none(v)

    @field_validator(
        "conteudo_programatico", "etapas", "distribuicao_questoes", mode="before"
    )
    @classmethod
    def _listas(cls, v: object) -> list[dict]:
        return _lista_de_dicts(v)


class ConcursoEdital(BaseModel):
    orgao: Optional[str] = None
    banca: Optional[str] = None
    taxa_inscricao: Optional[str] = None
    data_prova: Optional[str] = None

    @field_validator("orgao", "banca", "taxa_inscricao", mode="before")
    @classmethod
    def _opcionais(cls, v: object) -> Optional[str]:
        return _str_ou_none(v)

    @field_validator("data_prova", mode="before")
    @classmethod
    def _data(cls, v: object) -> Optional[str]:
        return _data_iso_ou_none(v)


class EditalExtraido(BaseModel):
    concurso: ConcursoEdital = Field(default_factory=ConcursoEdital)
    eventos: list[EventoEdital] = Field(default_factory=list)
    cargos: list[CargoEdital] = Field(default_factory=list)

    @field_validator("concurso", mode="before")
    @classmethod
    def _concurso(cls, v: object) -> dict:
        return _dict_ou_vazio(v)

    @field_validator("eventos", "cargos", mode="before")
    @classmethod
    def _listas(cls, v: object) -> list[dict]:
        return _lista_de_dicts(v)
