"""Comentários de uma questão no TC: fórum dos alunos (💬) e comentário do
professor (🎓). Shapes em discovery/comentarios_contract.md.
"""
from __future__ import annotations
import asyncio
from typing import Any
from bs4 import BeautifulSoup
from app.client import TcClient
from app.textmd import html_to_md
from app.observability import get_logger

log = get_logger(__name__)

DELAY_S = 1.2
MAX_PAGINAS = 40  # trava de segurança (50/pág); questões reais têm pouquíssimos


def _imagens_de(html: str | None) -> list[str]:
    if not html:
        return []
    soup = BeautifulSoup(html, "html.parser")
    return [img["src"] for img in soup.find_all("img") if img.get("src")]


def _page_alunos(payload: Any) -> dict:
    return ((payload or {}).get("comentarios") or {}).get("pageComentarios") or {}


def _normalizar_alunos(payload: Any) -> list[dict]:
    out: list[dict] = []
    for it in _page_alunos(payload).get("list") or []:
        tcid = it.get("id")
        if tcid is None:  # M-2: item sem id é ignorado defensivamente
            continue
        corpo = it.get("comentario")
        tipo = ("professor" if it.get("professor")
                else "administrador" if it.get("administrador") else "aluno")
        dp = it.get("dataPublicacao") or {}
        out.append({
            "tc_comentario_id": int(tcid),
            "tc_parent_id": None,  # fórum do TC é flat (sem thread no payload)
            "autor_nome": it.get("apelidoUsuario"),
            "autor_tipo": tipo,
            "curtidas": int(it.get("quantidadeVoto") or 0),
            "md": html_to_md(corpo),
            "imagens": _imagens_de(corpo),
            "publicado_em": (dp.get("$") if isinstance(dp, dict) else None),
        })
    return out


def _normalizar_professor(payload: Any) -> list[dict]:
    c = (payload or {}).get("comentario") or {}
    corpo = c.get("textoComentario")
    if not corpo:
        return []
    return [{
        "tc_comentario_id": None,  # TC não dá id; fetch_comentarios sintetiza -id_questao
        "tc_parent_id": None,
        "autor_nome": c.get("nomeProfessor"),
        "autor_tipo": "professor",
        "curtidas": 0,
        "md": html_to_md(corpo),
        "imagens": _imagens_de(corpo),
        "publicado_em": c.get("dataFormatadaParaHtml5"),
    }]


def normalizar_comentarios(payload: Any, quadro: str) -> list[dict]:
    return (_normalizar_professor(payload) if quadro == "professores"
            else _normalizar_alunos(payload))


async def fetch_comentarios(client: TcClient, id_questao: int, quadro: str) -> dict:
    """Busca os comentários de uma questão (caminho leve, sem human-mode)."""
    referer = f"https://www.tecconcursos.com.br/questoes/{id_questao}"

    if quadro == "professores":
        await asyncio.sleep(DELAY_S)
        path = f"/api/questoes/{id_questao}/comentario?tokenPreVisualizacao="
        r = await client._client.get(path, headers=client._build_headers(referer, None))
        client._check(r)
        coments = normalizar_comentarios(r.json(), "professores")
        for c in coments:  # sintetiza id determinístico (1 comentário/questão)
            if c["tc_comentario_id"] is None:
                c["tc_comentario_id"] = -id_questao
        log.info("tc.comentarios.fetched", id_questao=id_questao, quadro=quadro, n=len(coments))
        return {"comentarios": coments}

    # alunos: paginado (pageSize 50)
    coments: list[dict] = []
    pagina = 1
    while pagina <= MAX_PAGINAS:
        await asyncio.sleep(DELAY_S)
        path = (f"/api/discussoes/{id_questao}/comentarios-alunos"
                f"?ordenarPor=data&pagina={pagina}")
        r = await client._client.get(path, headers=client._build_headers(referer, None))
        client._check(r)
        data = r.json()
        pagina_itens = normalizar_comentarios(data, "alunos")
        if not pagina_itens:  # M-7: página vazia encerra a paginação
            break
        coments.extend(pagina_itens)
        pg = _page_alunos(data)
        page_size = int(pg.get("pageSize") or 50)
        total_pages = int(pg.get("totalPages") or 0)
        if len(pagina_itens) < page_size or (total_pages and pagina >= total_pages):
            break
        pagina += 1

    log.info("tc.comentarios.fetched", id_questao=id_questao, quadro=quadro, n=len(coments))
    return {"comentarios": coments}
