from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

logger = logging.getLogger(__name__)
JobHandler = Callable[[int, Any], Awaitable[None]]


class UserAutobuyQueueManager:
    """Per-user concurrent autobuy queue; handoff uses put_nowait."""

    def __init__(self, maxsize: int = 2000, workers_per_user: int = 8):
        self._maxsize = max(1, int(maxsize))
        self._workers_per_user = max(1, int(workers_per_user))
        self._queues: dict[int, asyncio.Queue[Any]] = {}
        self._workers: dict[int, list[asyncio.Task[None]]] = {}
        self._lock = asyncio.Lock()

    def _get_queue(self, user_id: int) -> asyncio.Queue[Any]:
        queue = self._queues.get(user_id)
        if queue is None:
            queue = asyncio.Queue(maxsize=self._maxsize)
            self._queues[user_id] = queue
        return queue

    async def ensure_worker(self, user_id: int, handler: JobHandler) -> None:
        async with self._lock:
            workers = [task for task in self._workers.get(user_id, []) if not task.done()]
            self._workers[user_id] = workers
            for _ in range(self._workers_per_user - len(workers)):
                workers.append(asyncio.create_task(self._worker_loop(user_id, handler)))

    async def enqueue(self, user_id: int, payload: Any, handler: JobHandler) -> None:
        await self.ensure_worker(user_id, handler)
        queue = self._get_queue(user_id)
        if queue.full():
            dropped = 0
            while queue.full() and not queue.empty() and dropped < 200:
                try:
                    queue.get_nowait()
                    queue.task_done()
                    dropped += 1
                except asyncio.QueueEmpty:
                    break
            if dropped:
                logger.warning("AUTOBUY_QUEUE_DROP user_id=%s dropped=%s", user_id, dropped)
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            logger.warning("AUTOBUY_QUEUE_FULL user_id=%s", user_id)

    async def stop_user(self, user_id: int) -> None:
        async with self._lock:
            workers = self._workers.pop(user_id, [])
        for task in workers:
            task.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        self._queues.pop(user_id, None)

    async def shutdown(self) -> None:
        for user_id in list(self._workers):
            await self.stop_user(user_id)

    async def _worker_loop(self, user_id: int, handler: JobHandler) -> None:
        queue = self._get_queue(user_id)
        while True:
            try:
                payload = await queue.get()
            except asyncio.CancelledError:
                break
            try:
                await handler(user_id, payload)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("AUTOBUY_QUEUE_WORKER_ERR user_id=%s", user_id)
            finally:
                queue.task_done()
