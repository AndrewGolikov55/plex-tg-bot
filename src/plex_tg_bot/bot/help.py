from __future__ import annotations

from aiogram import F, Router, types
from aiogram.filters import Command

from plex_tg_bot.i18n import t


async def handle_help_message(message: types.Message) -> None:
    await message.answer(t("help.text"))


async def handle_help_callback(cq: types.CallbackQuery) -> None:
    if cq.message is not None and not isinstance(
        cq.message, types.InaccessibleMessage
    ):
        await cq.message.answer(t("help.text"))
    await cq.answer()


def make_help_router() -> Router:
    router = Router(name="help")

    @router.message(Command("help"))
    async def _on_cmd(message: types.Message) -> None:
        await handle_help_message(message)

    @router.callback_query(F.data == "help:show")
    async def _on_cb(cq: types.CallbackQuery) -> None:
        await handle_help_callback(cq)

    return router
