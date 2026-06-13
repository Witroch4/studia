"""Salvar matérias de um guia nas "Minhas Pastas" — por usuário.

Modelo: o catálogo (Guia → GuiaCaderno → CadernoQuestoes materializado com
owner_uid NULL) é compartilhado e fica sempre "pronto p/ estudar". O vínculo
"este usuário salvou esta matéria" é por usuário (tabela cadernos_salvos):
conta nova começa sem nada salvo, mas pode estudar do catálogo direto.
"""

from __future__ import annotations

import pytest

from auth import CurrentUser
from models import CadernoQuestoes, CadernoSalvo, Guia, GuiaCaderno


def _u(uid: str, role: str = "user") -> CurrentUser:
    return CurrentUser(id=uid, email=f"{uid}@t", name=uid, role=role, banned=False)


USER_A = _u("user-A")
USER_B = _u("user-B")


async def _seed_guia(db, *, n_materializados: int = 2, n_em_breve: int = 1):
    """Cria um guia com `n_materializados` matérias prontas (caderno_id setado,
    owner_uid NULL = catálogo) e `n_em_breve` ainda sem materializar."""
    guia = Guia(tc_guia_id=900, nome="Guia TESTE / 2026", banca="FGV")
    db.add(guia)
    await db.flush()

    cadernos = []
    for i in range(n_materializados):
        cq = CadernoQuestoes(
            nome=f"Matéria {i}",
            pasta=guia.nome,
            owner_uid=None,  # catálogo compartilhado
            tc_caderno_id=1000 + i,
            question_ids=[i * 10 + 1, i * 10 + 2],
            total=2,
        )
        db.add(cq)
        await db.flush()
        gc = GuiaCaderno(
            guia_id=guia.id,
            tc_caderno_id=1000 + i,
            nome=f"Matéria {i}",
            total_questoes=2,
            ordem=i,
            caderno_id=cq.id,
            status="materialized",
        )
        db.add(gc)
        cadernos.append((gc, cq))

    for j in range(n_em_breve):
        gc = GuiaCaderno(
            guia_id=guia.id,
            tc_caderno_id=2000 + j,
            nome=f"Em breve {j}",
            total_questoes=5,
            ordem=100 + j,
            caderno_id=None,
            status="collecting",
        )
        db.add(gc)
    await db.commit()
    return guia, cadernos


# ─── conta nova: nada salvo ──────────────────────────────


@pytest.mark.asyncio
async def test_conta_nova_nenhuma_materia_salva(client, db_session, auth_state):
    guia, _ = await _seed_guia(db_session)
    auth_state["user"] = USER_A

    r = await client.get(f"/api/q/guias/{guia.id}")
    assert r.status_code == 200
    cads = r.json()["cadernos"]
    # Catálogo segue "pronto" (caderno_id presente) mas nada salvo p/ o usuário.
    assert all(c["salvo"] is False for c in cads if c["caderno_id"])

    r = await client.get("/api/q/guias")
    g = next(x for x in r.json()["guias"] if x["id"] == guia.id)
    assert g["cadernos_salvos"] == 0

    # Minhas Pastas vazia para conta nova.
    r = await client.get("/api/q/cadernos")
    assert r.json() == []
    assert (await client.get("/api/q/pastas")).json() == []


# ─── salvar uma matéria ──────────────────────────────────


@pytest.mark.asyncio
async def test_salvar_uma_materia_aparece_em_minhas_pastas(client, db_session, auth_state):
    guia, cadernos = await _seed_guia(db_session)
    gc0, cq0 = cadernos[0]
    auth_state["user"] = USER_A

    r = await client.post(f"/api/q/guias/{guia.id}/salvar", json={"tc_caderno_id": gc0.tc_caderno_id})
    assert r.status_code == 200
    assert r.json()["novos"] == 1

    # Só a matéria salva fica salvo=True.
    r = await client.get(f"/api/q/guias/{guia.id}")
    by_tc = {c["tc_caderno_id"]: c for c in r.json()["cadernos"]}
    assert by_tc[gc0.tc_caderno_id]["salvo"] is True
    assert by_tc[cadernos[1][0].tc_caderno_id]["salvo"] is False

    # Aparece em Minhas Pastas, agrupada pelo nome do guia.
    r = await client.get("/api/q/cadernos")
    assert [c["id"] for c in r.json()] == [cq0.id]
    r = await client.get("/api/q/pastas")
    pastas = {p["pasta"]: p for p in r.json()}
    assert pastas[guia.nome]["cadernos"] == 1


