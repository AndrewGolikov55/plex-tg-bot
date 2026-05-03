from __future__ import annotations

import pytest
from aiogram.types import InlineKeyboardMarkup

from plex_tg_bot.bot.menu import build_main_menu
from plex_tg_bot.i18n import set_lang, t


@pytest.fixture(autouse=True)
def _set_lang() -> None:
    set_lang("en")


def _buttons(markup: InlineKeyboardMarkup) -> list[object]:
    """Flatten inline_keyboard rows into a single list of buttons."""
    return [btn for row in markup.inline_keyboard for btn in row]


def test_no_access_menu() -> None:
    markup = build_main_menu("no_access")
    buttons = _buttons(markup)
    assert len(buttons) == 1

    cb_datas = [b.callback_data for b in buttons]
    assert "request:start" in cb_datas

    request_btn = next(b for b in buttons if b.callback_data == "request:start")
    assert request_btn.text == t("menu.request_access")


def test_pending_menu() -> None:
    """Pending state has no actionable buttons — `/start` text already says
    the request is awaiting admin approval."""
    markup = build_main_menu("pending")
    buttons = _buttons(markup)
    assert len(buttons) == 0


def test_has_access_menu_no_overseerr() -> None:
    markup = build_main_menu("has_access", overseerr_enabled=False)
    buttons = _buttons(markup)
    assert len(buttons) == 2

    cb_datas = [b.callback_data for b in buttons]
    assert "apps:show" in cb_datas

    urls = [b.url for b in buttons]
    assert any(url and "plex.tv" in url for url in urls)

    # No overseerr button
    assert all("overseerr" not in (b.url or "") for b in buttons)


def test_has_access_menu_with_overseerr() -> None:
    overseerr_url = "https://overseerr.example.com"
    markup = build_main_menu(
        "has_access",
        overseerr_enabled=True,
        overseerr_url=overseerr_url,
    )
    buttons = _buttons(markup)
    assert len(buttons) == 3

    cb_datas = [b.callback_data for b in buttons]
    assert "apps:show" in cb_datas

    urls = [b.url for b in buttons]
    assert overseerr_url in urls

    overseerr_btn = next(b for b in buttons if b.url == overseerr_url)
    assert overseerr_btn.text == t("menu.overseerr")


def test_has_access_menu_overseerr_enabled_but_no_url() -> None:
    markup = build_main_menu("has_access", overseerr_enabled=True, overseerr_url=None)
    buttons = _buttons(markup)
    # overseerr_url is None so no overseerr button, only apps + watch
    assert len(buttons) == 2

    cb_datas = [b.callback_data for b in buttons]
    assert "apps:show" in cb_datas
