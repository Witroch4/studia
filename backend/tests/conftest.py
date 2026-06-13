import os

# Hermetic: garante que o SCRAPER_URL do container dev não vaze nos testes.
# DEVE ficar ANTES de qualquer import de módulo do projeto (q_router lê
# SCRAPER_URL no import time, via `from main import app`).
os.environ["SCRAPER_URL"] = "http://scraper:8090"

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.pool import NullPool
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from auth import CurrentUser, get_current_user_opt
from database import get_db
from main import app

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@postgres:5432/studia_test",
)


def make_user(uid: str, *, role: str = "user", banned: bool = False) -> CurrentUser:
    """Helper p/ montar um CurrentUser nos testes."""
    return CurrentUser(
        id=uid,
        email=f"{uid}@studia.test",
        name=uid,
        role=role,
        banned=banned,
    )


# Usuário padrão dos testes = admin (os endpoints admin-only de coleta/guias
# dependem disso; testes de isolamento trocam via auth_state["user"]).
ADMIN_USER = make_user("admin-1", role="admin")
USER_A = make_user("user-A")
USER_B = make_user("user-B")


@pytest_asyncio.fixture(scope="session")
async def _engine():
    # NullPool: desabilita reutilização de conexões entre testes.
    # Sem isso, o asyncpg retorna a mesma conexão do pool e o estado
    # interno (savepoints) do teste anterior vaza, causando
    # InterfaceError: cannot perform operation: another operation is in progress.
    engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db_session(_engine):
    # Isolamento por teste: transação externa + savepoints internos; rollback no fim.
    conn = await _engine.connect()
    trans = await conn.begin()
    Session = async_sessionmaker(
        bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
    )
    session = Session()
    try:
        yield session
    finally:
        await session.close()
        await trans.rollback()
        await conn.close()


@pytest.fixture
def auth_state():
    """Holder mutável do usuário atual. Default: admin.

    Para simular outro usuário num teste, reatribua:
        auth_state["user"] = USER_B
    Para simular deslogado:
        auth_state["user"] = None
    """
    return {"user": ADMIN_USER}


@pytest_asyncio.fixture
async def client(db_session, auth_state):
    async def override_get_db():
        yield db_session

    async def override_user():
        return auth_state["user"]

    previous_db = app.dependency_overrides.get(get_db)
    previous_user = app.dependency_overrides.get(get_current_user_opt)
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user_opt] = override_user
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
        if previous_user is None:
            app.dependency_overrides.pop(get_current_user_opt, None)
        else:
            app.dependency_overrides[get_current_user_opt] = previous_user
