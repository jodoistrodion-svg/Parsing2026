from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Awaitable,Callable
@dataclass(frozen=True,slots=True)
class PurchasePolicy:
    account_check:bool=False
    parallel_first_wave:int=24
    max_duration_sec:float=2.8
PurchaseRunner=Callable[...,Awaitable[tuple[bool,str]]]
class PurchaseEngine:
    """Thin seam around the legacy buyer; keeps its latency-sensitive runner intact."""
    def __init__(self,runner:PurchaseRunner,policy:PurchasePolicy|None=None): self._runner=runner; self.policy=policy or PurchasePolicy()
    async def purchase(self,source,item,found_perf=None): return await self._runner(source,item,found_perf=found_perf)
