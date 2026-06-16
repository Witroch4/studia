import re
import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sse_starlette.sse import EventSourceResponse

from database import engine, get_db
from models import (
    Base, Deck, Flashcard, Disciplina, Aula, BlocoConteudo,
    StatusProcessamento, Concurso, Candidato,
)
from parser import parse_markdown
from minio_client import upload_pdf, get_presigned_url, ensure_bucket
from auth import require_admin
from security import CSRF_COOKIE, SESSION_COOKIE
import concurso_engine as ce


_log = logging.getLogger(__name__)


# ─── Helpers ─────────────────────────────────────────────


def slugify(text: str) -> str:
    replacements = {
        "á": "a", "â": "a", "ã": "a",
        "é": "e", "ê": "e",
        "í": "i",
        "ó": "o", "ô": "o",
        "ú": "u",
        "ç": "c",
    }
    s = text.lower().strip()
    for old, new in replacements.items():
        s = s.replace(old, new)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


# ─── Modelos Gemini disponíveis ──────────────────────────


GEMINI_MODELS = [
    {
        "value": "gemini-3.1-pro-preview",
        "label": "Gemini 3.1 Pro Preview",
        "description": "SOTA reasoning com profundidade e multimodal avançado",
        "pricing": "≤200K: $2.00 / $12.00 · >200K: $4.00 / $18.00",
        "recommended": False,
    },
    {
        "value": "gemini-3-flash-preview",
        "label": "Gemini 3 Flash Preview",
        "description": "Inteligência frontier com velocidade, search e grounding",
        "pricing": "$0.50 / $3.00 por 1M tokens",
        "recommended": True,
    },
    {
        "value": "gemini-3-pro-preview",
        "label": "Gemini 3 Pro Preview",
        "description": "Raciocínio avançado, multimodal e vibe coding",
        "pricing": "≤200K: $2.00 / $12.00 · >200K: $4.00 / $18.00",
        "recommended": False,
    },
    {
        "value": "gemini-2.5-pro",
        "label": "Gemini 2.5 Pro",
        "description": "Geração anterior, excelente em código e raciocínio complexo",
        "pricing": "≤200K: $1.25 / $10.00 · >200K: $2.50 / $15.00",
        "recommended": False,
    },
    {
        "value": "gemini-2.5-flash",
        "label": "Gemini 2.5 Flash",
        "description": "Raciocínio híbrido, 1M context, thinking budgets",
        "pricing": "$0.30 / $2.50 por 1M tokens",
        "recommended": False,
    },
    {
        "value": "gemini-2.5-flash-lite",
        "label": "Gemini 2.5 Flash Lite",
        "description": "Menor e mais econômico, feito para uso em escala",
        "pricing": "$0.10 / $0.40 por 1M tokens",
        "recommended": False,
    },
    {
        "value": "gemini-flash-latest",
        "label": "Gemini Flash (latest)",
        "description": "Alias automático → gemini-2.5-flash-preview mais recente",
        "pricing": "$0.30 / $2.50 por 1M tokens",
        "recommended": False,
    },
    {
        "value": "gemini-flash-lite-latest",
        "label": "Gemini Flash Lite (latest)",
        "description": "Alias automático → Flash Lite mais recente",
        "pricing": "$0.10 / $0.40 por 1M tokens",
        "recommended": False,
    },
]


# ─── App ─────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Migrações rodam via Alembic: ./dev.sh migrate (ou python -m scripts.db_prepare)
    # Garantir bucket MinIO existe
    try:
        await asyncio.to_thread(ensure_bucket)
    except Exception:
        pass  # MinIO pode não estar pronto ainda

    # Produtor do NATS JetStream: precisa de startup() p/ criar/garantir o
    # stream e poder publicar (.kiq). Diferente do Redis, não conecta lazy.
    from worker import broker
    if not broker.is_worker_process:
        try:
            await broker.startup()
        except Exception as exc:
            _log.warning("NATS broker startup falhou; .kiq vai falhar por request até reconectar: %s", exc)
    try:
        yield
    finally:
        if not broker.is_worker_process:
            try:
                await broker.shutdown()
            except Exception:
                pass


