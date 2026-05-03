"""Bot profile setup: description, short description, slash-commands menu.

Called once at startup. Telegram persists these server-side, so we don't
have to do anything per-message after this. Commands are registered with
two scopes:

- BotCommandScopeDefault — visible in any chat: /start, /request, /help.
- BotCommandScopeChat(chat_id=ADMIN_CHAT_ID) — adds /admin only in the
  configured admin chat (group or DM). Telegram clients honor the scope;
  ordinary users never see the /admin entry.

Authorization is still enforced by chat-id check inside admin handlers
— Telegram scope is just UX hinting, not a security boundary.
"""
from __future__ import annotations

import logging

from aiogram import Bot
from aiogram.types import (
    BotCommand,
    BotCommandScopeChat,
    BotCommandScopeDefault,
)

from plex_tg_bot.config import Settings
from plex_tg_bot.i18n import t

log = logging.getLogger(__name__)


def _public_commands() -> list[BotCommand]:
    """Commands visible to every Telegram user."""
    return [
        BotCommand(command="start", description=t("commands.start")),
        BotCommand(command="request", description=t("commands.request")),
        BotCommand(command="help", description=t("commands.help")),
    ]


def _admin_commands() -> list[BotCommand]:
    """Commands visible inside the admin chat (group or DM). Includes /admin."""
    return [
        *_public_commands(),
        BotCommand(command="admin", description=t("commands.admin")),
    ]


async def setup_bot_profile(bot: Bot, settings: Settings) -> None:
    """Push description, short_description, and slash-commands menu to Telegram.

    Idempotent: Telegram only updates if the value actually changed.
    Failures are logged but don't crash startup — the bot still works,
    just without the polished profile."""
    try:
        await bot.set_my_description(t("bot_meta.description"))
        await bot.set_my_short_description(t("bot_meta.short_description"))
    except Exception as e:
        log.warning("set_my_description failed: %s", e)

    try:
        await bot.set_my_commands(
            _public_commands(),
            scope=BotCommandScopeDefault(),
        )
        await bot.set_my_commands(
            _admin_commands(),
            scope=BotCommandScopeChat(chat_id=settings.admin_chat_id),
        )
    except Exception as e:
        log.warning("set_my_commands failed: %s", e)
