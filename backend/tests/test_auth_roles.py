import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

from auth import CurrentUser, require_professor, get_current_user_opt
from tests.conftest import make_user


def test_is_professor_property():
    assert make_user("u", role="professor").is_professor is True
    assert make_user("u", role="admin").is_professor is True
    assert make_user("u", role="user").is_professor is False
    # admin continua admin; professor NÃO é admin
    assert make_user("u", role="professor").is_admin is False
    assert make_user("u", role="admin").is_admin is True


def _app_com_user(user):
    app = FastAPI()

    @app.get("/protegido")
    async def protegido(u: CurrentUser = Depends(require_professor)):
        return {"id": u.id}

    async def override():
        return user

    app.dependency_overrides[get_current_user_opt] = override
    return app


@pytest.mark.asyncio
async def test_require_professor_status_por_role():
    casos = {None: 401, "user": 403, "professor": 200, "admin": 200}
    for role, esperado in casos.items():
        user = None if role is None else make_user("u", role=role)
        app = _app_com_user(user)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as cli:
            r = await cli.get("/protegido")
        assert r.status_code == esperado, f"role={role}"
