from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.fsm.storage.memory import MemoryStorage

from plex_tg_bot.config import Settings


def make_bot_and_dispatcher(settings: Settings) -> tuple[Bot, Dispatcher]:
    session = AiohttpSession(proxy=settings.proxy_url) if settings.proxy_url else AiohttpSession()
    bot = Bot(token=settings.telegram_bot_token, session=session)
    dp = Dispatcher(storage=MemoryStorage())
    return bot, dp
