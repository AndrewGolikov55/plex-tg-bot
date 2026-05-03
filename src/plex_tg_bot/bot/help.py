from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import Command

from plex_tg_bot.i18n import t


async def handle_help_message(message: types.Message) -> None:
    await message.answer(t("help.text"))


def make_help_router() -> Router:
    router = Router(name="help")

    @router.message(Command("help"))
    async def _on_cmd(message: types.Message) -> None:
        await handle_help_message(message)

    return router
