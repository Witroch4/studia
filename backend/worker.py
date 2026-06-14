import io
import json
import asyncio
import os
import re
import traceback
from dataclasses import dataclass

import httpx
import pymupdf
from nats.js.api import ConsumerConfig, StreamConfig
from taskiq_nats import PullBasedJetStreamBroker
from taskiq_redis import RedisAsyncResultBackend

from database import async_session
from models import Aula, BlocoConteudo, Flashcard, Deck, StatusProcessamento
from minio_client import download_pdf
from gemini_service import process_pdf_chunks

SCRAPER_URL = os.getenv("SCRAPER_URL", "http://scraper:8090")


@dataclass(frozen=True)
class BrokerConfig:
    nats_servers: list[str]
    result_redis_url: str
    stream: str
    subject: str
    durable: str
    pull_batch: int
    max_ack_pending: int
    ack_wait_seconds: int
    max_deliver: int


def load_broker_config() -> BrokerConfig:
    """Config do broker NATS do worker do backend, 100% via env (defaults seguros)."""
    servers = os.getenv("NATS_SERVERS", "nats://nats:4222")
    return BrokerConfig(
        nats_servers=[s.strip() for s in servers.split(",") if s.strip()],
        result_redis_url=os.getenv("TASKIQ_RESULT_REDIS_URL", "redis://redis:6379/2"),
        stream=os.getenv("TASKIQ_STUDIA_BACKEND_STREAM", "TASKIQ_STUDIA_BACKEND"),
        subject=os.getenv("TASKIQ_STUDIA_BACKEND_SUBJECT", "taskiq.studia.backend"),
        durable=os.getenv("TASKIQ_STUDIA_BACKEND_DURABLE", "studia-backend-workers"),
        pull_batch=int(os.getenv("TASKIQ_STUDIA_BACKEND_PULL_BATCH", "1")),
        max_ack_pending=int(os.getenv("TASKIQ_STUDIA_BACKEND_MAX_ACK_PENDING", "1")),
        ack_wait_seconds=int(os.getenv("TASKIQ_STUDIA_BACKEND_ACK_WAIT_SECONDS", "3600")),
        max_deliver=int(os.getenv("TASKIQ_STUDIA_BACKEND_MAX_DELIVER", "3")),
    )


def build_broker(cfg: BrokerConfig | None = None) -> PullBasedJetStreamBroker:
    """Constrói o broker NATS JetStream (não conecta — conexão é no startup())."""
    cfg = cfg or load_broker_config()
    return PullBasedJetStreamBroker(
        servers=cfg.nats_servers,
        subject=cfg.subject,
        stream_name=cfg.stream,
        durable=cfg.durable,
        pull_consume_batch=cfg.pull_batch,
        stream_config=StreamConfig(name=cfg.stream, subjects=[cfg.subject]),
        consumer_config=ConsumerConfig(
            durable_name=cfg.durable,
            filter_subject=cfg.subject,
            ack_wait=cfg.ack_wait_seconds,
            max_deliver=cfg.max_deliver,
            max_ack_pending=cfg.max_ack_pending,
        ),
    ).with_result_backend(RedisAsyncResultBackend(redis_url=cfg.result_redis_url))


broker = build_broker()


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


