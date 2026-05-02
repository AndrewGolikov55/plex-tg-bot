from __future__ import annotations

import asyncio
import logging

from plex_tg_bot.bot.factory import make_bot_and_dispatcher
from plex_tg_bot.bot.request import make_request_router
from plex_tg_bot.bot.start import make_start_router
from plex_tg_bot.config import Settings
from plex_tg_bot.db import Repo
from plex_tg_bot.i18n import set_lang
from plex_tg_bot.services.http import make_async_client


async def _run() -> None:
    settings = Settings()  # type: ignore[call-arg]
    logging.basicConfig(level=settings.log_level)
    set_lang(settings.bot_lang)

    repo = Repo(settings.db_path)
    await repo.connect()

    http = make_async_client(settings.proxy_url, settings.no_proxy)

    bot, dp = make_bot_and_dispatcher(settings)
    dp.include_router(make_start_router(repo, settings))
    dp.include_router(make_request_router(repo, bot, settings))
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
