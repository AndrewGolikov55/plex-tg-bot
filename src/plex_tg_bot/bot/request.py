from __future__ import annotations

from aiogram import Bot, F, Router, types
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.utils.keyboard import InlineKeyboardBuilder

from plex_tg_bot.bot.states import RequestFSM
from plex_tg_bot.config import Settings
from plex_tg_bot.db import Repo
from plex_tg_bot.i18n import t
from plex_tg_bot.services.email import is_valid_email


async def handle_request_cmd(
    message: types.Message, state: FSMContext, repo: Repo
) -> None:
    u = message.from_user
    if u is None:
        return
    if await repo.has_active_access(u.id):
        await message.answer(t("request.already_have_access"))
        return
    if await repo.get_pending_request_for_user(u.id):
        await message.answer(t("request.already_pending"))
        return
    await state.set_state(RequestFSM.awaiting_email)
    await message.answer(t("request.ask_email"))


async def handle_request_callback(
    cq: types.CallbackQuery, state: FSMContext, repo: Repo
) -> None:
    u = cq.from_user
    if u is None or cq.message is None:
        await cq.answer()
        return
    if await repo.has_active_access(u.id):
        await cq.message.answer(t("request.already_have_access"))
        await cq.answer()
        return
    if await repo.get_pending_request_for_user(u.id):
        await cq.message.answer(t("request.already_pending"))
        await cq.answer()
        return
    await state.set_state(RequestFSM.awaiting_email)
    await cq.message.answer(t("request.ask_email"))
    await cq.answer()


async def handle_email_text(
    message: types.Message, state: FSMContext
) -> None:
    text = (message.text or "").strip()
    if not is_valid_email(text):
        await message.answer(t("request.invalid_email"))
        return
    await state.update_data(email=text)
    await state.set_state(RequestFSM.awaiting_referrer)
    await message.answer(t("request.ask_referrer"))


async def handle_referrer_text(
    message: types.Message,
    state: FSMContext,
    repo: Repo,
    bot: Bot,
    settings: Settings,
) -> None:
    u = message.from_user
    if u is None:
        return
    data = await state.get_data()
    email = str(data.get("email", ""))
    referrer = (message.text or "").strip()

    rid = await repo.create_request(
        telegram_id=u.id,
        email=email,
        referrer=referrer,
        admin_chat_id=settings.admin_chat_id,
        admin_msg_id=None,
    )

    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Approve", callback_data=f"approve:{rid}")
    kb.button(text="❌ Reject", callback_data=f"reject:{rid}")
    kb.adjust(2)

    username = f"@{u.username}" if u.username else u.first_name or "user"
    sent = await bot.send_message(
        chat_id=settings.admin_chat_id,
        text=t(
            "admin.request_card",
            user=username,
            tg_id=u.id,
            email=email,
            referrer=referrer,
        ),
        reply_markup=kb.as_markup(),
    )
    await repo.set_request_admin_msg_id(rid, sent.message_id)

    await state.clear()
    await message.answer(t("request.submitted"))


def make_request_router(repo: Repo, bot: Bot, settings: Settings) -> Router:
    router = Router(name="request")

    @router.message(Command("request"))
    async def _on_request(message: types.Message, state: FSMContext) -> None:
        await handle_request_cmd(message, state, repo)

    @router.callback_query(F.data == "request:start")
    async def _on_request_cb(cq: types.CallbackQuery, state: FSMContext) -> None:
        await handle_request_callback(cq, state, repo)

    @router.message(StateFilter(RequestFSM.awaiting_email), F.text)
    async def _on_email(message: types.Message, state: FSMContext) -> None:
        await handle_email_text(message, state)

    @router.message(StateFilter(RequestFSM.awaiting_referrer), F.text)
    async def _on_ref(message: types.Message, state: FSMContext) -> None:
        await handle_referrer_text(message, state, repo, bot, settings)

    return router
