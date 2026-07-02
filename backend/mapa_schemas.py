"""Shapes Pydantic do JSON extraído do edital (Mapa da Aprovação).

A IA pode devolver lixo parcial: tudo aqui é tolerante — campo ausente vira
None/lista vazia, tipo de evento fora do vocabulário vira "outro", data fora
do ISO vira None. NUNCA levantar por campo opcional malformado.
"""
from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIPOS_EVENTO = {"inscricao", "isencao", "prova", "recurso", "resultado", "homologacao", "outro"}


def _data_iso_ou_none(v: object) -> Optional[str]:
    s = str(v).strip() if v is not None else ""
    return s if _ISO_DATE.match(s) else None


class EventoEdital(BaseModel):
    titulo: str = ""
    data_inicio: Optional[str] = None
    data_fim: Optional[str] = None
    tipo: str = "outro"

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


class EtapaCargo(BaseModel):
    nome: str = ""
    carater: Optional[str] = None


class DistribuicaoQuestoes(BaseModel):
    materia: str = ""
    quantidade: Optional[int] = None
    peso: Optional[float] = None


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


class ConcursoEdital(BaseModel):
    orgao: Optional[str] = None
    banca: Optional[str] = None
    taxa_inscricao: Optional[str] = None
    data_prova: Optional[str] = None

    @field_validator("data_prova", mode="before")
    @classmethod
    def _data(cls, v: object) -> Optional[str]:
        return _data_iso_ou_none(v)


class EditalExtraido(BaseModel):
    concurso: ConcursoEdital = Field(default_factory=ConcursoEdital)
    eventos: list[EventoEdital] = Field(default_factory=list)
    cargos: list[CargoEdital] = Field(default_factory=list)
