import os
import json
import tempfile
import time
import base64
import pathlib
from typing import AsyncIterator

from google import genai
from google.genai import types


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")

# Limite para inline requests (doc: < 20MB)
INLINE_MAX_BYTES = 20 * 1024 * 1024  # 20MB

PROMPT_BATCH = """Atue como um Professor Engenheiro Sênior.
Analise as páginas do PDF em anexo com máximo rigor acadêmico.

Você DEVE executar as 3 tarefas abaixo e retornar o resultado em JSON válido.

TAREFA 1 — RESUMO DIDÁTICO (campo: resumo_markdown)
- Escreva um resumo explicativo em Markdown.
- Use **negrito** em termos-chave e conceitos fundamentais.
- Estruture com títulos ### quando houver múltiplos tópicos.
- Explique fórmulas em linguagem acessível.

TAREFA 2 — FÓRMULAS MATEMÁTICAS (campo: formulas)
- Extraia TODAS as equações/fórmulas encontradas.
- Escreva cada equação em LaTeX compatível com KaTeX.
- Use $$ para equações block e $ para inline.
- Para cada fórmula informe: latex (a equação), nome (nome da fórmula), variaveis (explicação das variáveis).
- Se não houver fórmulas, retorne lista vazia [].

TAREFA 3 — FLASHCARDS (campo: flashcards)
- Crie 5 a 10 flashcards de recuperação ativa.
- frente: pergunta direta e desafiadora (sem tags XML).
- verso: resposta estruturada usando Markdown. Pode usar as tags XML:
  * <atencao>Titulo: texto de alerta</atencao> para pegadinhas
  * <destaque>termo</destaque> para termos-chave
  * <resumo>fórmula ou definição</resumo> para fórmulas principais
- topico: assunto específico do card.

FORMATO DE SAÍDA — JSON estrito:
{
  "resumo_markdown": "string com markdown",
  "formulas": [
    {"latex": "$$...$$", "nome": "string", "variaveis": "string"}
  ],
  "flashcards": [
    {"frente": "string", "verso": "string", "topico": "string"}
  ]
}

Responda APENAS com o JSON. Sem texto antes ou depois."""


CHAT_SYSTEM_PROMPT = """Você é um tutor especialista que conhece profundamente o conteúdo desta aula.
Responda de forma didática, usando Markdown para formatação.
Use LaTeX ($...$ inline, $$...$$ block) para fórmulas matemáticas.
Quando relevante, use as tags XML:
- <atencao>Titulo: texto</atencao> para alertas
- <destaque>termo</destaque> para termos-chave
- <resumo>conteúdo</resumo> para resumos/fórmulas importantes

O conteúdo completo da aula está abaixo para referência:

---
{texto_aula}
---"""


def _get_client() -> genai.Client:
    return genai.Client(api_key=GEMINI_API_KEY)


def _build_inline_request(paginas_label: str, pdf_bytes: bytes) -> dict:
    """Monta um request inline para a Batch API (formato da doc)."""
    return {
        "contents": [
            {
                "parts": [
                    {
                        "inline_data": {
                            "mime_type": "application/pdf",
                            "data": base64.b64encode(pdf_bytes).decode(),
                        }
                    },
                    {"text": PROMPT_BATCH},
                ],
                "role": "user",
            }
        ],
        "config": {
            "temperature": 1.0,
            "response_mime_type": "application/json",
        },
    }


def _build_file_request(index: int, paginas_label: str, pdf_bytes: bytes) -> dict:
    """Monta um request JSONL para a Batch API (formato com key/request)."""
    return {
        "key": f"chunk-{index}-{paginas_label}",
        "request": _build_inline_request(paginas_label, pdf_bytes),
    }


def _estimate_inline_size(pdf_chunks: list[tuple[str, bytes]]) -> int:
    """Estima tamanho total dos requests inline em bytes (base64 ≈ 4/3 do original)."""
    total = 0
    for _, pdf_bytes in pdf_chunks:
        # base64 expande ~33% + overhead JSON do prompt/config (~2KB)
        total += int(len(pdf_bytes) * 4 / 3) + 2048
    return total


