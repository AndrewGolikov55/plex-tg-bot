"""Approve/reject callback handlers with transactional rollback on Plex failure."""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from aiogram import Bot, F, Router, types
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from plex_tg_bot.bot.states import RejectFSM
from plex_tg_bot.config import Settings
from plex_tg_bot.db import Repo
from plex_tg_bot.i18n import t
from plex_tg_bot.services.overseerr import OverseerrClient, OverseerrError
from plex_tg_bot.services.plex import PlexAlreadyShared, PlexAuthError, PlexClient, PlexUnreachable

if TYPE_CHECKING:
    pass

log = logging.getLogger(__name__)

_ACCEPT_URL_TEMPLATE = (
    "https://app.plex.tv/desktop/#!/sharing-invite?inviteToken={token}"
)


def _build_approved_dm(
    server_name: str, email: str, invite_token: str | None
) -> tuple[str, types.InlineKeyboardMarkup]:
    """Compose the DM sent to the user after approve.

    With invite_token: rich text + [Accept invite] URL button + [Get apps].
    Without: text-only fallback + [Get apps] only.
    """
    kb = InlineKeyboardBuilder()
    if invite_token:
        text = t(
            "notify_user.approved", server_name=server_name, email=email
        )
        kb.button(
            text=t("notify_user.accept_invite_button"),
            url=_ACCEPT_URL_TEMPLATE.format(token=invite_token),
        )
    else:
        text = t(
            "notify_user.approved_no_token",
            server_name=server_name,
            email=email,
        )
    kb.button(text=t("notify_user.apps_button"), callback_data="apps:show")
    kb.adjust(1)
    return text, kb.as_markup()


