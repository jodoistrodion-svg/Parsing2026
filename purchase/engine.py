from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PurchasePolicy:
    account_check: bool = False
    parallel_first_wave: int = 24
    max_duration_sec: float = 2.8


PurchaseRunner = Callable[..., Awaitable[tuple[bool, str]]]


class PurchaseEngine:
    """Thin seam around the legacy buyer; it adds no hot-path work."""

    def __init__(self, runner: PurchaseRunner, policy: PurchasePolicy | None = None):
        self._runner = runner
        self.policy = policy or PurchasePolicy()

    async def purchase(
        self,
        source: dict[str, Any],
        item: dict[str, Any],
        found_perf: float | None = None,
    ) -> tuple[bool, str]:
        return await self._runner(source, item, found_perf=found_perf)
