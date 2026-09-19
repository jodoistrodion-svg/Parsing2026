from __future__ import annotations

import time
from dataclasses import dataclass

from aiohttp import web

from metrics.events import METRICS


@dataclass(slots=True)
class RuntimeHealth:
    started_at: float = 0.0
    ready: bool = False
    shutting_down: bool = False
    last_error: str | None = None

    def snapshot(self) -> dict[str, object]:
        uptime = max(0.0, time.monotonic() - self.started_at) if self.started_at else 0.0
        return {
            "status": "ready" if self.ready and not self.shutting_down else "starting" if not self.shutting_down else "stopping",
            "ready": self.ready,
            "shutting_down": self.shutting_down,
            "uptime_sec": round(uptime, 3),
            "last_error": self.last_error,
        }


class HealthServer:
    def __init__(self, host: str, port: int, health: RuntimeHealth | None = None) -> None:
        self.host = host
        self.port = int(port)
        self.health = health or RuntimeHealth(started_at=time.monotonic())
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    async def start(self) -> None:
        self.health.started_at = time.monotonic()
        if self.port <= 0:
            return

        app = web.Application()
        app.add_routes(
            [
                web.get("/healthz", self._healthz),
                web.get("/readyz", self._readyz),
                web.get("/metrics", self._metrics),
            ]
        )
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        METRICS.set("health_server_up", 1)
        METRICS.set("health_server_port", self.port)

    async def stop(self) -> None:
        self.health.shutting_down = True
        self.health.ready = False
        METRICS.set("health_server_up", 0)
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None
            self._site = None

    async def set_ready(self, ready: bool = True) -> None:
        self.health.ready = bool(ready)
        METRICS.set("app_ready", 1 if self.health.ready else 0)

    def set_error(self, message: str | None) -> None:
        self.health.last_error = message

    async def _healthz(self, _request: web.Request) -> web.Response:
        return web.json_response({"ok": True, **self.health.snapshot()})

    async def _readyz(self, _request: web.Request) -> web.Response:
        payload = {"ok": self.health.ready and not self.health.shutting_down, **self.health.snapshot()}
        return web.json_response(payload, status=200 if payload["ok"] else 503)

    async def _metrics(self, _request: web.Request) -> web.Response:
        return web.Response(text=METRICS.prometheus_text(), content_type="text/plain")