@pytest.mark.asyncio
async def test_salvar_idempotente(client, db_session, auth_state):
    guia, cadernos = await _seed_guia(db_session)
    gc0, _ = cadernos[0]
    auth_state["user"] = USER_A

    await client.post(f"/api/q/guias/{guia.id}/salvar", json={"tc_caderno_id": gc0.tc_caderno_id})
    r = await client.post(f"/api/q/guias/{guia.id}/salvar", json={"tc_caderno_id": gc0.tc_caderno_id})
    assert r.json()["novos"] == 0

    rows = (await db_session.execute(
        CadernoSalvo.__table__.select().where(CadernoSalvo.usuario_uid == USER_A.id)
    )).all()
    assert len(rows) == 1


# ─── salvar todas ────────────────────────────────────────


@pytest.mark.asyncio
async def test_salvar_todas_salva_so_materializadas(client, db_session, auth_state):
    guia, cadernos = await _seed_guia(db_session, n_materializados=2, n_em_breve=1)
    auth_state["user"] = USER_A

    r = await client.post(f"/api/q/guias/{guia.id}/salvar", json={})
    assert r.status_code == 200
    assert r.json()["novos"] == 2  # só as 2 materializadas; "em breve" não

    r = await client.get("/api/q/guias")
    g = next(x for x in r.json()["guias"] if x["id"] == guia.id)
    assert g["cadernos_salvos"] == 2

    r = await client.get("/api/q/cadernos")
    assert len(r.json()) == 2


# ─── dessalvar ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_dessalvar_remove_de_minhas_pastas(client, db_session, auth_state):
    guia, cadernos = await _seed_guia(db_session)
    gc0, _ = cadernos[0]
    auth_state["user"] = USER_A

    await client.post(f"/api/q/guias/{guia.id}/salvar", json={"tc_caderno_id": gc0.tc_caderno_id})
    r = await client.delete(f"/api/q/guias/{guia.id}/salvar", params={"tc_caderno_id": gc0.tc_caderno_id})
    assert r.status_code == 200
    assert r.json()["removidos"] == 1

    r = await client.get("/api/q/cadernos")
    assert r.json() == []


# ─── isolamento entre usuários ───────────────────────────


@pytest.mark.asyncio
async def test_salvar_isolado_por_usuario(client, db_session, auth_state):
    guia, cadernos = await _seed_guia(db_session)
    gc0, _ = cadernos[0]

    auth_state["user"] = USER_A
    await client.post(f"/api/q/guias/{guia.id}/salvar", json={"tc_caderno_id": gc0.tc_caderno_id})

    # User B não vê o que A salvou.
    auth_state["user"] = USER_B
    r = await client.get(f"/api/q/guias/{guia.id}")
    assert all(c["salvo"] is False for c in r.json()["cadernos"])
    assert (await client.get("/api/q/cadernos")).json() == []
    g = next(x for x in (await client.get("/api/q/guias")).json()["guias"] if x["id"] == guia.id)
    assert g["cadernos_salvos"] == 0


# ─── estudar do catálogo sem salvar ──────────────────────


@pytest.mark.asyncio
async def test_estudar_catalogo_sem_salvar(client, db_session, auth_state):
    """Conta nova consegue abrir/estudar um caderno do catálogo sem salvar."""
    guia, cadernos = await _seed_guia(db_session)
    _, cq0 = cadernos[0]
    auth_state["user"] = USER_A

    r = await client.get(f"/api/q/cadernos/{cq0.id}")
    assert r.status_code == 200
    assert r.json()["id"] == cq0.id
