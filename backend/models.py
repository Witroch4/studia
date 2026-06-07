from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Table,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

import enum


class Base(DeclarativeBase):
    pass


# ─── Enums ──────────────────────────────────────────────


class StatusProcessamento(str, enum.Enum):
    PENDENTE = "PENDENTE"
    PROCESSANDO = "PROCESSANDO"
    CONCLUIDO = "CONCLUIDO"
    ERRO = "ERRO"


# ─── Deck & Flashcard (existentes) ──────────────────────


class Deck(Base):
    __tablename__ = "decks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(256))
    icon: Mapped[str] = mapped_column(String(64), default="style")
    icon_color: Mapped[str] = mapped_column(String(32), default="text-cyan-500")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    cards: Mapped[list["Flashcard"]] = relationship(
        back_populates="deck", cascade="all, delete-orphan"
    )


class Flashcard(Base):
    __tablename__ = "flashcards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    deck_id: Mapped[int] = mapped_column(ForeignKey("decks.id", ondelete="CASCADE"))
    assunto: Mapped[str] = mapped_column(String(256))
    frente: Mapped[str] = mapped_column(Text)
    verso: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Novos campos para integração com aulas
    aula_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("aulas.id", ondelete="SET NULL"), nullable=True
    )
    proxima_revisao: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    fator_facilidade: Mapped[float] = mapped_column(Float, default=2.5)

    deck: Mapped["Deck"] = relationship(back_populates="cards")
    aula: Mapped[Optional["Aula"]] = relationship(back_populates="flashcards")


# ─── Disciplinas & Aulas (novos) ────────────────────────


class Disciplina(Base):
    __tablename__ = "disciplinas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    nome: Mapped[str] = mapped_column(String(256))
    descricao: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    icon: Mapped[str] = mapped_column(String(64), default="library_books")
    icon_color: Mapped[str] = mapped_column(String(32), default="text-cyan-500")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    aulas: Mapped[list["Aula"]] = relationship(
        back_populates="disciplina", cascade="all, delete-orphan"
    )


class Aula(Base):
    __tablename__ = "aulas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    disciplina_id: Mapped[int] = mapped_column(
        ForeignKey("disciplinas.id", ondelete="CASCADE")
    )
    numero: Mapped[int] = mapped_column(Integer)
    titulo: Mapped[str] = mapped_column(String(512))
    pdf_path_minio: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default=StatusProcessamento.PENDENTE.value
    )
    texto_completo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    modelo_usado: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    erro_msg: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    disciplina: Mapped["Disciplina"] = relationship(back_populates="aulas")
    blocos: Mapped[list["BlocoConteudo"]] = relationship(
        back_populates="aula", cascade="all, delete-orphan"
    )
    flashcards: Mapped[list["Flashcard"]] = relationship(back_populates="aula")


class BlocoConteudo(Base):
    __tablename__ = "blocos_conteudo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    aula_id: Mapped[int] = mapped_column(
        ForeignKey("aulas.id", ondelete="CASCADE")
    )
    paginas: Mapped[str] = mapped_column(String(32))
    resumo_markdown: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    formulas_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    aula: Mapped["Aula"] = relationship(back_populates="blocos")


# ─── Concorrência / Concurso (novos) ─────────────────────


class Concurso(Base):
    __tablename__ = "concursos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(256))
    arquivo_nome: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    total_candidatos: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    candidatos: Mapped[list["Candidato"]] = relationship(
        back_populates="concurso", cascade="all, delete-orphan"
    )


class Candidato(Base):
    __tablename__ = "candidatos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    concurso_id: Mapped[int] = mapped_column(
        ForeignKey("concursos.id", ondelete="CASCADE"), index=True
    )
    inscricao: Mapped[str] = mapped_column(String(64))
    cargo: Mapped[str] = mapped_column(String(256), default="—")
    polo: Mapped[str] = mapped_column(String(32), default="—")
    macropolo: Mapped[str] = mapped_column(String(64), default="—")
    nascimento: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    pontos: Mapped[float] = mapped_column(Float, default=0.0, index=True)
    discursiva: Mapped[float] = mapped_column(Float, default=0.0)
    tot_esp: Mapped[float] = mapped_column(Float, default=0.0)
    tot_bas: Mapped[float] = mapped_column(Float, default=0.0)
    l_port: Mapped[float] = mapped_column(Float, default=0.0)
    l_ing: Mapped[float] = mapped_column(Float, default=0.0)
    situacao: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    pos_ac: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pos_pcd: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pos_pn: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pos_pi: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    pos_pq: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    concurso: Mapped["Concurso"] = relationship(back_populates="candidatos")


# ─── witdev-tec-master: Questões / Concursos (novos) ────────────


questao_assunto = Table(
    "questao_assunto",
    Base.metadata,
    Column("questao_id", BigInteger, ForeignKey("questoes.id", ondelete="CASCADE"), primary_key=True),
    Column("assunto_id", Integer, ForeignKey("assuntos.id", ondelete="CASCADE"), primary_key=True),
)


