"""Admin commands: /admin list|pending|sync."""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from aiogram import Router, types
from aiogram.filters import Command, CommandObject

from plex_tg_bot.config import Settings
from plex_tg_bot.db import Repo
from plex_tg_bot.i18n import t


async def handle_admin(
    message: types.Message,
    command: CommandObject,
    repo: Repo,
    settings: Settings,
    run_sync: Callable[[], Awaitable[tuple[int, int]]],
) -> None:
    """Core admin handler — factored out for testability."""
    if message.chat.id != settings.admin_chat_id:
        await message.answer(t("admin.not_authorized"))
        return

    parts = (command.args or "").strip().split()
    sub = parts[0] if parts else ""

    if sub == "list":
        users = await repo.list_users_overview()
        lines = [t("admin.list_header")]
        for u in users:
            lines.append(
                f"- {u['username'] or u['display_name']} | "
                f"{u['email'] or '-'} | {u['shared_status'] or '-'}"
            )
        await message.answer("\n".join(lines))

    elif sub == "pending":
        reqs = await repo.list_pending_requests()
        lines = [t("admin.pending_header")]
        for r in reqs:
            lines.append(f"- #{r['id']} {r['email']} ({r['referrer']})")
        await message.answer("\n".join(lines))

    elif sub == "sync":
        active, revoked = await run_sync()
        await message.answer(t("admin.sync_done", active=active, revoked=revoked))

    else:
        await message.answer("Usage: /admin list|pending|sync")


def make_admin_router(
    repo: Repo,
    settings: Settings,
    run_sync: Callable[[], Awaitable[tuple[int, int]]],
) -> Router:
    router = Router(name="admin")

    @router.message(Command("admin"))
    async def _on(message: types.Message, command: CommandObject) -> None:
        await handle_admin(message, command, repo, settings, run_sync)

    return router