def _parse_result_text(text: str) -> dict:
    """Parseia texto de resposta do Gemini para dict estruturado."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {
            "resumo_markdown": text,
            "formulas": [],
            "flashcards": [],
        }


def _error_result(msg: str) -> dict:
    """Cria resultado de erro padronizado."""
    return {
        "resumo_markdown": f"Erro no processamento: {msg}",
        "formulas": [],
        "flashcards": [],
    }


def _poll_batch_job(client: genai.Client, job_name: str):
    """
    Poll batch job com backoff progressivo conforme doc oficial.
    Doc recomenda sleep(30). Backoff: 30s → 45s → 67s → ... → max 5min.
    """
    completed_states = {
        "JOB_STATE_SUCCEEDED",
        "JOB_STATE_FAILED",
        "JOB_STATE_CANCELLED",
        "JOB_STATE_EXPIRED",
    }
    poll_interval = 30
    max_interval = 300

    job = client.batches.get(name=job_name)
    while job.state.name not in completed_states:
        print(f"[Batch] Estado: {job.state.name} | Próximo check em {poll_interval:.0f}s")
        time.sleep(poll_interval)
        poll_interval = min(poll_interval * 1.5, max_interval)
        job = client.batches.get(name=job_name)

    print(f"[Batch] Job finalizado: {job.state.name}")
    return job


def _extract_results_from_job(client: genai.Client, job) -> list[dict]:
    """
    Extrai resultados de um batch job finalizado.
    Lida com resultados em arquivo (JSONL) e inline.
    """
    results = []

    if job.dest and job.dest.file_name:
        # Resultados em arquivo JSONL
        content_buffer = client.files.download(file=job.dest.file_name)
        content = content_buffer.decode("utf-8")
        for line in content.strip().split("\n"):
            if not line:
                continue
            parsed = json.loads(line)
            if parsed.get("response"):
                text = ""
                for part in parsed["response"]["candidates"][0]["content"]["parts"]:
                    if part.get("text"):
                        text += part["text"]
                results.append(_parse_result_text(text))
            elif parsed.get("error"):
                results.append(_error_result(str(parsed["error"])))

    elif job.dest and hasattr(job.dest, "inlined_responses") and job.dest.inlined_responses:
        # Resultados inline
        for resp in job.dest.inlined_responses:
            if resp.response:
                text = resp.response.text or ""
                results.append(_parse_result_text(text))
            elif hasattr(resp, "error") and resp.error:
                results.append(_error_result(str(resp.error)))

    return results


def process_pdf_chunks(
    pdf_chunks: list[tuple[str, bytes]],
    modelo: str = "gemini-3-flash-preview",
) -> list[dict]:
    """
    Processa chunks de PDF via Gemini Batch API.
    Escolhe dinamicamente entre inline requests e JSONL baseado no tamanho.

    - Inline (<20MB): envia direto, sem criar arquivo. Mais rápido.
    - JSONL (>=20MB): cria arquivo, faz upload via Files API. Para PDFs grandes.

    Retorna lista de dicts com resumo, formulas e flashcards.
    """
    client = _get_client()
    estimated_size = _estimate_inline_size(pdf_chunks)
    use_inline = estimated_size < INLINE_MAX_BYTES

    print(f"[Batch] {len(pdf_chunks)} chunks | ~{estimated_size / 1024 / 1024:.1f}MB | Modo: {'inline' if use_inline else 'JSONL file'}")

    if use_inline:
        return _process_inline(client, pdf_chunks, modelo)
    else:
        return _process_jsonl_file(client, pdf_chunks, modelo)


def _process_inline(
    client: genai.Client,
    pdf_chunks: list[tuple[str, bytes]],
    modelo: str,
) -> list[dict]:
    """Processa via inline requests (< 20MB). Sem upload de arquivo."""
    inline_requests = [
        _build_inline_request(label, pdf_bytes)
        for label, pdf_bytes in pdf_chunks
    ]

    batch_job = client.batches.create(
        model=modelo,
        src=inline_requests,
        config={"display_name": f"studia-inline-{time.time():.0f}"},
    )

    job = _poll_batch_job(client, batch_job.name)

    if job.state.name != "JOB_STATE_SUCCEEDED":
        error_info = getattr(job, "error", job.state.name)
        raise RuntimeError(f"Batch job falhou: {error_info}")

    # Checar falhas parciais via batchStats
    _check_batch_stats(job, len(pdf_chunks))

    return _extract_results_from_job(client, job)


def _process_jsonl_file(
    client: genai.Client,
    pdf_chunks: list[tuple[str, bytes]],
    modelo: str,
) -> list[dict]:
    """Processa via JSONL file upload (>= 20MB). Para PDFs grandes."""
    jsonl_path = None
    try:
        # Criar JSONL e fazer upload
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".jsonl", delete=False
        ) as f:
            for i, (label, pdf_bytes) in enumerate(pdf_chunks):
                req = _build_file_request(i, label, pdf_bytes)
                f.write(json.dumps(req) + "\n")
            jsonl_path = f.name

        uploaded_file = client.files.upload(
            file=jsonl_path,
            config=types.UploadFileConfig(mime_type="jsonl"),
        )

        batch_job = client.batches.create(
            model=modelo,
            src=uploaded_file.name,
            config={"display_name": f"studia-file-{time.time():.0f}"},
        )

        job = _poll_batch_job(client, batch_job.name)

        if job.state.name != "JOB_STATE_SUCCEEDED":
            error_info = getattr(job, "error", job.state.name)
            raise RuntimeError(f"Batch job falhou: {error_info}")

        # Checar falhas parciais via batchStats
        _check_batch_stats(job, len(pdf_chunks))

        return _extract_results_from_job(client, job)

    finally:
        if jsonl_path:
            pathlib.Path(jsonl_path).unlink(missing_ok=True)


def _check_batch_stats(job, expected_count: int):
    """
    Verifica batchStats para falhas parciais.
    Doc: mesmo com JOB_STATE_SUCCEEDED, requests individuais podem falhar.
    """
    stats = getattr(job, "batch_stats", None)
    if not stats:
        return

    failed = getattr(stats, "failed_request_count", 0) or 0
    total = getattr(stats, "total_request_count", expected_count) or expected_count
    succeeded = getattr(stats, "succeeded_request_count", 0) or 0

    print(f"[Batch] Stats: {succeeded}/{total} OK, {failed} falhas")

    if failed > 0:
        print(f"[Batch] ATENÇÃO: {failed} de {total} requests falharam individualmente")


def cancel_batch_job(job_name: str) -> dict:
    """Cancela um batch job em andamento."""
    client = _get_client()
    try:
        client.batches.cancel(name=job_name)
        job = client.batches.get(name=job_name)
        return {"status": "cancelled", "state": job.state.name}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def delete_batch_job(job_name: str) -> dict:
    """Deleta um batch job (remove da lista)."""
    client = _get_client()
    try:
        client.batches.delete(name=job_name)
        return {"status": "deleted"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


def list_batch_jobs() -> list[dict]:
    """Lista batch jobs recentes na API do Gemini."""
    client = _get_client()
    jobs = []
    for job in client.batches.list():
        jobs.append({
            "name": job.name,
            "display_name": getattr(job, "display_name", None),
            "state": job.state.name,
            "create_time": str(getattr(job, "create_time", "")),
        })
    return jobs


def process_pdf_chunk_sync(
    pdf_bytes: bytes,
    modelo: str = "gemini-3-flash-preview",
) -> dict:
    """
    Processa um chunk de PDF de forma síncrona (fallback quando batch é muito pequeno).
    """
    client = _get_client()
    response = client.models.generate_content(
        model=modelo,
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            PROMPT_BATCH,
        ],
        config=types.GenerateContentConfig(
            temperature=1.0,
            response_mime_type="application/json",
        ),
    )
    return _parse_result_text(response.text)


async def chat_stream(
    texto_aula: str,
    mensagem: str,
    historico: list[dict],
    modelo: str = "gemini-3-flash-preview",
) -> AsyncIterator[str]:
    """
    Chat com streaming usando contexto completo do PDF.
    historico: [{"role": "user"|"model", "text": "..."}]
    """
    client = _get_client()
    system_prompt = CHAT_SYSTEM_PROMPT.format(texto_aula=texto_aula)

    # Montar contents com histórico
    contents = []
    for msg in historico:
        contents.append(
            types.Content(
                role=msg["role"],
                parts=[types.Part.from_text(text=msg["text"])],
            )
        )
    contents.append(
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=mensagem)],
        )
    )

    response = client.models.generate_content_stream(
        model=modelo,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.7,
        ),
    )

    for chunk in response:
        if chunk.text:
            yield chunk.text
