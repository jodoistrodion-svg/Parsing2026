from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Mapping, Any


@dataclass(slots=True)
class RateLimitState:
    limit: int | None = None
    remaining: int | None = None
    reset_at: float | None = None

    @property
    def exhausted(self) -> bool:
        return self.remaining == 0


class AdaptiveRateLimiter:
    """Wait only when server headers say a bucket is exhausted."""

    def __init__(self, safety_ms: int = 5):
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
        state = self._states.get(bucket)
        if state is None or not state.exhausted or state.reset_at is None:
            return
        async with self._lock(bucket):
            state = self._states.get(bucket)
            if state is None or not state.exhausted or state.reset_at is None:
                return
            delay = state.reset_at - time.time() + self._safety
            if delay > 0:
                await asyncio.sleep(delay)

    async def observe(self, bucket: str, headers: Mapping[str, Any]) -> None:
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
        )

    def snapshot(self) -> dict[str, RateLimitState]:
        return dict(self._states)
