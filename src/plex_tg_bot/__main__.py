from __future__ import annotations

import asyncio
import logging

from plex_tg_bot import __version__
from plex_tg_bot.bot.approve import make_approve_router
from plex_tg_bot.bot.apps import make_apps_router
from plex_tg_bot.bot.factory import make_bot_and_dispatcher
from plex_tg_bot.bot.overseerr import make_overseerr_router
from plex_tg_bot.bot.request import make_request_router
from plex_tg_bot.bot.start import make_start_router
from plex_tg_bot.bot.watch import make_watch_router
from plex_tg_bot.config import Settings
from plex_tg_bot.db import Repo
from plex_tg_bot.i18n import set_lang
from plex_tg_bot.services.http import make_async_client
from plex_tg_bot.services.overseerr import OverseerrClient
from plex_tg_bot.services.plex import PlexClient

log = logging.getLogger(__name__)


async def _run() -> None:
    settings = Settings()  # type: ignore[call-arg]
    logging.basicConfig(level=settings.log_level)
    set_lang(settings.bot_lang)

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

    dp.include_router(make_start_router(repo, settings))
    dp.include_router(make_request_router(repo, bot, settings))
    dp.include_router(make_approve_router(repo, bot, settings, plex, overseerr))
    dp.include_router(make_apps_router(repo, settings))
    dp.include_router(make_watch_router(repo, settings))
    dp.include_router(make_overseerr_router(repo, settings))
    try:
        await dp.start_polling(bot)
    finally:
        await http.aclose()
        await repo.close()
        await bot.session.close()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
