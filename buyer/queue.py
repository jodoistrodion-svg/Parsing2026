from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from app.config.settings import AUTOBUY_QUEUE_SIZE, AUTOBUY_WORKERS_PER_USER
from metrics.events import METRICS

logger = logging.getLogger(__name__)
JobHandler = Callable[[int, Any], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class QueueSnapshot:
    user_id: int
    queued: int
    workers: int
    maxsize: int


class UserAutobuyQueueManager:
    """Bounded per-user work queues with explicit backpressure and deterministic shutdown."""

    def __init__(
        self,
        maxsize: int = AUTOBUY_QUEUE_SIZE,
        workers_per_user: int = AUTOBUY_WORKERS_PER_USER,
    ) -> None:
        self._maxsize = max(1, int(maxsize))
        self._workers_per_user = max(1, int(workers_per_user))
        self._queues: dict[int, asyncio.Queue[Any]] = {}
        self._workers: dict[int, list[asyncio.Task[Any]]] = {}
        self._stopped_users: set[int] = set()
        self._lock = asyncio.Lock()

    def _get_queue(self, user_id: int) -> asyncio.Queue[Any]:
        queue = self._queues.get(user_id)
        if queue is None:
            queue = asyncio.Queue(maxsize=self._maxsize)
            self._queues[user_id] = queue
        return queue

    def _ensure_workers_locked(self, user_id: int, queue: asyncio.Queue[Any], handler: JobHandler) -> None:
        workers = [task for task in self._workers.get(user_id, []) if not task.done()]
        self._workers[user_id] = workers
        missing = max(0, self._workers_per_user - len(workers))
        for worker_index in range(missing):
            task = asyncio.create_task(
                self._worker_loop(user_id, queue, handler),
                name=f"autobuy-worker:{user_id}:{len(workers) + worker_index}",
            )
            workers.append(task)

    async def ensure_worker(self, user_id: int, handler: JobHandler) -> None:
        async with self._lock:
            self._stopped_users.discard(user_id)
            queue = self._get_queue(user_id)
            self._ensure_workers_locked(user_id, queue, handler)

    async def enqueue(
        self,
        user_id: int,
        payload: Any,
        handler: JobHandler,
    ) -> bool:
        async with self._lock:
            if user_id in self._stopped_users:
                METRICS.inc("autobuy_queue_rejected_stopped_total")
                return False
            queue = self._get_queue(user_id)
            self._ensure_workers_locked(user_id, queue, handler)
            try:
                queue.put_nowait(payload)
            except asyncio.QueueFull:
                METRICS.inc("autobuy_queue_rejected_total")
                logger.warning(
                    "AUTOBUY_QUEUE_FULL user_id=%s maxsize=%s",
                    user_id,
                    self._maxsize,
                )
                return False

        METRICS.inc("autobuy_queue_admitted_total")
        return True

    async def join_user(self, user_id: int) -> None:
        queue = self._queues.get(user_id)
        if queue is not None:
            await queue.join()

    async def stop_user(self, user_id: int, *, drain: bool = False) -> None:
        async with self._lock:
            self._stopped_users.add(user_id)
            workers = self._workers.pop(user_id, [])
            queue = self._queues.pop(user_id, None)

        if drain and queue is not None:
            await queue.join()

        for task in workers:
            task.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)

        if queue is not None:
            while not queue.empty():
                try:
                    queue.get_nowait()
                    queue.task_done()
                except asyncio.QueueEmpty:
                    break

    async def shutdown(self, *, drain: bool = False) -> None:
        for user_id in list(self._workers):
            await self.stop_user(user_id, drain=drain)

    def snapshot(self, user_id: int | None = None) -> list[QueueSnapshot]:
        user_ids = [user_id] if user_id is not None else sorted(self._queues)
        return [
            QueueSnapshot(
                user_id=uid,
                queued=self._queues[uid].qsize(),
                workers=sum(not task.done() for task in self._workers.get(uid, [])),
                maxsize=self._maxsize,
            )
            for uid in user_ids
            if uid in self._queues
        ]

    async def _worker_loop(self, user_id: int, queue: asyncio.Queue[Any], handler: JobHandler) -> None:
        while True:
            try:
                payload = await queue.get()
            except asyncio.CancelledError:
                return

            try:
                await handler(user_id, payload)
                METRICS.inc("autobuy_jobs_completed_total")
            except asyncio.CancelledError:
                raise
            except Exception:
                METRICS.inc("autobuy_jobs_failed_total")
                logger.exception("AUTOBUY_QUEUE_WORKER_ERR user_id=%s", user_id)
            finally:
                queue.task_done()
