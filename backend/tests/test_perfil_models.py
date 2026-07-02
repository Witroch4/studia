"""PerfilUsuario: criação, defaults e unicidade de owner_uid/apelido."""

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models import PerfilUsuario

pytestmark = pytest.mark.asyncio


async def test_cria_perfil_com_defaults(db_session):
    db_session.add(PerfilUsuario(owner_uid="user-A"))
    await db_session.commit()
    p = (await db_session.execute(
        select(PerfilUsuario).where(PerfilUsuario.owner_uid == "user-A")
    )).scalars().one()
    assert p.apelido is None
    assert p.avatar_key is None
    assert p.perfil_publico is True
    assert p.mostrar_estatisticas is True
    assert p.mostrar_foto is True


async def test_apelido_unico(db_session):
    db_session.add(PerfilUsuario(owner_uid="user-A", apelido="rochedo-16"))
    await db_session.commit()
    db_session.add(PerfilUsuario(owner_uid="user-B", apelido="rochedo-16"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()


async def test_owner_uid_unico(db_session):
    db_session.add(PerfilUsuario(owner_uid="user-A"))
    await db_session.commit()
    db_session.add(PerfilUsuario(owner_uid="user-A"))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
