from datetime import date, datetime
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
    SmallInteger,
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
    # slug único POR DONO (dois usuários podem ter "engenharia-civil")
    __table_args__ = (UniqueConstraint("user_id", "slug", name="uq_decks_user_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    slug: Mapped[str] = mapped_column(String(128), index=True)
    nome: Mapped[str] = mapped_column(String(256))
    icon: Mapped[str] = mapped_column(String(64), default="style")
    icon_color: Mapped[str] = mapped_column(String(32), default="text-cyan-500")
    # Dono (Better Auth user.id). NULL = legado/sistema (catálogo inicial).
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # Catálogo público read-only; admin promove/despromove.
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # false = dono marcou "Impedir promoção" ao catálogo.
    permitir_promocao: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
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
    # Dono do import (Better Auth user.id). NULL = legado do pool global.
    user_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    # Catálogo: admin publica para todos; user comum importa privado.
    is_public: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
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
    nome: Mapped[str] = mapped_column(Text, index=True)
    ano: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    escolaridade: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # Texto livre vindo do TC (sem limite confiável): manter TEXT evita
    # StringDataRightTruncationError que derrubava a faixa inteira na coleta.
    area: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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
    # Better Auth usa id string ("user".id é text) — este é o vínculo real com o
    # dono da resolução (usado no limite diário de questões e nas estatísticas).
    usuario_uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    resposta: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    acertou: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    tempo_segundos: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class QuestaoAnotacao(Base):
    """Canvas and strike-through state for one question in one caderno scope."""

    __tablename__ = "questao_anotacoes"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    usuario_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    # Dono real da anotação (Better Auth "user".id). Escopo por usuário: cada
    # aluno tem o próprio canvas/strikes na mesma questão de um caderno.
    usuario_uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
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
            "uq_questao_anotacoes_scope_uid",
            func.coalesce(usuario_uid, ""),
            func.coalesce(caderno_id, 0),
            questao_id,
            unique=True,
        ),
    )


class CalculadoraHistorico(Base):
    """Scientific calculator history, optionally linked to a question."""

    __tablename__ = "calculadora_historico"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    usuario_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    # Dono real do histórico (Better Auth "user".id), por usuário.
    usuario_uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    caderno_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    questao_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    expression: Mapped[str] = mapped_column(Text, nullable=False)
    result: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)


class QuestaoFavorita(Base):
    """Questões marcadas com estrela, por usuário (owner_uid = "user".id)."""

    __tablename__ = "questoes_favoritas"

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True
    )
    questao_id: Mapped[int] = mapped_column(
        ForeignKey("questoes.id", ondelete="CASCADE"), index=True
    )
    owner_uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Uma favorita por (usuário, questão) — dois usuários podem favoritar a mesma.
    __table_args__ = (
        UniqueConstraint("owner_uid", "questao_id", name="uq_favorita_owner_questao"),
    )


class CadernoQuestoes(Base):
    __tablename__ = "cadernos_questoes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # Dono do caderno (Better Auth "user".id). NULL = caderno de catálogo
    # (materializado de um guia); acessível a todos via aba Guias, nunca listado
    # em "Minhas Pastas". Cadernos pessoais ("NOVO CADERNO") têm owner_uid setado.
    owner_uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    nome: Mapped[str] = mapped_column(String(512))
    pasta: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    filtros: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    question_ids: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    # Idempotência da materialização a partir de um caderno do TC.
    tc_caderno_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, unique=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class CadernoSalvo(Base):
    """Caderno do catálogo (de guia) que um usuário salvou nas suas "Minhas
    Pastas".

    NÃO duplica questões: aponta para o `CadernoQuestoes` compartilhado
    (`owner_uid` NULL, materializado de um guia). O estudo/respostas/stats já
    são por usuário via `Resolucao.usuario_uid` — aqui guardamos apenas o
    vínculo "este usuário salvou este caderno do catálogo". Conta nova começa
    sem nenhum salvo; saved-set vazio = Minhas Pastas vazia.
    """

    __tablename__ = "cadernos_salvos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_uid: Mapped[str] = mapped_column(String(64), index=True)
    caderno_id: Mapped[int] = mapped_column(
        ForeignKey("cadernos_questoes.id", ondelete="CASCADE"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("usuario_uid", "caderno_id", name="uq_caderno_salvo"),
    )


# ─── Guias de estudo (importados do TC) ─────────────────────────


class Guia(Base):
    __tablename__ = "guias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # NULL para guias manuais (montados pelo admin, sem origem no TC).
    tc_guia_id: Mapped[Optional[int]] = mapped_column(
        Integer, unique=True, index=True, nullable=True
    )
    slug: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    nome: Mapped[str] = mapped_column(String(512))
    banca: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    tc_pasta_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending")
    # Guia restrito a contas PRO (assinatura ou voucher). Admin sempre vê.
    pro_only: Mapped[bool] = mapped_column(Boolean, default=False)
    total_cadernos: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    cadernos: Mapped[list["GuiaCaderno"]] = relationship(
        back_populates="guia", cascade="all, delete-orphan"
    )


class GuiaCaderno(Base):
    __tablename__ = "guia_cadernos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    guia_id: Mapped[int] = mapped_column(
        ForeignKey("guias.id", ondelete="CASCADE"), index=True
    )
    # NULL quando o caderno do guia não tem origem no TC (guia manual).
    tc_caderno_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, index=True, nullable=True
    )
    tc_caderno_base: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    nome: Mapped[str] = mapped_column(String(512))
    disciplina: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    total_questoes: Mapped[int] = mapped_column(Integer, default=0)
    total_capitulos: Mapped[int] = mapped_column(Integer, default=0)
    ordem: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # CadernoQuestoes materializado no studIA (quando coleta concluída).
    caderno_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cadernos_questoes.id", ondelete="SET NULL"), nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    guia: Mapped["Guia"] = relationship(back_populates="cadernos")

    __table_args__ = (
        UniqueConstraint("guia_id", "tc_caderno_id", name="uq_guia_caderno"),
    )


