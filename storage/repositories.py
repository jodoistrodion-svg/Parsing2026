from __future__ import annotations

from typing import Any, Protocol


class UrlRepository(Protocol):
    async def list(self, user_id: int) -> list[dict[str, Any]]: ...


class SeenRepository(Protocol):
    async def contains(self, user_id: int, key: str) -> bool: ...
    async def mark(self, user_id: int, key: str) -> None: ...


class PurchaseAttemptRepository(Protocol):
    async def contains(self, user_id: int, key: str) -> bool: ...
    async def mark(self, user_id: int, key: str) -> None: ...