app = FastAPI(title="studIA API", version="0.2.0", lifespan=lifespan)

# Em prod front e back são same-origin (Traefik), mas mantemos a allowlist
# explícita p/ dev (cross-origin) e para qualquer origem extra via env.
# allow_credentials=True exige origens explícitas (não "*") — o cookie do
# Better Auth só viaja com credenciais habilitadas dos dois lados.
import os as _os  # noqa: E402

_DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "https://studia.witdev.com.br",
]
_extra_origins = [o.strip() for o in _os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
CORS_ALLOWED = list(dict.fromkeys(_DEFAULT_ORIGINS + _extra_origins))

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ALLOWED,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_CSRF_EXEMPT = {"/api/session/handoff", "/api/session/logout"}
_MUTATING = {"POST", "PUT", "PATCH", "DELETE"}


@app.middleware("http")
async def csrf_protect(request, call_next):
    if (
        request.method in _MUTATING
        and request.url.path not in _CSRF_EXEMPT
        and request.cookies.get(SESSION_COOKIE)  # só exige CSRF p/ sessão JWT
    ):
        header = request.headers.get("x-csrf-token")
        cookie = request.cookies.get(CSRF_COOKIE)
        if not header or not cookie or header != cookie:
            from fastapi.responses import JSONResponse
            return JSONResponse({"detail": "csrf inválido"}, status_code=403)
    return await call_next(request)


# Guias de estudo importados do TC (cascata guia → pasta → cadernos → questões).
# Registrado ANTES de q_router para que `/api/q/guias` não caia no catch-all
# `/api/q/{questao_id}`.
from guias_router import router as guias_router  # noqa: E402
app.include_router(guias_router)

# witdev-tec-master: questões/cadernos/IA
from q_router import router as q_router  # noqa: E402
app.include_router(q_router)

from cronograma_router import router as cronograma_router  # noqa: E402
app.include_router(cronograma_router)

# Assinatura / billing (Stripe)
from billing_router import router as billing_router  # noqa: E402
app.include_router(billing_router)

# Vouchers PRO (resgate sem Stripe)
from voucher_router import router as voucher_router  # noqa: E402
app.include_router(voucher_router)

# Painel admin de assinaturas (gestão Stripe)
from admin_billing_router import router as admin_billing_router  # noqa: E402
app.include_router(admin_billing_router)

# Auth: handoff Better Auth → JWT + logout
from auth_router import router as auth_router  # noqa: E402
app.include_router(auth_router)


# ─── Health ──────────────────────────────────────────────


@app.get("/api/health")
def health():
    return {"status": "ok"}


# ─── Modelos ─────────────────────────────────────────────


@app.get("/api/modelos")
def list_models():
    return GEMINI_MODELS


# ─── Decks ───────────────────────────────────────────────


@app.get("/api/decks")
async def list_decks(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            Deck.id,
            Deck.slug,
            Deck.nome,
            Deck.icon,
            Deck.icon_color,
            func.count(Flashcard.id).label("total"),
        )
        .outerjoin(Flashcard)
        .group_by(Deck.id)
    )
    decks = [
        {
            "id": row.slug,
            "nome": row.nome,
            "icon": row.icon,
            "icon_color": row.icon_color,
            "total": row.total,
            "revisar": row.total,  # TODO: spaced repetition
            "pct": 0,
        }
        for row in result.all()
    ]
    return decks


@app.delete("/api/decks/{deck_slug}")
async def delete_deck(deck_slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Deck).where(Deck.slug == deck_slug)
    )
    deck = result.scalar_one_or_none()
    if not deck:
        raise HTTPException(status_code=404, detail="Deck não encontrado")
    await db.delete(deck)
    await db.commit()
    return {"ok": True}


# ─── Flashcards ──────────────────────────────────────────


@app.get("/api/flashcards/todos")
async def get_all_cards(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Flashcard, Deck.nome).join(Deck)
    )
    rows = result.all()
    cards = [
        {
            "id": card.id,
            "tema": nome,
            "assunto": card.assunto,
            "frente": card.frente,
            "verso": card.verso,
        }
        for card, nome in rows
    ]
    return {"deck_id": "todos", "deck_nome": "Todos", "total": len(cards), "cards": cards}


