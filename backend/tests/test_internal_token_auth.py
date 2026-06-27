import os
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from database import get_db
from main import app


@pytest_asyncio.fixture
async def client_sem_auth(db_session):
    """Cliente HTTP sem sessão autenticada.

    Sobrescreve apenas get_db (banco de testes isolado), mas NÃO sobrescreve
    get_current_user_opt — assim o endpoint recebe user=None e cai no caminho
    do token de serviço.
    """
    from auth import get_current_user_opt

    async def override_get_db():
        yield db_session

    previous_db = app.dependency_overrides.get(get_db)
    # Garante que get_current_user_opt NÃO está sobrescrito (retorna None por padrão sem cookie).
    previous_user = app.dependency_overrides.pop(get_current_user_opt, None)
    app.dependency_overrides[get_db] = override_get_db
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as test_client:
            yield test_client
    finally:
        if previous_db is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = previous_db
        # Restaura override anterior de get_current_user_opt (se havia um do client autenticado).
        if previous_user is not None:
            app.dependency_overrides[get_current_user_opt] = previous_user


@pytest.mark.asyncio
async def test_token_servico_autoriza(db_session, client_sem_auth, monkeypatch):
    from models import Questao

    monkeypatch.setenv("STUDIA_INTERNAL_TOKEN", "segredo123")
    db_session.add(Questao(id=70, id_externo=None))  # no-op, mas passa do auth
    await db_session.commit()
    # sem sessão + token correto → 200 (no-op por id_externo None)
    r = await client_sem_auth.post(
        "/api/q/questoes/70/importar-comentarios-tc?quadro=alunos",
        headers={"X-Internal-Token": "segredo123"},
    )
    assert r.status_code == 200
    # sem sessão + token errado → 401
    r2 = await client_sem_auth.post(
        "/api/q/questoes/70/importar-comentarios-tc?quadro=alunos",
        headers={"X-Internal-Token": "errado"},
    )
    assert r2.status_code == 401
