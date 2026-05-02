from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from plex_tg_bot.config import Settings
from plex_tg_bot.db import Repo
from plex_tg_bot.i18n import t


async def handle_watch(
    message: types.Message, repo: Repo, settings: Settings
) -> None:
    if message.from_user is None:
        return
    if not await repo.has_active_access(message.from_user.id):
        await message.answer(t("request.access_required"))
        return
    b = InlineKeyboardBuilder()
    b.button(text=t("menu.watch"), url=settings.watch_url)
    await message.answer(t("menu.watch"), reply_markup=b.as_markup())


def make_watch_router(repo: Repo, settings: Settings) -> Router:
    router = Router(name="watch")

    @router.message(Command("watch"))
    async def _on(message: types.Message) -> None:
        await handle_watch(message, repo, settings)

    return router
