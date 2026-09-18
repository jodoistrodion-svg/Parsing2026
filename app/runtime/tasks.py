from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from dataclasses import dataclass
from typing import Any

from metrics.events import METRICS

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class ManagedTask:
    name: str
    task: asyncio.Task[Any]
    critical: bool = False


class TaskSupervisor:
    """Owns background tasks and guarantees deterministic cancellation and collection."""

    def __init__(self) -> None:
        self._tasks: dict[str, ManagedTask] = {}
        self._lock = asyncio.Lock()

    async def spawn(
        self,
        name: str,
        coroutine: Coroutine[Any, Any, Any],
        *,
        critical: bool = False,
    ) -> asyncio.Task[Any]:
        async with self._lock:
            previous = self._tasks.pop(name, None)
            if previous is not None and not previous.task.done():
                previous.task.cancel()
                await asyncio.gather(previous.task, return_exceptions=True)

            task = asyncio.create_task(coroutine, name=name)
            self._tasks[name] = ManagedTask(name=name, task=task, critical=critical)
            task.add_done_callback(self._on_done)
            METRICS.inc("background_tasks_spawned_total", labels={"task": name})
            return task

    def _on_done(self, task: asyncio.Task[Any]) -> None:
        for name, managed in list(self._tasks.items()):
            if managed.task is not task:
                continue
            if task.cancelled():
                METRICS.inc("background_tasks_cancelled_total", labels={"task": name})
                self._tasks.pop(name, None)
                return
            try:
                exc = task.exception()
            except asyncio.CancelledError:
                self._tasks.pop(name, None)
                return
            if exc is not None:
                METRICS.inc("background_tasks_failed_total", labels={"task": name})
                logger.error(
                    "BACKGROUND_TASK_FAILED name=%s",
                    name,
                    exc_info=(type(exc), exc, exc.__traceback__),
                )
            else:
                METRICS.inc("background_tasks_completed_total", labels={"task": name})
            self._tasks.pop(name, None)
            return

    def snapshot(self) -> list[dict[str, object]]:
        return [
            {
                "name": item.name,
                "done": item.task.done(),
                "cancelled": item.task.cancelled(),
                "critical": item.critical,
            }
            for item in self._tasks.values()
        ]

    async def shutdown(self, timeout: float = 5.0) -> None:
        async with self._lock:
            tasks = list(self._tasks.values())
            self._tasks.clear()

        for managed in tasks:
            if not managed.task.done():
                managed.task.cancel()

        if tasks:
            await asyncio.wait_for(
                asyncio.gather(*(item.task for item in tasks), return_exceptions=True),
                timeout=max(0.1, timeout),
            )
