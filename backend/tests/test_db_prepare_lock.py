import pytest

from scripts import db_prepare


class _Result:
    def __init__(self, value):
        self._value = value

    def scalar(self):
        return self._value


class _Conn:
    def __init__(self, values):
        self.values = list(values)
        self.calls = 0

    async def execute(self, statement, params):
        self.calls += 1
        return _Result(self.values.pop(0))


@pytest.mark.asyncio
async def test_acquire_advisory_lock_retries_until_lock_is_available(monkeypatch):
    conn = _Conn([False, False, True])
    sleeps = []

    async def fake_sleep(seconds):
        sleeps.append(seconds)

    monkeypatch.setattr(db_prepare.asyncio, "sleep", fake_sleep)

    await db_prepare.acquire_advisory_lock(
        conn, lock_id=123, timeout_s=10, retry_delay_s=0.25
    )

    assert conn.calls == 3
    assert sleeps == [0.25, 0.25]


@pytest.mark.asyncio
async def test_acquire_advisory_lock_times_out_instead_of_waiting_forever(monkeypatch):
    conn = _Conn([False])

    async def fake_sleep(seconds):
        raise AssertionError("should not sleep after deadline")

    monkeypatch.setattr(db_prepare.asyncio, "sleep", fake_sleep)

    with pytest.raises(TimeoutError, match="advisory lock 123"):
        await db_prepare.acquire_advisory_lock(
            conn, lock_id=123, timeout_s=0, retry_delay_s=0.25
        )
