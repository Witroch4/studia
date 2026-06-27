import json
from pathlib import Path
from app.scrapers.tc_comentarios import normalizar_comentarios

FIX = Path(__file__).parent / "fixtures"

def _carrega(nome):
    return json.loads((FIX / nome).read_text())

def test_normaliza_alunos_valores_reais():
    out = normalizar_comentarios(_carrega("coment_alunos_sample.json"), "alunos")
    assert len(out) == 3
    c = out[0]
    assert set(c) == {"tc_comentario_id", "tc_parent_id", "autor_nome",
                      "autor_tipo", "curtidas", "md", "imagens", "publicado_em"}
    assert c["tc_comentario_id"] == 1984253
    assert c["autor_nome"] == "concurseirolol"
    assert c["autor_tipo"] == "aluno"
    assert c["curtidas"] == 1
    assert c["publicado_em"] == "02/12/2023 20:09:16"
    # 1º comentário é só uma imagem (s3) + texto
    assert any("amazonaws.com" in u or "tecconcursos" in u for u in c["imagens"])

def test_normaliza_professor_objeto_unico():
    out = normalizar_comentarios(_carrega("coment_professor_sample.json"), "professores")
    assert len(out) == 1
    c = out[0]
    assert c["autor_tipo"] == "professor"
    assert c["autor_nome"] == "Camila Rosa Vaz"
    assert c["publicado_em"] == "2024-04-28"
    assert c["md"] and "764" in c["md"]  # corpo convertido p/ markdown


def test_normaliza_alunos_item_sem_id_e_ignorado():
    """M-2: item da lista de alunos sem 'id' deve ser pulado sem KeyError."""
    payload = {
        "comentarios": {
            "pageComentarios": {
                "list": [
                    # item sem 'id' — deve ser ignorado defensivamente
                    {"comentario": "<p>sem id</p>", "apelidoUsuario": "x",
                     "quantidadeVoto": 0, "dataPublicacao": {}},
                    # item válido — deve ser normalizado normalmente
                    {"id": 99, "comentario": "<p>ok</p>", "apelidoUsuario": "y",
                     "quantidadeVoto": 2, "dataPublicacao": {"$": "01/01/2024 10:00:00"}},
                ],
                "pageSize": 50,
                "totalPages": 1,
            }
        }
    }
    out = normalizar_comentarios(payload, "alunos")
    assert len(out) == 1
    assert out[0]["tc_comentario_id"] == 99