class GuiaFila(Base):
    """Fila FIFO de coleta de guias. Garante 1 guia coletando por vez + cooldown
    entre guias (o supervisor `scripts/guia_supervisor.py` consome esta tabela).

    Ciclo de status: queued → resolving → collecting → done/skipped/error.
    `finalizado_em` do último terminado é a referência do cooldown.
    """

    __tablename__ = "guia_fila"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # URL colada do guia. NULL em re-coleta (já tem guia_id).
    url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, server_default="queued", default="queued", index=True
    )
    guia_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("guias.id", ondelete="SET NULL"), nullable=True
    )
    iniciado_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    finalizado_em: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    tentativas: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0", default=0
    )
    erro: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    requested_by: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


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


# ─── Assinaturas (Stripe) ───────────────────────────────────────


class Assinatura(Base):
    """Assinatura Stripe de um usuário Better Auth (`usuario_uid` = "user".id).

    Plano grátis = sem linha aqui (ou status inativo). Plano pago = linha com
    status 'active'/'trialing' e `current_period_end` no futuro → libera
    questões ilimitadas. Atualizada pelos webhooks do Stripe.
    """

    __tablename__ = "assinaturas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_uid: Mapped[str] = mapped_column(String(64), index=True)
    stripe_customer_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    stripe_subscription_id: Mapped[Optional[str]] = mapped_column(
        String(64), nullable=True, unique=True, index=True
    )
    price_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="incomplete", index=True)
    current_period_end: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancel_at_period_end: Mapped[bool] = mapped_column(Boolean, default=False)
    # Cancelamento administrativo (por violação etc.) — preenchido pelo painel admin.
    cancel_motivo: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    cancel_admin_uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    cancel_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


# ─── Vouchers PRO (resgate sem Stripe) ──────────────────────────


class Voucher(Base):
    """Código de cupom que concede acesso PRO por `dias` (sem pagamento Stripe).

    Gerado pelo admin, resgatável UMA vez por UMA conta. Ao resgatar gravamos a
    conta (`resgatado_por_uid`) e a data PRO acumulada da conta (`pro_ate`), que
    estende a partir da data mais distante já vigente (Stripe ou voucher anterior).
    Disponível = `resgatado_por_uid IS NULL`. O acesso vale enquanto `pro_ate > now`.
    """

    __tablename__ = "vouchers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    codigo: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    dias: Mapped[int] = mapped_column(Integer, default=365)
    criado_por_uid: Mapped[str] = mapped_column(String(64), index=True)
    resgatado_por_uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    resgatado_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    pro_ate: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


# ─── Estatísticas e fórum do TC por questão ─────────────────────


class QuestaoEstatistica(Base):
    """Estatísticas agregadas do TC de uma questão (puxadas na coleta)."""

    __tablename__ = "questao_estatisticas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    questao_id: Mapped[int] = mapped_column(
        ForeignKey("questoes.id", ondelete="CASCADE"), unique=True, index=True
    )
    total_resolucoes: Mapped[int] = mapped_column(Integer, default=0)
    total_acertos: Mapped[int] = mapped_column(Integer, default=0)
    percentual_acertos: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # Distribuição das respostas: {"A": 1234, "B": 567, ...} ou {"CERTO": .., "ERRADO": ..}.
    distribuicao_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    fonte: Mapped[str] = mapped_column(String(16), default="tc")
    coletado_em: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class QuestaoComentario(Base):
    """Comentário/fórum do TC associado a uma questão (puxado na coleta)."""

    __tablename__ = "questao_comentarios"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    questao_id: Mapped[int] = mapped_column(
        ForeignKey("questoes.id", ondelete="CASCADE"), index=True
    )
    # Idempotência: id do comentário no TC (upsert por este campo).
    tc_comentario_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, nullable=True, unique=True, index=True
    )
    tc_parent_id: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True, index=True)
    autor_nome: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    autor_tipo: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # professor | aluno
    texto_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    texto_md: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    curtidas: Mapped[int] = mapped_column(Integer, default=0)
    publicado_em: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # ─── Campos do fórum studIA (feed unificado local + TC anonimizado) ───
    origem: Mapped[str] = mapped_column(
        String(16), default="studia", server_default="studia", index=True
    )  # "studia" (aluno) | "tc" (importado, exibido com pseudônimo)
    owner_uid: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("questao_comentarios.id", ondelete="CASCADE"), nullable=True, index=True
    )  # resposta a um post raiz (1 nível só)
    score: Mapped[int] = mapped_column(Integer, default=0, server_default="0", index=True)
    edited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ─── Fórum dos professores (mesmo quadro de comentários, segregado) ───
    forum_tipo: Mapped[str] = mapped_column(
        String(16), default="alunos", server_default="alunos", index=True
    )  # "alunos" | "professores"
    persona_nome: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)


