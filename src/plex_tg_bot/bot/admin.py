"""Inline-button admin panel.

Triggered by /admin (no args). All subsequent navigation is via
callback_data prefixed `admin:*`. The panel is gated by chat-id: only
messages/callbacks where `chat.id == settings.admin_chat_id` are
honoured (works for both group and DM admins).
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from typing import Protocol

from aiogram import Bot, F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from plex_tg_bot.config import Settings
from plex_tg_bot.db import Repo
from plex_tg_bot.i18n import t

log = logging.getLogger(__name__)

USERS_PAGE_SIZE = 10
PENDING_PAGE_SIZE = 10


class _PlexProto(Protocol):
    async def revoke_share(self, plex_user_id: int) -> None: ...


def _is_admin_chat(chat_id: int, settings: Settings) -> bool:
    return chat_id == settings.admin_chat_id


def _build_panel_kb() -> types.InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.button(text=t("admin.users_button"), callback_data="admin:users:page:1")
    b.button(text=t("admin.pending_button"), callback_data="admin:pending:page:1")
    b.button(text=t("admin.sync_button"), callback_data="admin:sync")
    b.adjust(2, 1)
    return b.as_markup()


async def handle_admin_cmd(
    message: types.Message,
    repo: Repo,
    settings: Settings,
    bot: Bot,
    plex: _PlexProto,
    run_sync: Callable[[], Awaitable[tuple[int, int]]],
) -> None:
    if not _is_admin_chat(message.chat.id, settings):
        await message.answer(t("admin.not_authorized"))
        return
    await message.answer(t("admin.panel_title"), reply_markup=_build_panel_kb())


async def handle_admin_callback(
    cq: types.CallbackQuery,
    repo: Repo,
    settings: Settings,
    bot: Bot,
    plex: _PlexProto,
    run_sync: Callable[[], Awaitable[tuple[int, int]]],
) -> None:
    """Top-level dispatcher for `admin:*` callback_data."""
    if cq.message is None or cq.data is None:
        await cq.answer()
        return
    if not _is_admin_chat(cq.message.chat.id, settings):
        await cq.answer(t("admin.not_authorized"), show_alert=True)
        return

    parts = cq.data.split(":")
    section = parts[1] if len(parts) >= 2 else ""

    if section == "menu":
        await _show_panel(cq)
    elif section == "users":
        await _users_dispatch(cq, repo, settings, bot, plex, parts)
    elif section == "pending":
        await _pending_dispatch(cq, repo, parts)
    elif section == "sync":
        await _do_sync(cq, run_sync)
    else:
        await cq.answer()


async def _show_panel(cq: types.CallbackQuery) -> None:
    if cq.message is None or not hasattr(cq.message, "edit_text"):
        await cq.answer()
        return
    await cq.message.edit_text(t("admin.panel_title"), reply_markup=_build_panel_kb())
    await cq.answer()


async def _users_dispatch(
    cq: types.CallbackQuery,
    repo: Repo,
    settings: Settings,
    bot: Bot,
    plex: _PlexProto,
    parts: list[str],
) -> None:
    # parts: ["admin", "users", "<sub>", ...]
    if len(parts) >= 4 and parts[2] == "page":
        try:
            page = max(1, int(parts[3]))
        except ValueError:
            await cq.answer()
            return
        await _show_users_page(cq, repo, page)
    elif len(parts) >= 4 and parts[2] == "remove":
        await _show_remove_confirm(cq, parts[3])
    elif len(parts) >= 4 and parts[2] == "remove_confirm":
        await _do_remove(cq, repo, settings, bot, plex, parts[3])
    elif len(parts) >= 4 and parts[2] == "remove_cancel":
        await _show_users_page(cq, repo, 1)
    else:
        await cq.answer()


async def _show_users_page(
    cq: types.CallbackQuery, repo: Repo, page: int
) -> None:
    if cq.message is None or not hasattr(cq.message, "edit_text"):
        await cq.answer()
        return
    total = await repo.count_shared_users()
    if total == 0:
        kb = InlineKeyboardBuilder()
        kb.button(text=t("admin.back_button"), callback_data="admin:menu")
        await cq.message.edit_text(t("admin.users_empty"), reply_markup=kb.as_markup())
        await cq.answer()
        return

    total_pages = max(1, (total + USERS_PAGE_SIZE - 1) // USERS_PAGE_SIZE)
    page = min(page, total_pages)
    offset = (page - 1) * USERS_PAGE_SIZE
    rows = await repo.list_shared_users_paginated(offset=offset, limit=USERS_PAGE_SIZE)

    lines = [t("admin.users_header", page=page, total_pages=total_pages, total=total)]
    body_kb = InlineKeyboardBuilder()
    for r in rows:
        emoji = "🟢" if r["status"] == "active" else "🔴"
        label = r["username"] or r["display_name"] or "—"
        lines.append(f"{emoji} @{label} — {r['email']}")
        body_kb.button(text="🗑", callback_data=f"admin:users:remove:{r['email']}")
    body_kb.adjust(*([1] * len(rows)))

    page_kb = InlineKeyboardBuilder()
    if page > 1:
        page_kb.button(text="←", callback_data=f"admin:users:page:{page - 1}")
    page_kb.button(text=f"{page}/{total_pages}", callback_data="admin:users:noop")
    if page < total_pages:
        page_kb.button(text="→", callback_data=f"admin:users:page:{page + 1}")
    page_kb.adjust(3)

    back_kb = InlineKeyboardBuilder()
    back_kb.button(text=t("admin.back_button"), callback_data="admin:menu")

    final = body_kb.as_markup()
    if total_pages > 1:
        final.inline_keyboard.extend(page_kb.as_markup().inline_keyboard)
    final.inline_keyboard.extend(back_kb.as_markup().inline_keyboard)

    await cq.message.edit_text("\n".join(lines), reply_markup=final)
    await cq.answer()


async def _show_remove_confirm(cq: types.CallbackQuery, email: str) -> None:
    if cq.message is None or not hasattr(cq.message, "edit_text"):
        await cq.answer()
        return
    text = t("admin.remove_confirm", email=email)
    kb = InlineKeyboardBuilder()
    kb.button(
        text=t("admin.remove_yes"),
        callback_data=f"admin:users:remove_confirm:{email}",
    )
    kb.button(
        text=t("admin.remove_cancel"),
        callback_data=f"admin:users:remove_cancel:{email}",
    )
    kb.adjust(2)
    await cq.message.edit_text(text, reply_markup=kb.as_markup())
    await cq.answer()


def _retry_kb(email: str) -> types.InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(
        text=t("admin.retry_button"),
        callback_data=f"admin:users:remove_confirm:{email}",
    )
    kb.button(text=t("admin.back_button"), callback_data="admin:users:page:1")
    kb.adjust(2)
    return kb.as_markup()


async def _do_remove(
    cq: types.CallbackQuery,
    repo: Repo,
    settings: Settings,
    bot: Bot,
    plex: _PlexProto,
    email: str,
) -> None:
    """Atomic: Plex revoke first, then DB delete + DM. On Plex error: nothing
    is mutated, retry card is shown."""
    if cq.message is None or not hasattr(cq.message, "edit_text"):
        await cq.answer()
        return

    # 0. confirm row exists
    row = await repo.get_shared_user_by_email(email)
    if row is None:
        kb = InlineKeyboardBuilder()
        kb.button(text=t("admin.back_button"), callback_data="admin:menu")
        await cq.message.edit_text(
            t("admin.remove_not_found"), reply_markup=kb.as_markup()
        )
        await cq.answer()
        return

    # 1. Plex revoke — friends endpoint, identified by stored plex_user_id.
    from plex_tg_bot.services.plex import PlexAuthError, PlexUnreachable

    plex_user_id = int(row.get("plex_user_id") or 0)
    try:
        await plex.revoke_share(plex_user_id)
    except PlexAuthError as e:
        log.error("revoke %s: PLEX_TOKEN rejected (401): %s", email, e)
        await cq.message.edit_text(
            t("admin.remove_plex_auth_error"), reply_markup=_retry_kb(email)
        )
        await cq.answer()
        return
    except PlexUnreachable as e:
        log.warning("revoke %s: plex error %s", email, e)
        await cq.message.edit_text(
            t("admin.remove_plex_unreachable"), reply_markup=_retry_kb(email)
        )
        await cq.answer()
        return

    # 2. DB delete
    await repo.delete_shared_user(email)

    # 3. user DM (best effort)
    if row.get("telegram_id"):
        try:
            await bot.send_message(int(row["telegram_id"]), t("notify_user.revoked"))
        except Exception as e:
            log.warning("DM revoked-user %s failed: %s", email, e)

    # 4. success card
    kb = InlineKeyboardBuilder()
    kb.button(text=t("admin.back_button"), callback_data="admin:users:page:1")
    await cq.message.edit_text(
        t("admin.remove_success", email=email),
        reply_markup=kb.as_markup(),
    )
    await cq.answer()


async def _pending_dispatch(
    cq: types.CallbackQuery, repo: Repo, parts: list[str]
) -> None:
    if len(parts) >= 4 and parts[2] == "page":
        try:
            page = max(1, int(parts[3]))
        except ValueError:
            await cq.answer()
            return
        await _show_pending_page(cq, repo, page)
    else:
        await cq.answer()


async def _show_pending_page(
    cq: types.CallbackQuery, repo: Repo, page: int
) -> None:
    if cq.message is None or not hasattr(cq.message, "edit_text"):
        await cq.answer()
        return
    rows_all = await repo.list_pending_requests()
    total = len(rows_all)
    if total == 0:
        kb = InlineKeyboardBuilder()
        kb.button(text=t("admin.back_button"), callback_data="admin:menu")
        await cq.message.edit_text(t("admin.pending_empty"), reply_markup=kb.as_markup())
        await cq.answer()
        return
    total_pages = max(1, (total + PENDING_PAGE_SIZE - 1) // PENDING_PAGE_SIZE)
    page = min(page, total_pages)
    rows = rows_all[(page - 1) * PENDING_PAGE_SIZE: page * PENDING_PAGE_SIZE]

    lines = [
        t("admin.pending_header_paginated",
          page=page, total_pages=total_pages, total=total)
    ]
    for r in rows:
        lines.append(f"#{r['id']} {r['email']} — {r['referrer']}")

    kb = InlineKeyboardBuilder()
    if page > 1:
        kb.button(text="←", callback_data=f"admin:pending:page:{page - 1}")
    kb.button(text=f"{page}/{total_pages}", callback_data="admin:pending:noop")
    if page < total_pages:
        kb.button(text="→", callback_data=f"admin:pending:page:{page + 1}")
    kb.button(text=t("admin.back_button"), callback_data="admin:menu")
    kb.adjust(3, 1)

    await cq.message.edit_text("\n".join(lines), reply_markup=kb.as_markup())
    await cq.answer()


async def _do_sync(
    cq: types.CallbackQuery,
    run_sync: Callable[[], Awaitable[tuple[int, int]]],
) -> None:
    if cq.message is None or not hasattr(cq.message, "edit_text"):
        await cq.answer()
        return
    active, revoked = await run_sync()
    text = t("admin.sync_done", active=active, revoked=revoked)
    kb = InlineKeyboardBuilder()
    kb.button(text=t("admin.back_button"), callback_data="admin:menu")
    await cq.message.edit_text(text, reply_markup=kb.as_markup())
    await cq.answer()


def make_admin_router(
    repo: Repo,
    settings: Settings,
    bot: Bot,
    plex: _PlexProto,
    run_sync: Callable[[], Awaitable[tuple[int, int]]],
) -> Router:
    router = Router(name="admin")

    @router.message(Command("admin"))
    async def _on_cmd(message: types.Message) -> None:
        await handle_admin_cmd(message, repo, settings, bot, plex, run_sync)

    @router.callback_query(F.data.startswith("admin:"))
    async def _on_cb(cq: types.CallbackQuery) -> None:
        await handle_admin_callback(cq, repo, settings, bot, plex, run_sync)

    return router