def split_pdf_chunks(pdf_bytes: bytes, pages_per_chunk: int = 10) -> list[tuple[str, bytes]]:
    """Divide PDF em chunks de N páginas. Retorna [(label, pdf_bytes)]."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    total = len(doc)
    chunks = []

    for start in range(0, total, pages_per_chunk):
        end = min(start + pages_per_chunk, total)
        label = f"{start + 1}-{end}"

        new_doc = pymupdf.open()
        new_doc.insert_pdf(doc, from_page=start, to_page=end - 1)

        buf = io.BytesIO()
        new_doc.save(buf)
        chunks.append((label, buf.getvalue()))
        new_doc.close()

    doc.close()
    return chunks


def extract_full_text(pdf_bytes: bytes) -> str:
    """Extrai texto completo do PDF para usar no chat."""
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    texts = []
    for page in doc:
        texts.append(page.get_text())
    doc.close()
    return "\n\n".join(texts)


@broker.task
async def processar_aula(aula_id: int, modelo: str = "gemini-3-flash-preview"):
    """Task principal: processa PDF de uma aula com Gemini."""
    async with async_session() as db:
        try:
            # 1. Buscar aula
            from sqlalchemy import select
            result = await db.execute(select(Aula).where(Aula.id == aula_id))
            aula = result.scalar_one_or_none()
            if not aula:
                return {"error": f"Aula {aula_id} não encontrada"}

            # Idempotência: se já concluída, não reprocessa (evita duplicar em
            # caso de redelivery do JetStream após ack_wait).
            if aula.status == StatusProcessamento.CONCLUIDO.value:
                return {"status": "skip", "motivo": "aula já concluída", "aula_id": aula_id}

            # 2. Atualizar status
            aula.status = StatusProcessamento.PROCESSANDO.value
            aula.modelo_usado = modelo
            await db.commit()

            # 3. Baixar PDF do MinIO
            object_name = aula.pdf_path_minio.split("/", 1)[1] if "/" in aula.pdf_path_minio else aula.pdf_path_minio
            pdf_bytes = await asyncio.to_thread(download_pdf, object_name)

            # 4. Extrair texto completo para chat
            texto_completo = await asyncio.to_thread(extract_full_text, pdf_bytes)
            aula.texto_completo = texto_completo
            await db.commit()

            # 5. Dividir em chunks de 10 páginas
            chunks = await asyncio.to_thread(split_pdf_chunks, pdf_bytes, 10)

            # 6. Processar com Gemini — sempre Batch API (50% desconto)
            # Escolhe automaticamente inline vs JSONL baseado no tamanho
            results = await asyncio.to_thread(
                process_pdf_chunks, chunks, modelo
            )

            # 7. Salvar resultados no banco
            # Buscar/criar deck para os flashcards desta aula
            from sqlalchemy import select as sel
            disc_result = await db.execute(
                sel(Aula).where(Aula.id == aula_id)
            )
            aula_fresh = disc_result.scalar_one()

            # Obter disciplina para nome do deck
            from models import Disciplina
            disc = await db.execute(
                sel(Disciplina).where(Disciplina.id == aula_fresh.disciplina_id)
            )
            disciplina = disc.scalar_one()
            deck_slug = slugify(disciplina.nome)

            deck_result = await db.execute(sel(Deck).where(Deck.slug == deck_slug))
            deck = deck_result.scalar_one_or_none()
            if not deck:
                deck = Deck(slug=deck_slug, nome=disciplina.nome)
                db.add(deck)
                await db.flush()

            for i, (label, _) in enumerate(chunks):
                if i >= len(results):
                    break
                data = results[i]

                # Criar bloco de conteúdo
                bloco = BlocoConteudo(
                    aula_id=aula_id,
                    paginas=label,
                    resumo_markdown=data.get("resumo_markdown", ""),
                    formulas_json=data.get("formulas", []),
                )
                db.add(bloco)

                # Criar flashcards
                for card_data in data.get("flashcards", []):
                    card = Flashcard(
                        deck_id=deck.id,
                        aula_id=aula_id,
                        assunto=card_data.get("topico", "Geral"),
                        frente=card_data.get("frente", ""),
                        verso=card_data.get("verso", ""),
                    )
                    db.add(card)

            # 8. Marcar como concluído
            aula.status = StatusProcessamento.CONCLUIDO.value
            aula.erro_msg = None
            await db.commit()

            return {"status": "ok", "chunks": len(chunks), "results": len(results)}

        except Exception as e:
            # Marcar como erro
            try:
                aula.status = StatusProcessamento.ERRO.value
                aula.erro_msg = str(e)[:2000]
                await db.commit()
            except Exception:
                pass
            traceback.print_exc()
            return {"error": str(e)}


# ─── witdev-tec-master: scrape via service HTTP ─────────────────


@broker.task
async def scrape_caderno_tc(caderno_id: int) -> dict:
    """Dispara scrape de um caderno TecConcursos via service `scraper`.

    O service é stateful (Playwright + storage_state) e roda em
    container próprio. Worker apenas orquestra: HTTP fire-and-forward.
    """
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=None, write=10, pool=30)) as c:
        r = await c.post(
            f"{SCRAPER_URL}/run/caderno",
            json={"caderno_id": caderno_id},
        )
        r.raise_for_status()
        return r.json()


@broker.task
async def scrape_questoes_tc(ids: list[int], caderno_id: int | None = None) -> dict:
    """Scrape de IDs específicos (útil para retries seletivos)."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(connect=10, read=None, write=10, pool=30)) as c:
        r = await c.post(
            f"{SCRAPER_URL}/run/questoes",
            json={"ids": ids, "caderno_id": caderno_id},
        )
        r.raise_for_status()
        return r.json()