class ComentarioVoto(Base):
    """Voto (+1/-1) de um usuário em um comentário do fórum. Um por (comentário, usuário)."""

    __tablename__ = "comentario_votos"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    comentario_id: Mapped[int] = mapped_column(
        ForeignKey("questao_comentarios.id", ondelete="CASCADE"), index=True
    )
    usuario_uid: Mapped[str] = mapped_column(String(64), index=True)
    valor: Mapped[int] = mapped_column(SmallInteger)  # +1 | -1
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("comentario_id", "usuario_uid", name="uq_voto_comentario_usuario"),
    )


class QuestaoTcImport(Base):
    """Marcador: comentários do TC já buscados para (questão, quadro).

    Existência da linha = já buscado (mesmo que `count=0`). Evita re-scrape.
    """
    __tablename__ = "questao_tc_imports"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    questao_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("questoes.id", ondelete="CASCADE"), index=True
    )
    quadro: Mapped[str] = mapped_column(String(16))  # "alunos" | "professores"
    count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    fetched_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    __table_args__ = (
        UniqueConstraint("questao_id", "quadro", name="uq_tc_import_questao_quadro"),
    )


# ─── Cronograma ────────────────────────────────────────────


class Cronograma(Base):
    """Configuração de um cronograma de estudo para um caderno (1 por usuário/caderno).

    O plano dia-a-dia, KPIs e revisões NÃO são persistidos — são calculados sob
    demanda (cronograma_core) a partir desta config + da tabela `resolucoes`.
    """
    __tablename__ = "cronogramas"
    __table_args__ = (
        UniqueConstraint("usuario_uid", "caderno_id", name="uq_cronograma_user_caderno"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    usuario_uid: Mapped[str] = mapped_column(String(64), index=True)
    caderno_id: Mapped[int] = mapped_column(
        ForeignKey("cadernos_questoes.id", ondelete="CASCADE"), index=True
    )
    data_inicio: Mapped[date] = mapped_column(Date)
    data_prova: Mapped[date] = mapped_column(Date)
    rebaseline_em: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    dias_folga: Mapped[list] = mapped_column(JSON, default=list)
    buffer_dias: Mapped[int] = mapped_column(Integer, default=21)
    incluir_revisao: Mapped[bool] = mapped_column(Boolean, default=True)
    incluir_discursivas: Mapped[bool] = mapped_column(Boolean, default=False)
    incluir_simulados: Mapped[bool] = mapped_column(Boolean, default=True)
    discursivas_por_semana: Mapped[int] = mapped_column(Integer, default=2)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )


class CronogramaDiscursiva(Base):
    __tablename__ = "cronograma_discursivas"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cronograma_id: Mapped[int] = mapped_column(
        ForeignKey("cronogramas.id", ondelete="CASCADE"), index=True
    )
    data: Mapped[date] = mapped_column(Date)
    tema: Mapped[str] = mapped_column(Text)
    tipo: Mapped[str] = mapped_column(String(64), default="Treino 20 linhas")
    qtd: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="Pendente")
    nota: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reescrita: Mapped[bool] = mapped_column(Boolean, default=False)
    observacoes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class CronogramaSimulado(Base):
    __tablename__ = "cronograma_simulados"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    cronograma_id: Mapped[int] = mapped_column(
        ForeignKey("cronogramas.id", ondelete="CASCADE"), index=True
    )
    data: Mapped[date] = mapped_column(Date)
    tipo: Mapped[str] = mapped_column(String(64))
    objetivas_planejadas: Mapped[int] = mapped_column(Integer, default=0)
    meta_objetiva: Mapped[int] = mapped_column(Integer, default=0)
    resultado_objetiva: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    discursiva_planejada: Mapped[int] = mapped_column(Integer, default=0)
    resultado_discursiva: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    observacoes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


class AppSetting(Base):
    """Configuração chave→valor do app (ex.: modelo de IA por recurso).

    Chaves atuais: llm.calculadora_reconhecimento (alias canônico do proxy),
    llm.processamento_pdf e llm.chat_aula (id Gemini upstream — exceção Batch).
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )
