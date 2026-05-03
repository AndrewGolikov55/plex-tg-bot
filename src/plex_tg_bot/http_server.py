from __future__ import annotations

import time

from aiohttp import web
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    generate_latest,
)


class Observability:
    def __init__(self) -> None:
        self.registry = CollectorRegistry()
        self.last_tg_update = Gauge(
            "plexbot_telegram_last_update_ts",
            "Last successful Telegram poll",
            registry=self.registry,
        )
        self.pending = Gauge(
            "plexbot_pending_requests",
            "Pending requests count",
            registry=self.registry,
        )
        self.shared_active = Gauge(
            "plexbot_shared_users_active",
            "Active shared users",
            registry=self.registry,
        )
        self.requests_total = Counter(
            "plexbot_requests_total",
            "Decision counter",
            labelnames=("result",),
            registry=self.registry,
        )
        self.plex_api_errors = Counter(
            "plexbot_plex_api_errors_total",
            "Plex API errors",
            registry=self.registry,
        )
        self.plex_auth_errors = Counter(
            "plexbot_plex_auth_errors_total",
            "Plex 401 errors",
            registry=self.registry,
        )
        self.overseerr_errors = Counter(
            "plexbot_overseerr_import_errors_total",
            "Overseerr import errors",
            registry=self.registry,
        )
        self.daily_sync_last = Gauge(
            "plexbot_daily_sync_last_ts",
            "Last daily sync ts",
            registry=self.registry,
        )
        self.daily_sync_failures = Counter(
            "plexbot_daily_sync_failures_total",
            "Daily sync failures",
            registry=self.registry,
        )
        self.last_tg_update.set(time.time())  # avoid false positive at startup

    def last_tg_update_ts(self) -> float:
        return float(self.last_tg_update._value.get())


def make_http_app(obs: Observability) -> web.Application:
    async def healthz(request: web.Request) -> web.Response:
        # Liveness only: if this handler runs, the asyncio loop and aiohttp
        # server are alive. last_tg_update is exposed for observability but
        # NOT a failure signal — the bot may legitimately be idle for hours
        # between user messages.
        return web.json_response(
            {"status": "ok", "last_tg_update": obs.last_tg_update_ts()}
        )

    async def metrics(request: web.Request) -> web.Response:
        return web.Response(
            body=generate_latest(obs.registry),
            headers={"Content-Type": CONTENT_TYPE_LATEST},
        )

    app = web.Application()
    app.router.add_get("/healthz", healthz)
    app.router.add_get("/metrics", metrics)
    return app


async def start_http_server(app: web.Application, port: int) -> web.AppRunner:
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return runner
