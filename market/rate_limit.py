from __future__ import annotations
import asyncio,time
from dataclasses import dataclass
@dataclass(slots=True)
class RateLimitState:
    limit:int|None=None; remaining:int|None=None; reset_at:float|None=None
    @property
    def exhausted(self)->bool: return self.remaining==0
class AdaptiveRateLimiter:
    def __init__(self,safety_ms:int=5): self._states={}; self._locks={}; self._safety=max(0.0,safety_ms/1000.0)
    def _lock(self,bucket):
        lock=self._locks.get(bucket)
        if lock is None: lock=asyncio.Lock(); self._locks[bucket]=lock
        return lock
    async def before_request(self,bucket):
        state=self._states.get(bucket)
        if state is None or not state.exhausted or state.reset_at is None:return
        async with self._lock(bucket):
            state=self._states.get(bucket)
            if state is None or not state.exhausted or state.reset_at is None:return
            delay=state.reset_at-time.time()+self._safety
            if delay>0: await asyncio.sleep(delay)
    async def observe(self,bucket,headers):
        def integer(name):
            try:return int(headers.get(name))
            except (TypeError,ValueError):return None
        def timestamp(name):
            try:return float(headers.get(name))
            except (TypeError,ValueError):return None
        self._states[bucket]=RateLimitState(integer("X-RateLimit-Limit"),integer("X-RateLimit-Remaining"),timestamp("X-RateLimit-Reset"))
    def snapshot(self): return dict(self._states)
