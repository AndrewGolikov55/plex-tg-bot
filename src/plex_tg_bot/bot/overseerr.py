from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from plex_tg_bot.config import Settings
from plex_tg_bot.db import Repo
from plex_tg_bot.i18n import t


async def handle_overseerr(
    message: types.Message, repo: Repo, settings: Settings
) -> None:
    if not settings.overseerr_enabled:
        await message.answer(t("errors.feature_disabled"))
        return
    if message.from_user is None:
        return
    if not await repo.has_active_access(message.from_user.id):
        await message.answer(t("request.access_required"))
        return
    b = InlineKeyboardBuilder()
    b.button(text=t("menu.overseerr"), url=settings.overseerr_public_url or "")
    await message.answer(t("menu.overseerr"), reply_markup=b.as_markup())


def make_overseerr_router(repo: Repo, settings: Settings) -> Router:
    router = Router(name="overseerr")

    @router.message(Command("overseerr"))
    async def _on(message: types.Message) -> None:
        await handle_overseerr(message, repo, settings)

    return router
