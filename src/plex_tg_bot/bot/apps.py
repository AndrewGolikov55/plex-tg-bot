from __future__ import annotations

from pathlib import Path

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from plex_tg_bot.config import Settings
from plex_tg_bot.db import Repo
from plex_tg_bot.i18n import t


def _apps_keyboard() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text="Plex iOS", url="https://apps.apple.com/app/plex/id383457673")
    b.button(
        text="Plex Android",
        url="https://play.google.com/store/apps/details?id=com.plexapp.android",
    )
    b.button(text="Plex Web", url="https://app.plex.tv/desktop/")
    b.adjust(1)
    return b.as_markup()


def _build_apps_payload(settings: Settings) -> tuple[str, types.InlineKeyboardMarkup]:
    md_path = Path(settings.apps_markdown_path)
    text = ""
    if md_path.exists():
        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            text = ""
    if not text:
        text = t("apps.fallback", url="https://www.plex.tv/media-server-downloads/")
    return text, _apps_keyboard()


async def handle_apps_message(
    message: types.Message, repo: Repo, settings: Settings
) -> None:
    if message.from_user is None:
        return
    if not await repo.has_active_access(message.from_user.id):
        await message.answer(t("request.access_required"))
        return
    text, kb = _build_apps_payload(settings)
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")


async def handle_apps_callback(
    cq: types.CallbackQuery, repo: Repo, settings: Settings
) -> None:
    if cq.from_user is None or cq.message is None:
        await cq.answer()
        return
    if not await repo.has_active_access(cq.from_user.id):
        await cq.message.answer(t("request.access_required"))
        await cq.answer()
        return
    text, kb = _build_apps_payload(settings)
    assert isinstance(cq.message, types.Message)
    await cq.message.answer(text, reply_markup=kb, parse_mode="Markdown")
    await cq.answer()


def make_apps_router(repo: Repo, settings: Settings) -> Router:
    router = Router(name="apps")

    @router.message(Command("apps"))
    async def _on_cmd(message: types.Message) -> None:
        await handle_apps_message(message, repo, settings)

    @router.callback_query(F.data == "apps:show")
    async def _on_cb(cq: types.CallbackQuery) -> None:
        await handle_apps_callback(cq, repo, settings)

    return router
