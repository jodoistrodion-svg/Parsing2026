from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass


@dataclass(slots=True)
class PurchaseClaim:
    key: str
    owner: asyncio.Task | None
    claimed_at: float


class PurchaseIdempotency:
    """Process-local idempotency guard with TTL recovery after abnormal task death."""

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self._claims: dict[str, PurchaseClaim] = {}
        self._lock = asyncio.Lock()
        self._ttl = max(1.0, float(ttl_seconds))

    def _prune_expired(self, now: float) -> None:
        expired = [
            key for key, claim in self._claims.items()
            if now - claim.claimed_at >= self._ttl
        ]
        for key in expired:
            self._claims.pop(key, None)

    async def claim(self, key: str) -> bool:
        now = time.monotonic()
        async with self._lock:
            self._prune_expired(now)
            if key in self._claims:
                return False
            self._claims[key] = PurchaseClaim(
                key=key,
                owner=asyncio.current_task(),
                claimed_at=now,
            )
            return True

    async def release(self, key: str) -> bool:
        owner = asyncio.current_task()
        async with self._lock:
            claim = self._claims.get(key)
            if claim is None:
                return False
            if claim.owner is not None and claim.owner is not owner:
                return False
            self._claims.pop(key, None)
            return True

    def claimed(self, key: str) -> bool:
        self._prune_expired(time.monotonic())
        return key in self._claims

    async def clear(self) -> None:
        async with self._lock:
            self._claims.clear()