async def handle_approve(
    cq: types.CallbackQuery,
    repo: Repo,
    bot: Bot,
    settings: Settings,
    plex: PlexClient,
    overseerr: OverseerrClient | None,
) -> None:
    """Core approve logic — separated from the router for testability."""
    admin = cq.from_user
    rid = int((cq.data or "").split(":")[1])
    now = int(time.time())

    admin_label = f"@{admin.username}" if admin.username else admin.first_name or str(admin.id)

    # ── Step 1: Atomic claim ────────────────────────────────────────────────
    claimed = await repo.claim_request(rid, admin.id, now)
    if not claimed:
        # Already handled — find out who handled it (best-effort)
        req = await repo.get_request(rid)
        await cq.answer(t("admin.already_handled", admin=admin_label), show_alert=True)
        return

    # ── Step 2: Fetch request and server cache ──────────────────────────────
    req = await repo.get_request(rid)
    if req is None:
        await repo.rollback_claim(rid)
        log.error("approve: request %d disappeared after claim", rid)
        await cq.answer(t("errors.plex_temporary"), show_alert=True)
        return

    cache = await repo.get_plex_server_cache()
    if cache is None:
        await repo.rollback_claim(rid)
        log.error("approve: plex_server_cache is empty, cannot share")
        await cq.answer(t("errors.plex_temporary"), show_alert=True)
        return

    email: str = req["email"]
    telegram_id: int = req["telegram_id"]
    machine_identifier: str = cache["machine_identifier"]

    # ── Step 3: Plex share ──────────────────────────────────────────────────
    plex_user_id: int
    invite_token: str | None = None
    try:
        plex_user_id, invite_token = await plex.share_server(
            machine_identifier=machine_identifier,
            email=email,
            library_section_ids=settings.shared_library_ids,
            allow_sync=settings.allow_sync,
            allow_camera_upload=settings.allow_camera_upload,
            allow_channels=settings.allow_channels,
        )
    except PlexAlreadyShared as e:
        plex_user_id = int(e.args[0]) if e.args else 0
        invite_token = e.args[1] if len(e.args) >= 2 else None
        log.info("approve: %s already shared (plex_user_id=%d)", email, plex_user_id)
    except (PlexAuthError, PlexUnreachable) as e:
        log.warning("approve: Plex error for request %d: %s", rid, e)
        await repo.rollback_claim(rid)
        await cq.answer(t("errors.plex_temporary"), show_alert=True)
        return

    # Fallback: if POST didn't surface the token, look it up via list_shared.
    if invite_token is None:
        try:
            items = await plex.list_shared(machine_identifier)
            for item in items:
                if item.get("email") == email:
                    tok = item.get("invite_token")
                    if isinstance(tok, str) and tok:
                        invite_token = tok
                    break
        except (PlexAuthError, PlexUnreachable) as e:
            log.warning(
                "approve %d: list_shared fallback for invite_token failed: %s",
                rid,
                e,
            )

    # ── Step 4: Upsert shared user ──────────────────────────────────────────
    await repo.upsert_shared_user(
        email=email,
        telegram_id=telegram_id,
        plex_user_id=plex_user_id,
        shared_at=now,
        last_seen_in_plex=now,
    )

    # ── Step 5: Finalize approval ───────────────────────────────────────────
    await repo.finalize_approve(rid)

    # ── Step 6: Best-effort Overseerr ───────────────────────────────────────
    if overseerr is not None and plex_user_id:
        try:
            await overseerr.import_from_plex([plex_user_id])
        except OverseerrError as e:
            log.warning("approve: Overseerr import failed (non-fatal): %s", e)

    # ── Step 7: Edit admin card ─────────────────────────────────────────────
    time_str = datetime.fromtimestamp(now, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    try:
        await bot.edit_message_text(
            chat_id=req["admin_chat_id"],
            message_id=req["admin_msg_id"],
            text=t("admin.approved_by", admin=admin_label, time=time_str),
        )
    except Exception as e:
        log.warning("approve: could not edit admin card for request %d: %s", rid, e)

    # ── Step 8: DM user ─────────────────────────────────────────────────────
    server_name = settings.plex_server_name or (
        cache["friendly_name"] if cache else "Plex"
    )
    dm_text, dm_kb = _build_approved_dm(
        server_name=server_name,
        email=email,
        invite_token=invite_token,
    )
    try:
        await bot.send_message(telegram_id, dm_text, reply_markup=dm_kb)
    except Exception as e:
        log.warning("approve: could not DM user %d: %s", telegram_id, e)

    # ── Step 9: Stop spinner ────────────────────────────────────────────────
    await cq.answer()


async def _finalize_reject(
    rid: int,
    reason: str | None,
    admin: Any,
    repo: Repo,
    bot: Bot,
) -> None:
    """Finalize a reject: update DB, edit admin card, DM the user."""
    req = await repo.get_request(rid)
    if req is None:
        return
    await repo.finalize_reject(rid, reason)
    time_str = datetime.now(UTC).strftime("%H:%M UTC")
    admin_label = f"@{admin.username}" if admin.username else admin.first_name or "admin"
    try:
        await bot.edit_message_text(
            chat_id=req["admin_chat_id"],
            message_id=req["admin_msg_id"],
            text=t("admin.rejected_by", admin=admin_label, time=time_str),
        )
    except Exception as e:
        log.warning("reject: edit admin card failed: %s", e)
    key = "notify_user.rejected" if reason else "notify_user.rejected_no_reason"
    try:
        if reason:
            await bot.send_message(req["telegram_id"], t(key, reason=reason))
        else:
            await bot.send_message(req["telegram_id"], t(key))
    except Exception as e:
        log.warning("reject: DM user failed: %s", e)


async def handle_reject(
    cq: types.CallbackQuery,
    repo: Repo,
    bot: Bot,
    settings: Settings,
    state: FSMContext,
) -> None:
    """Reject callback — claims request and enters FSM to collect reason."""
    if cq.data is None or cq.from_user is None or cq.message is None:
        return
    rid = int(cq.data.split(":", 1)[1])
    admin = cq.from_user
    claimed = await repo.claim_request(rid, decided_by=admin.id, decided_at=int(time.time()))
    if not claimed:
        admin_label = admin.username or admin.first_name or str(admin.id)
        await cq.answer(
            t("admin.already_handled", admin=admin_label),
            show_alert=True,
        )
        return
    await state.set_state(RejectFSM.awaiting_reason)
    await state.update_data(
        request_id=rid,
        card_msg_id=cq.message.message_id,
        admin_chat_id=cq.message.chat.id,
    )
    admin_label = admin.username or admin.first_name or "admin"
    await bot.send_message(
        cq.message.chat.id,
        t("admin.ask_reject_reason", admin=admin_label),
        reply_to_message_id=cq.message.message_id,
    )
    await cq.answer()


async def handle_reject_cancel(
    message: types.Message,
    state: FSMContext,
    repo: Repo,
) -> None:
    """Admin /cancel → rollback claim and clear FSM."""
    data = await state.get_data()
    rid = int(data.get("request_id", 0))
    if rid:
        await repo.rollback_claim(rid)
    await state.clear()


async def handle_reject_skip(
    message: types.Message,
    state: FSMContext,
    repo: Repo,
    bot: Bot,
) -> None:
    """Admin /skip → finalize with reason=None."""
    if message.from_user is None:
        return
    data = await state.get_data()
    rid = int(data.get("request_id", 0))
    await _finalize_reject(rid, None, message.from_user, repo, bot)
    await state.clear()


async def handle_reject_reason(
    message: types.Message,
    state: FSMContext,
    repo: Repo,
    bot: Bot,
) -> None:
    """Admin replies with reason text (must be reply to the card message)."""
    if message.from_user is None or message.reply_to_message is None:
        return
    data = await state.get_data()
    if message.reply_to_message.message_id != data.get("card_msg_id"):
        return  # ignore replies to other messages
    rid = int(data.get("request_id", 0))
    await _finalize_reject(rid, message.text or "", message.from_user, repo, bot)
    await state.clear()


def make_approve_router(
    repo: Repo,
    bot: Bot,
    settings: Settings,
    plex: PlexClient,
    overseerr: OverseerrClient | None,
) -> Router:
    router = Router(name="approve")

    @router.callback_query(F.data.startswith("approve:"))
    async def _on_approve(cq: types.CallbackQuery) -> None:
        await handle_approve(cq, repo, bot, settings, plex, overseerr)

    @router.callback_query(F.data.startswith("reject:"))
    async def _on_reject(cq: types.CallbackQuery, state: FSMContext) -> None:
        await handle_reject(cq, repo, bot, settings, state)

    @router.message(StateFilter(RejectFSM.awaiting_reason), F.text == "/cancel")
    async def _on_reject_cancel(message: types.Message, state: FSMContext) -> None:
        await handle_reject_cancel(message, state, repo)

    @router.message(StateFilter(RejectFSM.awaiting_reason), F.text == "/skip")
    async def _on_reject_skip(message: types.Message, state: FSMContext) -> None:
        await handle_reject_skip(message, state, repo, bot)

    @router.message(StateFilter(RejectFSM.awaiting_reason), F.text)
    async def _on_reject_reason(message: types.Message, state: FSMContext) -> None:
        await handle_reject_reason(message, state, repo, bot)

    return router
