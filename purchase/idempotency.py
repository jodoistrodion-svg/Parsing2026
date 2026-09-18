from __future__ import annotations
import asyncio
from dataclasses import dataclass
@dataclass(slots=True)
class PurchaseClaim: key:str; owner:asyncio.Task|None
class PurchaseIdempotency:
    def __init__(self): self._claims={}; self._lock=asyncio.Lock()
    async def claim(self,key):
        async with self._lock:
            if key in self._claims:return False
            self._claims[key]=PurchaseClaim(key,asyncio.current_task()); return True
    async def release(self,key):
        owner=asyncio.current_task()
        async with self._lock:
            claim=self._claims.get(key)
            if claim is None:
                return False
            if claim.owner is not None and claim.owner is not owner:
                return False
            self._claims.pop(key,None)
            return True
    def claimed(self,key): return key in self._claims