class Banca(Base):
    __tablename__ = "bancas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_externo: Mapped[Optional[int]] = mapped_column(Integer, unique=True, nullable=True, index=True)
    nome: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    slug: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    sigla: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Orgao(Base):
    __tablename__ = "orgaos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_externo: Mapped[Optional[int]] = mapped_column(Integer, unique=True, nullable=True, index=True)
    nome: Mapped[str] = mapped_column(String(512), index=True)
    slug: Mapped[str] = mapped_column(String(512), unique=True, index=True)
    sigla: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    esfera: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    regiao: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Cargo(Base):
    __tablename__ = "cargos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_externo: Mapped[Optional[int]] = mapped_column(Integer, unique=True, nullable=True, index=True)
    orgao_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orgaos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    nome: Mapped[str] = mapped_column(String(512), index=True)
    ano: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    escolaridade: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    area: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Prova(Base):
    __tablename__ = "provas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_externo: Mapped[Optional[int]] = mapped_column(Integer, unique=True, nullable=True, index=True)
    banca_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("bancas.id", ondelete="SET NULL"), nullable=True, index=True
    )
    orgao_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orgaos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cargo_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cargos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    codigo: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ano: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    data_aplicacao: Mapped[Optional[datetime]] = mapped_column(Date, nullable=True)
    pdf_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Materia(Base):
    __tablename__ = "materias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_externo: Mapped[Optional[int]] = mapped_column(Integer, unique=True, nullable=True, index=True)
    nome: Mapped[str] = mapped_column(String(256), unique=True, index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("materias.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Assunto(Base):
    __tablename__ = "assuntos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    id_externo: Mapped[Optional[int]] = mapped_column(Integer, unique=True, nullable=True, index=True)
    materia_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("materias.id", ondelete="SET NULL"), nullable=True, index=True
    )
    nome: Mapped[str] = mapped_column(String(512), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (UniqueConstraint("materia_id", "nome", name="uq_assunto_materia_nome"),)


class Questao(Base):
    __tablename__ = "questoes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_externo: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, nullable=True, index=True)
    codigo_externo: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True, index=True)
    prova_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("provas.id", ondelete="SET NULL"), nullable=True, index=True
    )
    banca_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("bancas.id", ondelete="SET NULL"), nullable=True, index=True
    )
    orgao_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("orgaos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    cargo_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cargos.id", ondelete="SET NULL"), nullable=True, index=True
    )
    materia_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("materias.id", ondelete="SET NULL"), nullable=True, index=True
    )
    numero_na_prova: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tipo: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    enunciado_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    enunciado_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    gabarito: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    texto_associado: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    imagens: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    status: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    raw_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Embedding pgvector (Gemini text-embedding-004 = 768 dims)
    # Populado por backend/generate_embeddings.py
    embedding_dim: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    alternativas: Mapped[list["Alternativa"]] = relationship(
        back_populates="questao", cascade="all, delete-orphan"
    )
    assuntos: Mapped[list["Assunto"]] = relationship(secondary=questao_assunto)


class Resolucao(Base):
    """Cada vez que alguém responde uma questão.

    Sem auth ainda — `usuario_id` opcional. Usamos pra calcular
    "(N Resolvidas, X Acertos, Y Erros)" estilo TC.
    """
    __tablename__ = "resolucoes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    questao_id: Mapped[int] = mapped_column(
        ForeignKey("questoes.id", ondelete="CASCADE"), index=True
    )
    caderno_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cadernos_questoes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    usuario_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    resposta: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    acertou: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    tempo_segundos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class QuestaoAnotacao(Base):
    """Canvas and strike-through state for one question in one caderno scope."""

    __tablename__ = "questao_anotacoes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    caderno_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cadernos_questoes.id", ondelete="CASCADE"), nullable=True, index=True
    )
    questao_id: Mapped[int] = mapped_column(
        ForeignKey("questoes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    canvas_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    strikes_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index(
            "uq_questao_anotacoes_scope",
            func.coalesce(usuario_id, 0),
            func.coalesce(caderno_id, 0),
            questao_id,
            unique=True,
        ),
    )


class CalculadoraHistorico(Base):
    """Scientific calculator history, optionally linked to a question."""

    __tablename__ = "calculadora_historico"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    usuario_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    caderno_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    questao_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class CadernoQuestoes(Base):
    __tablename__ = "cadernos_questoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(512))
    pasta: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    filtros: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    question_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Alternativa(Base):
    __tablename__ = "alternativas"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    id_externo: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, nullable=True, index=True)
    questao_id: Mapped[int] = mapped_column(
        ForeignKey("questoes.id", ondelete="CASCADE"), index=True
    )
    letra: Mapped[Optional[str]] = mapped_column(String(2), nullable=True)
    texto_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    texto_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    correta: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    ordem: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    questao: Mapped["Questao"] = relationship(back_populates="alternativas")