@app.get("/api/flashcards/{deck_slug}")
async def get_deck_cards(deck_slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Flashcard, Deck.nome)
        .join(Deck)
        .where(Deck.slug == deck_slug)
    )
    rows = result.all()
    cards = [
        {
            "id": card.id,
            "tema": nome,
            "assunto": card.assunto,
            "frente": card.frente,
            "verso": card.verso,
        }
        for card, nome in rows
    ]
    deck_nome = rows[0][1] if rows else deck_slug
    return {"deck_id": deck_slug, "deck_nome": deck_nome, "total": len(cards), "cards": cards}


class FlashcardCreate(BaseModel):
    tema: str
    assunto: str
    frente: str
    verso: str


@app.post("/api/flashcards")
async def create_flashcard(data: FlashcardCreate, db: AsyncSession = Depends(get_db)):
    slug = slugify(data.tema)

    deck = (await db.execute(select(Deck).where(Deck.slug == slug))).scalar_one_or_none()
    if not deck:
        deck = Deck(slug=slug, nome=data.tema)
        db.add(deck)
        await db.flush()

    card = Flashcard(
        deck_id=deck.id,
        assunto=data.assunto,
        frente=data.frente,
        verso=data.verso,
    )
    db.add(card)
    await db.commit()
    await db.refresh(card)

    return {
        "id": card.id,
        "deck_id": slug,
        "tema": data.tema,
        "assunto": card.assunto,
        "frente": card.frente,
        "verso": card.verso,
    }


@app.post("/api/flashcards/import")
async def import_flashcards(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    content = await file.read()
    parsed = parse_markdown(content.decode("utf-8"))

    deck_cache: dict[str, Deck] = {}
    imported_cards = []

    for item in parsed:
        slug = slugify(item["tema"])

        if slug not in deck_cache:
            deck = (await db.execute(select(Deck).where(Deck.slug == slug))).scalar_one_or_none()
            if not deck:
                deck = Deck(slug=slug, nome=item["tema"])
                db.add(deck)
                await db.flush()
            deck_cache[slug] = deck

        deck = deck_cache[slug]
        card = Flashcard(
            deck_id=deck.id,
            assunto=item["assunto"],
            frente=item["frente"],
            verso=item["verso"],
        )
        db.add(card)
        imported_cards.append({
            "tema": item["tema"],
            "assunto": item["assunto"],
            "frente": item["frente"],
            "verso": item["verso"],
        })

    await db.commit()

    temas = list({c["tema"] for c in imported_cards})

    return {
        "imported": len(imported_cards),
        "temas": temas,
        "cards": [
            {"id": i + 1, "tema": c["tema"], "assunto": c["assunto"], "frente": c["frente"], "verso": c["verso"]}
            for i, c in enumerate(imported_cards)
        ],
    }


# ─── Disciplinas ─────────────────────────────────────────


class DisciplinaCreate(BaseModel):
    nome: str
    descricao: Optional[str] = None
    icon: str = "library_books"
    icon_color: str = "text-cyan-500"


@app.get("/api/disciplinas")
async def list_disciplinas(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            Disciplina.id,
            Disciplina.slug,
            Disciplina.nome,
            Disciplina.descricao,
            Disciplina.icon,
            Disciplina.icon_color,
            func.count(Aula.id).label("total_aulas"),
        )
        .outerjoin(Aula)
        .group_by(Disciplina.id)
    )
    return [
        {
            "id": row.id,
            "slug": row.slug,
            "nome": row.nome,
            "descricao": row.descricao,
            "icon": row.icon,
            "icon_color": row.icon_color,
            "total_aulas": row.total_aulas,
        }
        for row in result.all()
    ]


