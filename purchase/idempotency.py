from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(slots=True)
class PurchaseClaim:
    key: str
    owner: asyncio.Task | None


class PurchaseIdempotency:
    """Process-local single-flight guard for one item key."""

    def __init__(self):
        self._claims: dict[str, PurchaseClaim] = {}
        self._lock = asyncio.Lock()

    async def claim(self, key: str) -> bool:
        async with self._lock:
            if key in self._claims:
                return False
            self._claims[key] = PurchaseClaim(key, asyncio.current_task())
            return True

    async def release(self, key: str) -> None:
        async with self._lock:
            self._claims.pop(key, None)

    def claimed(self, key: str) -> bool:
        return key in self._claims
