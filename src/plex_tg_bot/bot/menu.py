from __future__ import annotations

from typing import Literal

from aiogram.types import InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from plex_tg_bot.i18n import t

State = Literal["no_access", "pending", "has_access"]


def build_main_menu(
    state: State,
    overseerr_enabled: bool = False,
    watch_url: str = "https://app.plex.tv/desktop/",
    overseerr_url: str | None = None,
) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if state == "no_access":
        b.button(text=t("menu.request_access"), callback_data="request:start")
    elif state == "has_access":
        b.button(text=t("menu.apps"), callback_data="apps:show")
        b.button(text=t("menu.watch"), url=watch_url)
        if overseerr_enabled and overseerr_url:
            b.button(text=t("menu.overseerr"), url=overseerr_url)
    b.adjust(1)
    return b.as_markup()