@app.post("/api/disciplinas")
async def create_disciplina(data: DisciplinaCreate, db: AsyncSession = Depends(get_db)):
    slug = slugify(data.nome)

    existing = (await db.execute(
        select(Disciplina).where(Disciplina.slug == slug)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(400, "Disciplina já existe")

    disc = Disciplina(
        slug=slug,
        nome=data.nome,
        descricao=data.descricao,
        icon=data.icon,
        icon_color=data.icon_color,
    )
    db.add(disc)
    await db.commit()
    await db.refresh(disc)

    return {
        "id": disc.id,
        "slug": disc.slug,
        "nome": disc.nome,
        "descricao": disc.descricao,
        "icon": disc.icon,
        "icon_color": disc.icon_color,
        "total_aulas": 0,
    }


@app.get("/api/disciplinas/{slug}")
async def get_disciplina(slug: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Disciplina)
        .where(Disciplina.slug == slug)
        .options(selectinload(Disciplina.aulas))
    )
    disc = result.scalar_one_or_none()
    if not disc:
        raise HTTPException(404, "Disciplina não encontrada")

    aulas = sorted(disc.aulas, key=lambda a: a.numero)
    return {
        "id": disc.id,
        "slug": disc.slug,
        "nome": disc.nome,
        "descricao": disc.descricao,
        "icon": disc.icon,
        "icon_color": disc.icon_color,
        "aulas": [
            {
                "id": a.id,
                "numero": a.numero,
                "titulo": a.titulo,
                "status": a.status,
                "modelo_usado": a.modelo_usado,
                "erro_msg": a.erro_msg,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in aulas
        ],
    }


# ─── Aulas ───────────────────────────────────────────────


@app.post("/api/disciplinas/{slug}/aulas")
async def create_aula(
    slug: str,
    file: UploadFile = File(...),
    modelo: str = Form("gemini-3-flash-preview"),
    db: AsyncSession = Depends(get_db),
):
    # Buscar disciplina
    disc = (await db.execute(
        select(Disciplina).where(Disciplina.slug == slug)
    )).scalar_one_or_none()
    if not disc:
        raise HTTPException(404, "Disciplina não encontrada")

    # Calcular próximo número de aula
    result = await db.execute(
        select(func.coalesce(func.max(Aula.numero), -1))
        .where(Aula.disciplina_id == disc.id)
    )
    proximo_numero = result.scalar() + 1

    # Ler PDF
    pdf_bytes = await file.read()
    filename = file.filename or f"aula_{proximo_numero:02d}.pdf"

    # Gerar título a partir do nome do arquivo
    titulo_raw = filename.rsplit(".", 1)[0]  # remover extensão
    titulo = titulo_raw.replace("_", " ").replace("-", " ").strip()
    if not titulo:
        titulo = f"Aula {proximo_numero:02d}"

    # Upload para MinIO
    object_name = f"{slug}/aula_{proximo_numero:02d}_{slugify(titulo)}.pdf"
    minio_path = await asyncio.to_thread(upload_pdf, object_name, pdf_bytes)

    # Criar aula no banco
    aula = Aula(
        disciplina_id=disc.id,
        numero=proximo_numero,
        titulo=titulo,
        pdf_path_minio=minio_path,
        status=StatusProcessamento.PENDENTE.value,
        modelo_usado=modelo,
    )
    db.add(aula)
    await db.commit()
    await db.refresh(aula)

    # Disparar task de processamento
    from worker import processar_aula
    await processar_aula.kiq(aula.id, modelo)

    return {
        "id": aula.id,
        "numero": aula.numero,
        "titulo": aula.titulo,
        "status": aula.status,
        "modelo_usado": modelo,
    }


@app.get("/api/aulas/{aula_id}")
async def get_aula(aula_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Aula)
        .where(Aula.id == aula_id)
        .options(
            selectinload(Aula.blocos),
            selectinload(Aula.flashcards),
            selectinload(Aula.disciplina),
        )
    )
    aula = result.scalar_one_or_none()
    if not aula:
        raise HTTPException(404, "Aula não encontrada")

    blocos = sorted(aula.blocos, key=lambda b: b.paginas)

    return {
        "id": aula.id,
        "numero": aula.numero,
        "titulo": aula.titulo,
        "status": aula.status,
        "modelo_usado": aula.modelo_usado,
        "erro_msg": aula.erro_msg,
        "disciplina": {
            "slug": aula.disciplina.slug,
            "nome": aula.disciplina.nome,
        },
        "blocos": [
            {
                "id": b.id,
                "paginas": b.paginas,
                "resumo_markdown": b.resumo_markdown,
                "formulas": b.formulas_json or [],
            }
            for b in blocos
        ],
        "flashcards": [
            {
                "id": c.id,
                "assunto": c.assunto,
                "frente": c.frente,
                "verso": c.verso,
            }
            for c in aula.flashcards
        ],
        "total_flashcards": len(aula.flashcards),
    }


@app.get("/api/aulas/{aula_id}/status")
async def get_aula_status(aula_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Aula.status, Aula.erro_msg).where(Aula.id == aula_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(404, "Aula não encontrada")
    return {"status": row.status, "erro_msg": row.erro_msg}


@app.get("/api/aulas/{aula_id}/pdf")
async def download_aula_pdf(aula_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Aula.pdf_path_minio).where(Aula.id == aula_id)
    )
    row = result.one_or_none()
    if not row or not row.pdf_path_minio:
        raise HTTPException(404, "PDF não encontrado")

    object_name = row.pdf_path_minio.split("/", 1)[1] if "/" in row.pdf_path_minio else row.pdf_path_minio
    try:
        url = await asyncio.to_thread(get_presigned_url, object_name)
        # Trocar host minio por localhost para acesso externo
        url = url.replace("minio:9000", "localhost:9000")
        return RedirectResponse(url)
    except Exception as e:
        raise HTTPException(500, f"Erro ao gerar URL do PDF: {e}")


# ─── Jobs (Monitoramento) ────────────────────────────────


@app.get("/api/jobs")
async def list_jobs(
    db: AsyncSession = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Lista todas as aulas com processamento (ativo, concluído, erro). (admin)"""
    result = await db.execute(
        select(Aula, Disciplina.nome.label("disciplina_nome"))
        .join(Disciplina)
        .order_by(Aula.updated_at.desc())
    )
    rows = result.all()
    return [
        {
            "id": aula.id,
            "disciplina": disc_nome,
            "numero": aula.numero,
            "titulo": aula.titulo,
            "status": aula.status,
            "modelo_usado": aula.modelo_usado,
            "erro_msg": aula.erro_msg,
            "created_at": aula.created_at.isoformat() if aula.created_at else None,
            "updated_at": aula.updated_at.isoformat() if aula.updated_at else None,
        }
        for aula, disc_nome in rows
    ]


# ─── Batch Jobs Gemini (cancel/list) ─────────────────────


@app.get("/api/batch-jobs")
async def list_gemini_batch_jobs(_admin=Depends(require_admin)):
    """Lista batch jobs recentes na API do Gemini. (admin)"""
    from gemini_service import list_batch_jobs
    try:
        jobs = await asyncio.to_thread(list_batch_jobs)
        return jobs
    except Exception as e:
        raise HTTPException(500, f"Erro ao listar batch jobs: {e}")


@app.post("/api/batch-jobs/{job_name:path}/cancel")
async def cancel_gemini_batch_job(job_name: str, _admin=Depends(require_admin)):
    """Cancela um batch job em andamento no Gemini. (admin)"""
    from gemini_service import cancel_batch_job
    result = await asyncio.to_thread(cancel_batch_job, job_name)
    if result["status"] == "error":
        raise HTTPException(400, result["detail"])
    return result


@app.delete("/api/batch-jobs/{job_name:path}")
async def delete_gemini_batch_job(job_name: str, _admin=Depends(require_admin)):
    """Deleta um batch job do Gemini. (admin)"""
    from gemini_service import delete_batch_job
    result = await asyncio.to_thread(delete_batch_job, job_name)
    if result["status"] == "error":
        raise HTTPException(400, result["detail"])
    return result


# ─── Chat ────────────────────────────────────────────────


class ChatRequest(BaseModel):
    mensagem: str
    modelo: str = "gemini-3-flash-preview"
    historico: list[dict] = []


@app.post("/api/aulas/{aula_id}/chat")
async def chat_aula(aula_id: int, data: ChatRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Aula.texto_completo).where(Aula.id == aula_id)
    )
    row = result.one_or_none()
    if not row:
        raise HTTPException(404, "Aula não encontrada")

    texto = row.texto_completo
    if not texto:
        raise HTTPException(400, "PDF ainda não foi processado. Aguarde o processamento.")

    from gemini_service import chat_stream

    async def event_generator():
        try:
            async for chunk in chat_stream(
                texto_aula=texto,
                mensagem=data.mensagem,
                historico=data.historico,
                modelo=data.modelo,
            ):
                yield {"data": chunk}
        except Exception as e:
            yield {"event": "error", "data": str(e)}

    return EventSourceResponse(event_generator())


# ─── Concorrência / Concursos ────────────────────────────


def _db_to_engine(c: Candidato) -> ce.Candidato:
    return ce.Candidato(
        inscricao=c.inscricao,
        cargo=c.cargo,
        polo=c.polo,
        macropolo=c.macropolo,
        pontos=c.pontos,
        discursiva=c.discursiva or 0.0,
        tot_esp=c.tot_esp or 0.0,
        tot_bas=c.tot_bas or 0.0,
        l_port=c.l_port or 0.0,
        l_ing=c.l_ing or 0.0,
        nascimento=ce._to_date(c.nascimento or ""),
        situacao=c.situacao or "",
        pos_ac=c.pos_ac,
        pos_pcd=c.pos_pcd,
        pos_pn=c.pos_pn,
        pos_pi=c.pos_pi,
        pos_pq=c.pos_pq,
    )


@app.post("/api/concursos/import")
async def import_concurso(
    file: UploadFile = File(...),
    nome: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    raw = await file.read()
    try:
        texto = raw.decode("utf-8")
    except UnicodeDecodeError:
        texto = raw.decode("latin-1", errors="replace")

    try:
        cands = ce.parse_csv(texto)
    except ValueError as e:
        raise HTTPException(400, str(e))

    if not cands:
        raise HTTPException(400, "CSV sem candidatos válidos.")

    nome_final = nome.strip() or (file.filename or "Concurso").rsplit(".", 1)[0]
    concurso = Concurso(
        nome=nome_final,
        arquivo_nome=file.filename,
        total_candidatos=len(cands),
    )
    db.add(concurso)
    await db.flush()

    db.add_all([
        Candidato(
            concurso_id=concurso.id,
            inscricao=c.inscricao,
            cargo=c.cargo,
            polo=c.polo,
            macropolo=c.macropolo,
            nascimento=c.nascimento.strftime("%d/%m/%Y") if c.nascimento else None,
            pontos=c.pontos,
            discursiva=c.discursiva,
            tot_esp=c.tot_esp,
            tot_bas=c.tot_bas,
            l_port=c.l_port,
            l_ing=c.l_ing,
            situacao=c.situacao,
            pos_ac=c.pos_ac,
            pos_pcd=c.pos_pcd,
            pos_pn=c.pos_pn,
            pos_pi=c.pos_pi,
            pos_pq=c.pos_pq,
        )
        for c in cands
    ])
    await db.commit()

    return {
        "id": concurso.id,
        "nome": concurso.nome,
        "total_candidatos": len(cands),
    }


@app.get("/api/concursos")
async def list_concursos(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Concurso).order_by(Concurso.created_at.desc())
    )
    return [
        {
            "id": c.id,
            "nome": c.nome,
            "arquivo_nome": c.arquivo_nome,
            "total_candidatos": c.total_candidatos,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in result.scalars().all()
    ]


@app.delete("/api/concursos/{concurso_id}")
async def delete_concurso(concurso_id: int, db: AsyncSession = Depends(get_db)):
    c = (await db.execute(
        select(Concurso).where(Concurso.id == concurso_id)
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Concurso não encontrado")
    await db.delete(c)
    await db.commit()
    return {"ok": True}


@app.get("/api/concursos/{concurso_id}")
async def get_concurso(concurso_id: int, db: AsyncSession = Depends(get_db)):
    c = (await db.execute(
        select(Concurso).where(Concurso.id == concurso_id)
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Concurso não encontrado")

    rows = (await db.execute(
        select(Candidato).where(Candidato.concurso_id == concurso_id)
    )).scalars().all()

    cargos = sorted({r.cargo for r in rows})
    macropolos = sorted({r.macropolo for r in rows})
    polos: dict[str, int] = {}
    for r in rows:
        polos[r.polo] = polos.get(r.polo, 0) + 1

    return {
        "id": c.id,
        "nome": c.nome,
        "arquivo_nome": c.arquivo_nome,
        "total_candidatos": len(rows),
        "cargos": cargos,
        "macropolos": macropolos,
        "polos": sorted(
            [{"uf": k, "total": v} for k, v in polos.items()],
            key=lambda x: x["uf"],
        ),
        "cotas": {
            "PCD": sum(1 for r in rows if r.pos_pcd is not None),
            "PN": sum(1 for r in rows if r.pos_pn is not None),
            "PI": sum(1 for r in rows if r.pos_pi is not None),
            "PQ": sum(1 for r in rows if r.pos_pq is not None),
        },
    }


class SimularRequest(BaseModel):
    cargo: Optional[str] = None
    abrangencia: str = "GERAL"  # GERAL | MACROPOLO | POLO
    recorte: Optional[str] = None
    total_vagas: int = 10
    fator_cr: float = 3.0
    pct_pn: float = 0.25
    pct_pi: float = 0.03
    pct_pq: float = 0.02
    pct_pcd: float = 0.05
    arred_racial: str = "MEIO"
    arred_pcd: str = "CIMA"
    limiar_racial: int = 2
    criterio: str = "PONTOS"  # PONTOS | ESPECIFICO (padrão Petrobras)
    max_esp: float = 40.0
    limite_lista: int = 250
    minha_pontuacao: Optional[float] = None
    minhas_categorias: list[str] = []


@app.post("/api/concursos/{concurso_id}/simular")
async def simular_concurso(
    concurso_id: int,
    req: SimularRequest,
    db: AsyncSession = Depends(get_db),
):
    c = (await db.execute(
        select(Concurso).where(Concurso.id == concurso_id)
    )).scalar_one_or_none()
    if not c:
        raise HTTPException(404, "Concurso não encontrado")

    q = select(Candidato).where(Candidato.concurso_id == concurso_id)
    if req.cargo:
        q = q.where(Candidato.cargo == req.cargo)
    if req.abrangencia == "MACROPOLO" and req.recorte:
        q = q.where(Candidato.macropolo == req.recorte)
    elif req.abrangencia == "POLO" and req.recorte:
        q = q.where(Candidato.polo == req.recorte)

    rows = (await db.execute(q)).scalars().all()
    if not rows:
        raise HTTPException(400, "Nenhum candidato neste recorte.")

    cands = [_db_to_engine(r) for r in rows]
    cfg = ce.ConfigCotas(
        total_vagas=req.total_vagas,
        fator_cr=req.fator_cr,
        pct_pn=req.pct_pn,
        pct_pi=req.pct_pi,
        pct_pq=req.pct_pq,
        pct_pcd=req.pct_pcd,
        arred_racial=req.arred_racial,
        arred_pcd=req.arred_pcd,
        limiar_racial=req.limiar_racial,
        criterio=req.criterio,
        max_esp=req.max_esp,
    )

    if req.minha_pontuacao is not None:
        cats = [c for c in req.minhas_categorias if c in ("PN", "PI", "PQ", "PCD")]
        res = ce.simular_pessoal(
            cands, cfg, req.minha_pontuacao, cats
        )
        full = res["contexto"]
        pessoal = res["simulacao"]
    else:
        full = ce.simular(cands, cfg)
        pessoal = None

    classif = full.pop("classificacao")
    lim = max(20, min(req.limite_lista, 1000))

    return {
        **full,
        "recorte": {
            "cargo": req.cargo,
            "abrangencia": req.abrangencia,
            "valor": req.recorte,
            "total_no_recorte": len(rows),
        },
        "pessoal": pessoal,
        "classificacao": classif[:lim],
        "classificacao_total": len(classif),
    }
