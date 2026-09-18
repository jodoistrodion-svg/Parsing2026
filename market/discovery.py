from __future__ import annotations
import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
SourceFetcher=Callable[[dict[str,Any]],Awaitable[tuple[dict[str,Any],list[dict[str,Any]],str|None]]]
async def iter_sources_split(sources:list[dict[str,Any]],fetcher:SourceFetcher,*,include_non_autobuy:bool)->AsyncIterator[tuple[dict[str,Any],list[dict[str,Any]],str|None]]:
    autobuy=[s for s in sources if s.get("autobuy",False)]; plain=[s for s in sources if not s.get("autobuy",False)]
    if not autobuy and not (include_non_autobuy and plain): return
    async def run_group(group):
        if not group: return
        tasks=[asyncio.create_task(fetcher(s)) for s in group]
        try:
            for fut in asyncio.as_completed(tasks):
                try: yield await fut
                except Exception as exc: yield {"idx":-1,"url":"UNKNOWN","name":"UNKNOWN","enabled":True,"autobuy":False},[],str(exc)
        finally:
            for task in tasks:
                if not task.done(): task.cancel()
    async for result in run_group(autobuy): yield result
    if include_non_autobuy:
        async for result in run_group(plain): yield result
