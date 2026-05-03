from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject
from apscheduler.schedulers.asyncio import AsyncIOScheduler  # type: ignore[import-untyped]
from apscheduler.triggers.cron import CronTrigger  # type: ignore[import-untyped]

from plex_tg_bot import __version__
from plex_tg_bot.bot.admin import make_admin_router
from plex_tg_bot.bot.approve import make_approve_router
from plex_tg_bot.bot.apps import make_apps_router
from plex_tg_bot.bot.factory import make_bot_and_dispatcher
from plex_tg_bot.bot.help import make_help_router
from plex_tg_bot.bot.overseerr import make_overseerr_router
from plex_tg_bot.bot.request import make_request_router
from plex_tg_bot.bot.start import make_start_router
from plex_tg_bot.bot.watch import make_watch_router
from plex_tg_bot.config import Settings
from plex_tg_bot.db import Repo
from plex_tg_bot.http_server import Observability, make_http_app, start_http_server
from plex_tg_bot.i18n import load_apps, set_lang
from plex_tg_bot.jobs.daily_sync import run_daily_sync
from plex_tg_bot.services.http import make_async_client
from plex_tg_bot.services.overseerr import OverseerrClient
from plex_tg_bot.services.plex import PlexClient

log = logging.getLogger(__name__)


class _TelegramTickMiddleware(BaseMiddleware):
    def __init__(self, obs: Observability) -> None:
        self._obs = obs

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        self._obs.last_tg_update.set(time.time())
        return await handler(event, data)


async def _run() -> None:
    settings = Settings()  # type: ignore[call-arg]
    logging.basicConfig(level=settings.log_level)
    set_lang(settings.bot_lang)
    # Fail-fast: refuse to start if apps content for this locale isn't shipped.
    load_apps(settings.bot_lang)

    repo = Repo(settings.db_path)
    await repo.connect()

    http = make_async_client(settings.proxy_url, settings.no_proxy)

    bot, dp = make_bot_and_dispatcher(settings)

    plex = PlexClient(settings.plex_token, f"plex-tg-bot/{__version__}", http)
    overseerr: OverseerrClient | None = (
        OverseerrClient(
            settings.overseerr_public_url,  # type: ignore[arg-type]
            settings.overseerr_api_key,  # type: ignore[arg-type]
            http,
        )
        if settings.overseerr_enabled
        else None
    )

    if settings.plex_machine_identifier and settings.plex_server_name:
        await repo.upsert_plex_server_cache(
            settings.plex_machine_identifier, settings.plex_server_name
        )
    elif (await repo.get_plex_server_cache()) is None:
        try:
            mid, name = await plex.discover_server()
            await repo.upsert_plex_server_cache(mid, name)
        except Exception:
            log.warning("could not discover Plex server at startup")

    async def _sync_now() -> tuple[int, int]:
        return await run_daily_sync(repo, plex)

    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        _sync_now,
        CronTrigger.from_crontab(settings.daily_sync_cron),
        id="daily_sync",
    )
    scheduler.start()

    obs = Observability()
    http_app = make_http_app(obs)
    http_runner = await start_http_server(http_app, settings.health_port)

    async def _refresh_gauges() -> None:
        while True:
            try:
                obs.pending.set(await repo.count_pending_requests())
                obs.shared_active.set(await repo.count_active_shared())
            except Exception:
                log.exception("gauge refresh failed")
            await asyncio.sleep(60)

    gauge_task = asyncio.create_task(_refresh_gauges())

    dp.update.middleware(_TelegramTickMiddleware(obs))

    dp.include_router(make_admin_router(repo, settings, bot, plex, _sync_now))
    dp.include_router(make_start_router(repo, settings))
    dp.include_router(make_request_router(repo, bot, settings))
    dp.include_router(make_approve_router(repo, bot, settings, plex, overseerr))
    dp.include_router(make_apps_router(repo, settings))
    dp.include_router(make_watch_router(repo, settings))
    dp.include_router(make_overseerr_router(repo, settings))
    dp.include_router(make_help_router())
    try:
        await dp.start_polling(bot)
    finally:
        gauge_task.cancel()
        await http_runner.cleanup()
        scheduler.shutdown(wait=False)
        await http.aclose()
        await repo.close()
        await bot.session.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
