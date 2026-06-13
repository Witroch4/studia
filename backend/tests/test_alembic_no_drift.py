import os
import subprocess
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
TEST_DB = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@postgres:5432/studia_test",
)


def test_alembic_check_sem_drift():
    """alembic check contra o banco de teste: models == migrações (sem drift)."""
    env = {**os.environ, "DATABASE_URL": TEST_DB}
    up = subprocess.run(["alembic", "upgrade", "head"], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert up.returncode == 0, up.stderr
    chk = subprocess.run(["alembic", "check"], cwd=BACKEND, env=env, capture_output=True, text=True)
    assert chk.returncode == 0, f"drift detectado:\n{chk.stdout}\n{chk.stderr}"
