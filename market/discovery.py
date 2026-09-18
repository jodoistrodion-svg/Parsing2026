from __future__ import annotations
import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

SourceFetcher=Callable[[dict[str,Any]],Awaitable[tuple[dict[str,Any],list[dict[str,Any]],str|None]]]
DISCOVERY_MAX_IN_FLIGHT=64

async def _run_bounded(group:list[dict[str,Any]], fetcher:SourceFetcher, limit:int=DISCOVERY_MAX_IN_FLIGHT):
    if not group:
        return
    pending:set[asyncio.Task]=set()
    index=0
    while pending or index < len(group):
        while index < len(group) and len(pending) < max(1,limit):
            pending.add(asyncio.create_task(fetcher(group[index])))
            index += 1
        done,pending=await asyncio.wait(pending,return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            try:
                yield await task
            except Exception as exc:
                yield {"idx":-1,"url":"UNKNOWN","name":"UNKNOWN","enabled":True,"autobuy":False},[],str(exc)

    for task in pending:
        task.cancel()
    if pending:
        await asyncio.gather(*pending,return_exceptions=True)

async def iter_sources_split(sources:list[dict[str,Any]],fetcher:SourceFetcher,*,include_non_autobuy:bool)->AsyncIterator[tuple[dict[str,Any],list[dict[str,Any]],str|None]]:
    autobuy=[s for s in sources if s.get("autobuy",False)]
    plain=[s for s in sources if not s.get("autobuy",False)]
    if not autobuy and not (include_non_autobuy and plain):
        return
    async for result in _run_bounded(autobuy,fetcher):
        yield result
    if include_non_autobuy:
        async for result in _run_bounded(plain,fetcher):
            yield result
