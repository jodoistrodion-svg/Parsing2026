from __future__ import annotations

import asyncio
import random
import time
from dataclasses import dataclass


@dataclass(slots=True)
class RateLimitState:
    limit: int | None = None
    remaining: int | None = None
    reset_at: float | None = None
    retry_after_until: float | None = None

    @property
    def exhausted(self) -> bool:
        return self.remaining == 0


class AdaptiveRateLimiter:
    """Honors server reset/retry-after without adding fixed latency to the normal path."""

    def __init__(self, safety_ms: int = 5) -> None:
        self._states: dict[str, RateLimitState] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._safety = max(0.0, safety_ms / 1000.0)

    def _lock(self, bucket: str) -> asyncio.Lock:
        lock = self._locks.get(bucket)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[bucket] = lock
        return lock

    async def before_request(self, bucket: str) -> None:
        while True:
            state = self._states.get(bucket)
            if state is None:
                return
            now = time.time()
            waits = []
            if state.exhausted and state.reset_at is not None:
                waits.append(state.reset_at - now + self._safety)
            if state.retry_after_until is not None:
                waits.append(state.retry_after_until - now + self._safety)
            delay = max(waits, default=0.0)
            if delay <= 0:
                return
            await asyncio.sleep(delay)

    async def note_retry_after(self, bucket: str, seconds: float) -> None:
        if seconds <= 0:
            return
        jitter = random.uniform(0.0, min(0.05, seconds * 0.1))
        async with self._lock(bucket):
            state = self._states.setdefault(bucket, RateLimitState())
            state.retry_after_until = max(
                state.retry_after_until or 0.0,
                time.time() + seconds + jitter,
            )

    async def observe(self, bucket: str, headers) -> None:
        def integer(name: str) -> int | None:
            try:
                return int(headers.get(name))
            except (TypeError, ValueError):
                return None

        def timestamp(name: str) -> float | None:
            try:
                return float(headers.get(name))
            except (TypeError, ValueError):
                return None

        self._states[bucket] = RateLimitState(
            limit=integer("X-RateLimit-Limit"),
            remaining=integer("X-RateLimit-Remaining"),
            reset_at=timestamp("X-RateLimit-Reset"),
            retry_after_until=self._states.get(bucket, RateLimitState()).retry_after_until,
        )

    def snapshot(self) -> dict[str, RateLimitState]:
        return dict(self._states)
