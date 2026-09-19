from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from app.config.settings import DISCOVERY_MAX_IN_FLIGHT
from metrics.events import METRICS

SourceFetcher = Callable[[dict[str, Any]], Awaitable[tuple[dict[str, Any], list[dict[str, Any]], str | None]]]


async def _run_bounded(
    group: list[dict[str, Any]],
    fetcher: SourceFetcher,
    limit: int = DISCOVERY_MAX_IN_FLIGHT,
) -> AsyncIterator[tuple[dict[str, Any], list[dict[str, Any]], str | None]]:
    """Run source fetches concurrently and always cancel/drain pending work on exit."""
    if not group:
        return

    pending: set[asyncio.Task[Any]] = set()
    index = 0
    concurrency = max(1, min(int(limit), len(group)))

    try:
        while pending or index < len(group):
            while index < len(group) and len(pending) < concurrency:
                task = asyncio.create_task(fetcher(group[index]), name=f"discover:{index}")
                pending.add(task)
                index += 1

            if not pending:
                break

            done, pending = await asyncio.wait(
                pending,
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in done:
                try:
                    result = await task
                    METRICS.inc("discovery_sources_completed_total")
                    yield result
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    METRICS.inc("discovery_sources_failed_total")
                    yield (
                        {"idx": -1, "url": "UNKNOWN", "name": "UNKNOWN", "enabled": True, "autobuy": False},
                        [],
                        str(exc),
                    )
    finally:
        for task in pending:
            if not task.done():
                task.cancel()
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)


async def iter_sources_split(
    sources: list[dict[str, Any]],
    fetcher: SourceFetcher,
    *,
    include_non_autobuy: bool,
) -> AsyncIterator[tuple[dict[str, Any], list[dict[str, Any]], str | None]]:
    autobuy = [source for source in sources if source.get("autobuy", False)]
    plain = [source for source in sources if not source.get("autobuy", False)]

    async for result in _run_bounded(autobuy, fetcher):
        yield result

    if include_non_autobuy:
        async for result in _run_bounded(plain, fetcher):
            yield result
