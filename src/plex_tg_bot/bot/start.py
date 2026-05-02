from __future__ import annotations

from aiogram import Router, types
from aiogram.filters import CommandStart

from plex_tg_bot.bot.menu import State, build_main_menu
from plex_tg_bot.config import Settings
from plex_tg_bot.db import Repo
from plex_tg_bot.i18n import t


async def handle_start(
    message: types.Message,
    repo: Repo,
    settings: Settings,
) -> None:
    u = message.from_user
    if u is None:
        return
    await repo.upsert_user(
        telegram_id=u.id,
        username=u.username,
        display_name=" ".join(filter(None, [u.first_name, u.last_name])) or "",
        language=settings.bot_lang,
    )
    cache = await repo.get_plex_server_cache()
    server_name = settings.plex_server_name or (
        cache["friendly_name"] if cache else "Plex"
    )

    state: State
    if await repo.has_active_access(u.id):
        state = "has_access"
        text = t("welcome.has_access", server_name=server_name)
    elif await repo.get_pending_request_for_user(u.id):
        state = "pending"
        text = t("welcome.pending")
    else:
        state = "no_access"
        text = t("welcome.no_access", server_name=server_name)

    await message.answer(
        text,
        reply_markup=build_main_menu(
            state,
            overseerr_enabled=settings.overseerr_enabled,
            watch_url=settings.watch_url,
            overseerr_url=settings.overseerr_public_url,
        ),
    )


def make_start_router(repo: Repo, settings: Settings) -> Router:
    router = Router(name="start")

    @router.message(CommandStart())
    async def _on_start(message: types.Message) -> None:
        await handle_start(message, repo, settings)

    return router
