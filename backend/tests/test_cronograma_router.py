import pytest
from datetime import date

from conftest import USER_A, USER_B
from models import CadernoQuestoes
import cronograma_router as cr


async def _caderno(db, owner="user-A", total=120):
    cad = CadernoQuestoes(owner_uid=owner, nome="Caderno Teste", total=total,
                          question_ids=list(range(1, total + 1)))
    db.add(cad)
    await db.flush()
    return cad


@pytest.mark.asyncio
async def test_post_e_get_cronograma(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    r = await client.post(f"/api/q/cadernos/{cad.id}/cronograma", json={
        "data_prova": "2026-08-16", "data_inicio": "2026-06-01",
        "dias_folga": [6], "buffer_dias": 21,
        "incluir_discursivas": False, "incluir_simulados": True,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["config"]["caderno_id"] == cad.id
    assert len(body["plano"]) >= 1
    assert body["plano"][-1]["fase"] == "prova"
    assert body["kpis"]["total"] == 120
    assert body["progresso"] == []  # sem resoluções ainda → curva real vazia

    r2 = await client.get(f"/api/q/cadernos/{cad.id}/cronograma")
    assert r2.status_code == 200
    assert r2.json()["config"]["data_prova"] == "2026-08-16"


@pytest.mark.asyncio
async def test_get_sem_cronograma_404(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    r = await client.get(f"/api/q/cadernos/{cad.id}/cronograma")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_data_prova_invalida_422(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    r = await client.post(f"/api/q/cadernos/{cad.id}/cronograma", json={
        "data_prova": "2026-05-01", "data_inicio": "2026-06-01",
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_outro_usuario_nao_acessa(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session, owner="user-A")
    await client.post(f"/api/q/cadernos/{cad.id}/cronograma",
                      json={"data_prova": "2026-08-16", "data_inicio": "2026-06-01"})
    auth_state["user"] = USER_B
    r = await client.get(f"/api/q/cadernos/{cad.id}/cronograma")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_delete_cronograma(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    await client.post(f"/api/q/cadernos/{cad.id}/cronograma",
                      json={"data_prova": "2026-08-16", "data_inicio": "2026-06-01"})
    r = await client.delete(f"/api/q/cadernos/{cad.id}/cronograma")
    assert r.status_code == 200
    assert (await client.get(f"/api/q/cadernos/{cad.id}/cronograma")).status_code == 404


@pytest.mark.asyncio
async def test_post_duplicado_409(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    body = {"data_prova": "2026-08-16", "data_inicio": "2026-06-01"}
    assert (await client.post(f"/api/q/cadernos/{cad.id}/cronograma", json=body)).status_code == 200
    r = await client.post(f"/api/q/cadernos/{cad.id}/cronograma", json=body)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_put_liga_simulados_gera_marcos(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    # cria SEM simulados
    body0 = (await client.post(f"/api/q/cadernos/{cad.id}/cronograma", json={
        "data_prova": "2026-08-16", "data_inicio": "2026-05-25",
        "incluir_simulados": False})).json()
    assert body0["simulados"] == []
    # PUT ligando simulados → devem aparecer
    body1 = (await client.put(f"/api/q/cadernos/{cad.id}/cronograma", json={
        "data_prova": "2026-08-16", "data_inicio": "2026-05-25",
        "incluir_simulados": True})).json()
    assert len(body1["simulados"]) >= 1
    # PUT desligando → somem
    body2 = (await client.put(f"/api/q/cadernos/{cad.id}/cronograma", json={
        "data_prova": "2026-08-16", "data_inicio": "2026-05-25",
        "incluir_simulados": False})).json()
    assert body2["simulados"] == []


@pytest.mark.asyncio
async def test_recalcular_rebaseline(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    await client.post(f"/api/q/cadernos/{cad.id}/cronograma",
                      json={"data_prova": "2026-08-16", "data_inicio": "2026-06-01"})
    r = await client.post(f"/api/q/cadernos/{cad.id}/cronograma/recalcular")
    assert r.status_code == 200
    assert r.json()["config"]["rebaseline_em"] is not None


@pytest.mark.asyncio
async def test_patch_simulado_resultado(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    body = (await client.post(f"/api/q/cadernos/{cad.id}/cronograma",
            json={"data_prova": "2026-08-16", "data_inicio": "2026-05-25",
                  "incluir_simulados": True})).json()
    assert body["simulados"], "deve ter marcos de simulado"
    sid = body["simulados"][0]["id"]
    r = await client.patch(
        f"/api/q/cadernos/{cad.id}/cronograma/simulados/{sid}",
        json={"resultado_objetiva": 88, "observacoes": "ok"},
    )
    assert r.status_code == 200
    novo = (await client.get(f"/api/q/cadernos/{cad.id}/cronograma")).json()
    alvo = next(s for s in novo["simulados"] if s["id"] == sid)
    assert alvo["resultado_objetiva"] == 88


@pytest.mark.asyncio
async def test_criar_com_discursivas_usa_ia(client, db_session, auth_state, monkeypatch):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    monkeypatch.setattr(cr, "gerar_temas_discursivas",
                        lambda materias, n: [f"Tema IA {i}" for i in range(n)])
    body = (await client.post(f"/api/q/cadernos/{cad.id}/cronograma", json={
        "data_prova": "2026-08-16", "data_inicio": "2026-05-25",
        "incluir_discursivas": True, "discursivas_por_semana": 2,
    })).json()
    assert len(body["discursivas"]) >= 1
    assert body["discursivas"][0]["tema"].startswith("Tema IA")


@pytest.mark.asyncio
async def test_ia_indisponivel_nao_bloqueia(client, db_session, auth_state, monkeypatch):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    def _boom(materias, n):
        raise RuntimeError("gemini down")
    monkeypatch.setattr(cr, "gerar_temas_discursivas", _boom)
    r = await client.post(f"/api/q/cadernos/{cad.id}/cronograma", json={
        "data_prova": "2026-08-16", "data_inicio": "2026-05-25",
        "incluir_discursivas": True,
    })
    assert r.status_code == 200
    assert r.json()["discursivas"] == []


@pytest.mark.asyncio
async def test_patch_discursiva_status(client, db_session, auth_state, monkeypatch):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    monkeypatch.setattr(cr, "gerar_temas_discursivas", lambda m, n: ["T1", "T2"])
    body = (await client.post(f"/api/q/cadernos/{cad.id}/cronograma", json={
        "data_prova": "2026-08-16", "data_inicio": "2026-05-25",
        "incluir_discursivas": True})).json()
    did = body["discursivas"][0]["id"]
    r = await client.patch(f"/api/q/cadernos/{cad.id}/cronograma/discursivas/{did}",
                           json={"status": "Feita", "nota": 17.5})
    assert r.status_code == 200
    novo = (await client.get(f"/api/q/cadernos/{cad.id}/cronograma")).json()
    alvo = next(d for d in novo["discursivas"] if d["id"] == did)
    assert alvo["status"] == "Feita" and alvo["nota"] == 17.5


@pytest.mark.asyncio
async def test_export_xlsx(client, db_session, auth_state):
    auth_state["user"] = USER_A
    cad = await _caderno(db_session)
    await client.post(f"/api/q/cadernos/{cad.id}/cronograma",
                      json={"data_prova": "2026-08-16", "data_inicio": "2026-05-25"})
    r = await client.get(f"/api/q/cadernos/{cad.id}/cronograma/export.xlsx")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/vnd.openxmlformats")
    assert len(r.content) > 0


# ─────────────────────────── anuladas fora das contas ───────────────────────────

@pytest.mark.asyncio
async def test_anuladas_fora_das_contas(client, db_session, auth_state):
    """Questão anulada sai do total/meta e resolução antiga dela não conta."""
    from models import Questao, Resolucao

    auth_state["user"] = USER_A
    db_session.add_all([
        Questao(id=701, status="ATIVA", gabarito="A", enunciado_md="q1"),
        Questao(id=702, status="ANULADA", gabarito="X", enunciado_md="q2 anulada"),
        Questao(id=703, status="ATIVA", gabarito="Anulada", enunciado_md="q3 anulada via gabarito"),
        Questao(id=704, status="ATIVA", gabarito="B", enunciado_md="q4"),
    ])
    cad = CadernoQuestoes(owner_uid="user-A", nome="Com anuladas", total=4,
                          question_ids=[701, 702, 703, 704])
    db_session.add(cad)
    await db_session.flush()
    # resolveu a válida 701 (acertou) e a 702 ANTES de ela ser anulada (errou)
    db_session.add_all([
        Resolucao(questao_id=701, caderno_id=cad.id, usuario_uid="user-A", acertou=True),
        Resolucao(questao_id=702, caderno_id=cad.id, usuario_uid="user-A", acertou=False),
    ])
    await db_session.commit()

    r = await client.post(f"/api/q/cadernos/{cad.id}/cronograma", json={
        "data_prova": "2026-08-16", "data_inicio": "2026-06-01",
    })
    assert r.status_code == 200, r.text
    kpis = r.json()["kpis"]
    assert kpis["anuladas"] == 2           # 702 (status) + 703 (gabarito)
    assert kpis["total"] == 2              # total efetivo = 4 − 2
    assert kpis["resolvidas"] == 1         # a resolução da anulada não conta
    assert kpis["acertos"] == 1
    assert kpis["restantes"] == 1
    # curva real também ignora a anulada
    progresso = r.json()["progresso"]
    assert len(progresso) == 1 and progresso[0]["resolvidas"] == 1
    # meta distribui só as 2 respondíveis
    assert r.json()["plano"][-1]["meta_acumulada"] == 2


@pytest.mark.asyncio
async def test_indice_marca_anulada(client, db_session, auth_state):
    from models import Questao

    auth_state["user"] = USER_A
    db_session.add_all([
        Questao(id=711, status="ATIVA", gabarito="A", enunciado_md="ok"),
        Questao(id=712, status="ANULADA", gabarito="X", enunciado_md="anulada"),
    ])
    cad = CadernoQuestoes(owner_uid="user-A", nome="Indice anuladas", total=2,
                          question_ids=[711, 712])
    db_session.add(cad)
    await db_session.commit()

    r = await client.get(f"/api/q/cadernos/{cad.id}/indice")
    assert r.status_code == 200
    items = r.json()["items"]
    assert items[0]["anulada"] is False
    assert items[1]["anulada"] is True
