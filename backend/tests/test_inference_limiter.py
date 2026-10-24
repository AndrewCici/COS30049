"""InferenceLimiter: at most `max_concurrent` slots run at once, up to
`max_queued` more may wait briefly for one, and anything beyond that
capacity -- or that waits past the timeout -- fails fast with
InferenceUnavailableError instead of queuing indefinitely."""
import os

import anyio
import pytest

from app.security.limiter import InferenceLimiter, InferenceUnavailableError


@pytest.mark.anyio
async def test_admits_up_to_max_concurrent_at_once():
    limiter = InferenceLimiter(max_concurrent=2, max_queued=0, queue_timeout_s=1.0)
    running = 0
    peak = 0

    async def work():
        nonlocal running, peak
        async with limiter.slot():
            running += 1
            peak = max(peak, running)
            await anyio.sleep(0.05)
            running -= 1

    async with anyio.create_task_group() as tg:
        for _ in range(2):
            tg.start_soon(work)

    assert peak == 2


@pytest.mark.anyio
async def test_rejects_beyond_concurrent_plus_queued_capacity():
    limiter = InferenceLimiter(max_concurrent=1, max_queued=1, queue_timeout_s=1.0)
    errors = []

    async def hold_slot(duration: float):
        async with limiter.slot():
            await anyio.sleep(duration)

    async def try_slot():
        try:
            async with limiter.slot():
                pass
        except InferenceUnavailableError as exc:
            errors.append(exc)

    async with anyio.create_task_group() as tg:
        tg.start_soon(hold_slot, 0.2)   # occupies the 1 concurrent slot
        await anyio.sleep(0.02)
        tg.start_soon(try_slot)         # takes the 1 queued slot, waits
        await anyio.sleep(0.02)
        tg.start_soon(try_slot)         # capacity (1+1) already full -> immediate reject

    assert len(errors) == 1


@pytest.mark.anyio
async def test_rejects_after_queue_timeout_elapses():
    limiter = InferenceLimiter(max_concurrent=1, max_queued=1, queue_timeout_s=0.05)
    errors = []

    async def hold_slot(duration: float):
        async with limiter.slot():
            await anyio.sleep(duration)

    async def try_slot():
        try:
            async with limiter.slot():
                pass
        except InferenceUnavailableError as exc:
            errors.append(exc)

    async with anyio.create_task_group() as tg:
        tg.start_soon(hold_slot, 0.3)  # held well past the 0.05s queue timeout
        await anyio.sleep(0.01)
        tg.start_soon(try_slot)

    assert len(errors) == 1
    assert errors[0].retry_after_s >= 1


@pytest.mark.anyio
async def test_slot_is_released_after_use_so_later_callers_are_admitted():
    limiter = InferenceLimiter(max_concurrent=1, max_queued=0, queue_timeout_s=1.0)

    async with limiter.slot():
        pass  # released on exit

    async with limiter.slot():
        pass  # would raise InferenceUnavailableError if the first slot leaked


@pytest.mark.anyio
async def test_disabled_by_security_defences_off_never_blocks(monkeypatch):
    monkeypatch.setenv("SECURITY_DEFENCES", "off")
    limiter = InferenceLimiter(max_concurrent=1, max_queued=0, queue_timeout_s=0.01)

    async def hold_forever():
        async with limiter.slot():
            await anyio.sleep(10)

    async with anyio.create_task_group() as tg:
        tg.start_soon(hold_forever)
        await anyio.sleep(0.02)
        # With defences off, slot() is a no-op context manager -- this must
        # return immediately rather than waiting on the (still-held) semaphore.
        with anyio.fail_after(0.5):
            async with limiter.slot():
                pass
        tg.cancel_scope.cancel()


# --- integration: the real app over HTTP, limiter forced unavailable -------


def test_score_returns_503_with_retry_after_when_limiter_saturated(monkeypatch):
    os.environ["AIDETECT_METHOD"] = "mock"
    monkeypatch.delenv("SECURITY_DEFENCES", raising=False)
    from fastapi.testclient import TestClient

    import app.main as main_module

    class _AlwaysFull:
        def slot(self):
            raise InferenceUnavailableError(retry_after_s=3)

    monkeypatch.setattr(main_module, "inference_limiter", _AlwaysFull())
    client = TestClient(main_module.app)
    r = client.post("/api/v1/score", json={"text": "A normal passage. Another sentence here."})
    assert r.status_code == 503
    assert r.headers.get("retry-after") == "3"
    body = r.json()
    assert body["error"]["code"] == "INFERENCE_QUEUE_FULL"
