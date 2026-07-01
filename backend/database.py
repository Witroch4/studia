import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/studia",
)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    return int(value)


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    return float(value)


def _engine_kwargs_from_env() -> dict:
    return {
        "echo": False,
        "pool_pre_ping": True,
        "pool_size": _env_int("DB_POOL_SIZE", 10),
        "max_overflow": _env_int("DB_MAX_OVERFLOW", 20),
        "pool_timeout": _env_float("DB_POOL_TIMEOUT", 10.0),
        "pool_recycle": _env_int("DB_POOL_RECYCLE", 300),
        "connect_args": {
            "server_settings": {
                "application_name": os.getenv("DB_APPLICATION_NAME", "studia-backend")
            }
        },
    }


engine = create_async_engine(DATABASE_URL, **_engine_kwargs_from_env())
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session
