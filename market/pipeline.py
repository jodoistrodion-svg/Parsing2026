from __future__ import annotations
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from typing import Any
from domain.decision import DecisionEngine
@dataclass(slots=True)
class PipelineItem:
    item:dict[str,Any]; source:dict[str,Any]; found_perf:float
@dataclass(slots=True)
class PipelineStats:
    discovered:int=0; duplicates:int=0; filtered:int=0; accepted:int=0; queued:int=0; queue_rejected:int=0
FetchSources=Callable[...,AsyncIterator[tuple[dict[str,Any],list[dict[str,Any]],str|None]]]
async def _noop_mark(_:str)->None: return None
class DiscoveryPipeline:
    """Hot-path orchestration: fetch -> dedup/decision -> enqueue -> seen."""
    def __init__(self,*,fetch_sources:FetchSources,make_key:Callable[[dict[str,Any]],str],is_seen:Callable[[str],bool],is_attempted:Callable[[str],bool],mark_seen:Callable[[str],Awaitable[None]],enqueue_autobuy:Callable[[dict[str,Any],dict[str,Any],float],Awaitable[None]],decision:DecisionEngine|None=None,max_items_per_source:int=200,max_new_items_per_cycle:int=1000):
        self._fetch_sources=fetch_sources;self._make_key=make_key;self._is_seen=is_seen;self._is_attempted=is_attempted;self._mark_seen=mark_seen;self._enqueue_autobuy=enqueue_autobuy;self._decision=decision or DecisionEngine();self._max_items_per_source=max(0,int(max_items_per_source));self._max_new_items_per_cycle=max(0,int(max_new_items_per_cycle))
    async def run(self,user_id:int,*,include_non_autobuy:bool):
        stats=PipelineStats();accepted=[];errors=[];seen_this_cycle=set()
        async for source,items,err in self._fetch_sources(user_id,include_non_autobuy=include_non_autobuy):
            if err:errors.append((str(source.get("name") or "UNKNOWN"),str(source.get("url") or "UNKNOWN"),str(err)));continue
            if not items:continue
            ordered=sorted(items,key=_item_sort_key,reverse=True)[:self._max_items_per_source] if self._max_items_per_source>0 else sorted(items,key=_item_sort_key,reverse=True)
            for item in ordered:
                if self._max_new_items_per_cycle>0 and stats.accepted>=self._max_new_items_per_cycle:break
                stats.discovered+=1;key=self._make_key(item)
                if key in seen_this_cycle or self._is_seen(key):stats.duplicates+=1;continue
                decision=self._decision.decide(item,already_attempted=self._is_attempted(key))
                if not decision.accepted:
                    if decision.reason=="filtered":stats.filtered+=1
                    else:stats.duplicates+=1
                    continue
                found_perf=perf_counter();seen_this_cycle.add(key)
                # Enqueue first: a failed queue handoff must not permanently hide a lot.
                if source.get("autobuy",False) and not self._is_attempted(key):
                    queued = await self._enqueue_autobuy(source,item,found_perf)
                    if queued is False:
                        stats.queue_rejected+=1
                        continue
                    stats.queued+=1
                await self._mark_seen(key);stats.accepted+=1
                accepted.append(PipelineItem(item=item,source=source,found_perf=found_perf))
        return accepted,stats,errors
def _parse_timestamp(value: Any) -> int:
    if value in (None, ""):
        return 0
    try:
        return int(float(value))
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text:
        return 0
    try:
        normalized = text[:-1] + "+00:00" if text.endswith("Z") else text
        dt = datetime.fromisoformat(normalized)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp())
    except (TypeError, ValueError, OverflowError):
        return 0

def _item_sort_key(item:dict[str,Any])->tuple[int,int]:
    published=item.get("published_at") or item.get("created_at") or item.get("date") or item.get("time")
    ts=_parse_timestamp(published)
    try:iid=int(item.get("item_id") or item.get("id") or 0)
    except (TypeError, ValueError):iid=0
    return ts,iid
