"""Bot profile setup — description, short_description, commands menu.

Tests verify the public/admin command list shapes and that
setup_bot_profile gracefully handles Telegram API failures.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from plex_tg_bot.bot.profile import (
    _admin_commands,
    _public_commands,
    setup_bot_profile,
)
from plex_tg_bot.config import Settings
from plex_tg_bot.i18n import set_lang, t


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("ADMIN_CHAT_ID", "-100")
    monkeypatch.setenv("PLEX_TOKEN", "p")
    monkeypatch.setenv("BOT_LANG", "en")
    s = Settings()  # type: ignore[call-arg]
    set_lang("en")
    return s


def test_public_commands_excludes_admin() -> None:
    names = {c.command for c in _public_commands()}
    assert names == {"start", "request", "help"}
    # Each command has a localized description
    for c in _public_commands():
        assert c.description, f"{c.command} has empty description"


def test_admin_commands_includes_public_plus_admin() -> None:
    names = {c.command for c in _admin_commands()}
    assert names == {"start", "request", "help", "admin"}


def test_admin_command_description_uses_locale_key() -> None:
    cmds = _admin_commands()
    admin = next(c for c in cmds if c.command == "admin")
    assert admin.description == t("commands.admin")


async def test_setup_bot_profile_calls_all_three_apis(settings: Settings) -> None:
    bot = AsyncMock()
    await setup_bot_profile(bot, settings)
    bot.set_my_description.assert_awaited_once()
    bot.set_my_short_description.assert_awaited_once()
    # set_my_commands called twice — once for default scope, once for admin chat
    assert bot.set_my_commands.await_count == 2


async def test_setup_bot_profile_admin_scope_targets_admin_chat_id(
    settings: Settings,
) -> None:
    from aiogram.types import BotCommandScopeChat

    bot = AsyncMock()
    await setup_bot_profile(bot, settings)
    # Find the admin-scope call
    admin_call = next(
        c
        for c in bot.set_my_commands.call_args_list
        if isinstance(c.kwargs.get("scope"), BotCommandScopeChat)
    )
    assert admin_call.kwargs["scope"].chat_id == -100


async def test_setup_bot_profile_swallows_description_errors(
    settings: Settings,
) -> None:
    """If set_my_description raises (e.g. flood control), we still try commands."""
    bot = AsyncMock()
    bot.set_my_description.side_effect = Exception("flood")
    bot.set_my_short_description.side_effect = Exception("flood")
    # Should NOT raise out of setup
    await setup_bot_profile(bot, settings)
    # Commands still attempted
    assert bot.set_my_commands.await_count == 2


async def test_setup_bot_profile_swallows_commands_errors(
    settings: Settings,
) -> None:
    bot = AsyncMock()
    bot.set_my_commands.side_effect = Exception("flood")
    # Should NOT raise
    await setup_bot_profile(bot, settings)
