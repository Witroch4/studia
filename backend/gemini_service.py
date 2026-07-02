import os
import json
import tempfile
import time
import base64
import pathlib
from dataclasses import dataclass
from typing import AsyncIterator

from google import genai
from google.genai import types


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
LITELLM_BASE_URL_DEFAULT = "http://platform-litellm:4000"


@dataclass(frozen=True)
class ClientConfig:
    api_key: str
    base_url: str | None  # None = Gemini direto; senão = passthrough /gemini do proxy
    via_proxy: bool


def _client_config() -> ClientConfig:
    """Decide o transporte da IA: LiteLLM passthrough (consolidado) vs Gemini direto.

    Em prod `LITELLM_API_KEY` está setado → roteia TUDO (chat + Batch) pelo proxy
    interno (`<base>/gemini`), por rede docker. Sem ela (dev sem proxy / contingência)
    cai no Gemini direto com `GEMINI_API_KEY` — comportamento original preservado.
    """
    litellm_key = os.getenv("LITELLM_API_KEY", "")
    if litellm_key:
        base = os.getenv("LITELLM_BASE_URL", LITELLM_BASE_URL_DEFAULT).rstrip("/")
        return ClientConfig(api_key=litellm_key, base_url=f"{base}/gemini", via_proxy=True)
    return ClientConfig(api_key=os.getenv("GEMINI_API_KEY", ""), base_url=None, via_proxy=False)

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
    cfg = _client_config()
    if cfg.base_url:
        return genai.Client(
            api_key=cfg.api_key,
            http_options=types.HttpOptions(base_url=cfg.base_url),
        )
    return genai.Client(api_key=cfg.api_key)


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


def gerar_temas_discursivas(materias: list[str], n: int = 18) -> list[str]:
    """Sugere `n` temas de discursiva (caso prático) a partir das matérias do caderno.

    Retorna lista de strings. Levanta em caso de falha de IA — o chamador trata.
    """
    materias_txt = ", ".join(materias) or "tema geral do concurso"
    prompt = (
        "Você é um examinador de concursos. Gere "
        f"{n} temas de questão DISCURSIVA (caso prático, até 20 linhas) "
        f"para um candidato que estuda estas matérias: {materias_txt}. "
        "Cada tema deve ser específico e cobrir um aspecto diferente. "
        'Responda APENAS um JSON no formato {"temas": ["...", "..."]}.'
    )
    client = _get_client()
    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[prompt],
        config=types.GenerateContentConfig(
            temperature=1.0, response_mime_type="application/json"
        ),
    )
    data = json.loads(response.text)
    temas = data.get("temas", []) if isinstance(data, dict) else []
    return [str(t).strip() for t in temas if str(t).strip()][:n]


# ─── Mapa da Aprovação ─────────────────────────────────────

PROMPT_EDITAL = """Você é um analista de concursos públicos. Leia o EDITAL em PDF anexo e extraia os dados abaixo em JSON VÁLIDO.

REGRAS:
- NUNCA invente dados: campo ausente no edital fica null (listas ficam vazias).
- Datas SEMPRE em ISO "YYYY-MM-DD". Períodos usam data_inicio e data_fim.
- Copie nomes de cargos e matérias EXATAMENTE como escritos no edital.
- conteudo_programatico: TODAS as matérias do cargo com a lista COMPLETA de assuntos (cada item do programa é um assunto). Não resuma nem agrupe.
- eventos: todos os prazos do cronograma do edital. tipo ∈ {inscricao, isencao, prova, recurso, resultado, homologacao, outro}.
- vagas/salario/taxa_inscricao: strings livres como estão no edital (ex.: "2 + CR", "R$ 6.500,00").

FORMATO:
{"concurso": {"orgao": null, "banca": null, "taxa_inscricao": null, "data_prova": null},
 "eventos": [{"titulo": "", "data_inicio": null, "data_fim": null, "tipo": "outro"}],
 "cargos": [{"nome": "", "escolaridade": null, "vagas": null, "salario": null,
             "requisitos": null, "jornada": null,
             "conteudo_programatico": [{"materia": "", "assuntos": [""]}],
             "etapas": [{"nome": "", "carater": null}],
             "distribuicao_questoes": [{"materia": "", "quantidade": null, "peso": null}]}]}
Responda APENAS o JSON."""


def extrair_edital_estruturado(pdf_bytes: bytes, modelo: str) -> dict:
    """Extrai a estrutura do edital (cargos/matérias/eventos) em JSON.

    Via proxy LiteLLM (mesmo _get_client de sempre) — NUNCA Batch: o usuário
    espera na tela. Levanta em falha (chamador marca status=erro).
    """
    if len(pdf_bytes) > INLINE_MAX_BYTES:
        raise ValueError("edital maior que 20MB — não suportado")
    client = _get_client()
    response = client.models.generate_content(
        model=modelo,
        contents=[
            types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf"),
            PROMPT_EDITAL,
        ],
        config=types.GenerateContentConfig(
            temperature=0.2, response_mime_type="application/json"
        ),
    )
    data = json.loads(response.text)
    if not isinstance(data, dict):
        raise ValueError("IA não devolveu um objeto JSON")
    return data


def mapear_materias(
    materias_edital: list[str], materias_banco: list[str], modelo: str
) -> dict[str, str | None]:
    """De-para matéria do edital → matéria do nosso banco (ou None sem correspondência).

    Só devolve valores que existem EXATAMENTE em `materias_banco` — resposta
    fora da lista vira None (a IA não pode inventar matéria).
    """
    if not materias_edital:
        return {}
    if not materias_banco:
        return {m: None for m in materias_edital}
    prompt = (
        "Faça o de-para entre matérias de um edital de concurso e as matérias "
        "de um banco de questões. Para cada matéria do edital, escolha a matéria "
        "do banco de MESMO conteúdo, ou null se não houver equivalente claro. "
        "Use SOMENTE nomes exatos da lista do banco.\n"
        f"MATÉRIAS DO EDITAL: {json.dumps(materias_edital, ensure_ascii=False)}\n"
        f"MATÉRIAS DO BANCO: {json.dumps(materias_banco, ensure_ascii=False)}\n"
        'Responda APENAS JSON: {"mapeamento": {"<materia do edital>": "<materia do banco ou null>"}}'
    )
    client = _get_client()
    response = client.models.generate_content(
        model=modelo,
        contents=[prompt],
        config=types.GenerateContentConfig(
            temperature=0.0, response_mime_type="application/json"
        ),
    )
    data = json.loads(response.text)
    bruto = data.get("mapeamento", {}) if isinstance(data, dict) else {}
    validos = set(materias_banco)
    return {
        m: (bruto.get(m) if isinstance(bruto.get(m), str) and bruto.get(m) in validos else None)
        for m in materias_edital
    }
