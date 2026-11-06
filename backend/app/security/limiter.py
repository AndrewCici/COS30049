"""Bounds how many sentence-scoring inferences run at once.

CPython's GIL means concurrently-running CPU-bound threads contend rather
than execute in parallel, so letting every request start inference
immediately just makes every request slower together under load. Instead,
at most MAX_CONCURRENT_INFERENCES run; up to MAX_QUEUED_INFERENCES more may
wait briefly (QUEUE_TIMEOUT_S) for a slot; everything beyond that capacity,
or that waits past the timeout, fails fast with a 503 the caller can retry
rather than queuing indefinitely.
"""
from contextlib import asynccontextmanager

import anyio

from .. import config


class InferenceUnavailableError(RuntimeError):
    """Raised when no concurrency slot could be obtained in time."""

    def __init__(self, retry_after_s: int = 1):
        self.retry_after_s = retry_after_s
        super().__init__("Too many concurrent scoring requests.")


class InferenceLimiter:
    def __init__(self, max_concurrent: int, max_queued: int, queue_timeout_s: float):
        self._semaphore = anyio.Semaphore(max_concurrent)
        self._capacity = max_concurrent + max_queued
        self._admitted = 0  # running + queued-for-a-slot
        self._lock = anyio.Lock()
        self._queue_timeout_s = queue_timeout_s

    @asynccontextmanager
    async def slot(self):
        if not config.security_defences_enabled():
            yield
            return

        async with self._lock:
            if self._admitted >= self._capacity:
                raise InferenceUnavailableError()
            self._admitted += 1
        try:
            with anyio.move_on_after(self._queue_timeout_s) as cancel_scope:
                await self._semaphore.acquire()
            if cancel_scope.cancelled_caught:
                raise InferenceUnavailableError()
            try:
                yield
            finally:
                self._semaphore.release()
        finally:
            async with self._lock:
                self._admitted -= 1


inference_limiter = InferenceLimiter(
    max_concurrent=config.MAX_CONCURRENT_INFERENCES,
    max_queued=config.MAX_QUEUED_INFERENCES,
    queue_timeout_s=config.QUEUE_TIMEOUT_S,
)
