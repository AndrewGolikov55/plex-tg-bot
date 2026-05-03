"""Inline-button admin panel — all interactions are CallbackQueries.

Tests use module-level handler functions (handle_admin_cmd,
handle_admin_callback) directly with Fake CallbackQuery / Message /
FSMContext-style stubs. No live aiogram dispatcher needed.
"""
from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio

from plex_tg_bot.bot.admin import (
    handle_admin_callback,
    handle_admin_cmd,
)
from plex_tg_bot.config import Settings
from plex_tg_bot.db import Repo
from plex_tg_bot.i18n import set_lang, t


@pytest_asyncio.fixture
async def repo(tmp_path: Path) -> AsyncGenerator[Repo, None]:
    r = Repo(str(tmp_path / "test.sqlite"))
    await r.connect()
    yield r
    await r.close()


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for k, v in {
        "TELEGRAM_BOT_TOKEN": "t",
        "ADMIN_CHAT_ID": "-100",
        "PLEX_TOKEN": "p",
        "BOT_LANG": "en",
    }.items():
        monkeypatch.setenv(k, v)
    s = Settings()  # type: ignore[call-arg]
    set_lang("en")
    return s


class FakeMessage:
    def __init__(self, chat_id: int) -> None:
        self.chat = SimpleNamespace(id=chat_id)
        self.message_id = 999
        self.answer_calls: list[dict[str, Any]] = []
        self.edit_calls: list[dict[str, Any]] = []

    async def answer(
        self, text: str, reply_markup: object = None, parse_mode: str | None = None
    ) -> None:
        self.answer_calls.append(
            {"text": text, "reply_markup": reply_markup, "parse_mode": parse_mode}
        )

    async def edit_text(
        self, text: str, reply_markup: object = None, parse_mode: str | None = None
    ) -> None:
        self.edit_calls.append(
            {"text": text, "reply_markup": reply_markup, "parse_mode": parse_mode}
        )


class FakeCQ:
    def __init__(self, chat_id: int, data: str, user_id: int = 7) -> None:
        self.from_user = SimpleNamespace(id=user_id, username="admin1")
        self.message = FakeMessage(chat_id)
        self.data = data
        self.answer_calls: list[dict[str, Any]] = []

    async def answer(
        self, text: str | None = None, show_alert: bool = False
    ) -> None:
        self.answer_calls.append({"text": text, "show_alert": show_alert})


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_message(self, chat_id: int, text: str) -> SimpleNamespace:
        self.sent.append({"chat_id": chat_id, "text": text})
        return SimpleNamespace(message_id=1)


class FakePlex:
    def __init__(self) -> None:
        self.revoke_share = AsyncMock()


async def _stub_run_sync() -> tuple[int, int]:
    return (5, 1)


# ---- /admin opens panel ----


async def test_admin_command_from_admin_chat_opens_panel(
    repo: Repo, settings: Settings
) -> None:
    msg = FakeMessage(-100)
    await handle_admin_cmd(msg, repo, settings, FakeBot(), FakePlex(), _stub_run_sync)  # type: ignore[arg-type]
    assert msg.answer_calls
    assert msg.answer_calls[-1]["text"] == t("admin.panel_title")
    kb = msg.answer_calls[-1]["reply_markup"]
    labels = [b.text for row in kb.inline_keyboard for b in row]
    assert t("admin.users_button") in labels
    assert t("admin.pending_button") in labels
    assert t("admin.sync_button") in labels


async def test_admin_command_from_non_admin_chat_replies_not_authorized(
    repo: Repo, settings: Settings
) -> None:
    msg = FakeMessage(123)
    await handle_admin_cmd(msg, repo, settings, FakeBot(), FakePlex(), _stub_run_sync)  # type: ignore[arg-type]
    assert msg.answer_calls[-1]["text"] == t("admin.not_authorized")


# ---- users page ----


async def test_users_page_empty_state(repo: Repo, settings: Settings) -> None:
    cq = FakeCQ(-100, "admin:users:page:1")
    await handle_admin_callback(cq, repo, settings, FakeBot(), FakePlex(), _stub_run_sync)  # type: ignore[arg-type]
    last = cq.message.edit_calls[-1]
    assert last["text"] == t("admin.users_empty")


async def test_users_page_first_page_with_three_rows(
    repo: Repo, settings: Settings
) -> None:
    base = int(time.time())
    await repo.upsert_user(1, "alice", "Alice", "en")
    await repo.upsert_user(2, "bob", "Bob", "en")
    await repo.upsert_user(3, "carol", "Carol", "en")
    await repo.upsert_shared_user("a@e.com", 1, 100, base, base)
    await repo.upsert_shared_user("b@e.com", 2, 101, base - 1, base - 1)
    await repo.upsert_shared_user("c@e.com", 3, 102, base - 2, base - 2)

    cq = FakeCQ(-100, "admin:users:page:1")
    await handle_admin_callback(cq, repo, settings, FakeBot(), FakePlex(), _stub_run_sync)  # type: ignore[arg-type]
    last = cq.message.edit_calls[-1]
    text = last["text"]
    assert "alice" in text and "bob" in text and "carol" in text
    assert "🟢" in text
    kb = last["reply_markup"]
    callbacks = [
        b.callback_data for row in kb.inline_keyboard for b in row if b.callback_data
    ]
    assert any(cd == "admin:users:remove:a@e.com" for cd in callbacks)
    assert any(cd == "admin:menu" for cd in callbacks)


async def test_users_page_pagination_15_rows(repo: Repo, settings: Settings) -> None:
    now = int(time.time())
    for i in range(15):
        await repo.upsert_user(100 + i, f"u{i}", f"U{i}", "en")
        await repo.upsert_shared_user(
            f"u{i}@e.com", 100 + i, 1000 + i, now - i, now - i
        )

    cq1 = FakeCQ(-100, "admin:users:page:1")
    await handle_admin_callback(cq1, repo, settings, FakeBot(), FakePlex(), _stub_run_sync)  # type: ignore[arg-type]
    text1 = cq1.message.edit_calls[-1]["text"]
    assert "page 1/2" in text1
    kb1 = cq1.message.edit_calls[-1]["reply_markup"]
    cbs = [b.callback_data for r in kb1.inline_keyboard for b in r if b.callback_data]
    assert "admin:users:page:2" in cbs

    cq2 = FakeCQ(-100, "admin:users:page:2")
    await handle_admin_callback(cq2, repo, settings, FakeBot(), FakePlex(), _stub_run_sync)  # type: ignore[arg-type]
    text2 = cq2.message.edit_calls[-1]["text"]
    assert "page 2/2" in text2


async def test_users_page_clamps_overshoot(repo: Repo, settings: Settings) -> None:
    now = int(time.time())
    await repo.upsert_user(1, "a", "A", "en")
    await repo.upsert_shared_user("a@e.com", 1, 100, now, now)
    cq = FakeCQ(-100, "admin:users:page:99")
    await handle_admin_callback(cq, repo, settings, FakeBot(), FakePlex(), _stub_run_sync)  # type: ignore[arg-type]
    text = cq.message.edit_calls[-1]["text"]
    assert "page 1/1" in text


# ---- pending page + sync + menu + non-admin block ----


async def test_pending_page_empty(repo: Repo, settings: Settings) -> None:
    cq = FakeCQ(-100, "admin:pending:page:1")
    await handle_admin_callback(cq, repo, settings, FakeBot(), FakePlex(), _stub_run_sync)  # type: ignore[arg-type]
    last = cq.message.edit_calls[-1]
    assert last["text"] == t("admin.pending_empty")


async def test_pending_page_with_two_requests(
    repo: Repo, settings: Settings
) -> None:
    await repo.upsert_user(42, "v", "V", "en")
    await repo.create_request(42, "vasya@e.com", "From Andrew", -100, None)
    await repo.create_request(42, "petya@e.com", "Discord", -100, None)
    cq = FakeCQ(-100, "admin:pending:page:1")
    await handle_admin_callback(cq, repo, settings, FakeBot(), FakePlex(), _stub_run_sync)  # type: ignore[arg-type]
    text = cq.message.edit_calls[-1]["text"]
    assert "vasya@e.com" in text and "petya@e.com" in text
    assert "From Andrew" in text


async def test_admin_sync_callback_invokes_run_sync_and_renders_result(
    repo: Repo, settings: Settings
) -> None:
    cq = FakeCQ(-100, "admin:sync")
    sync_called = AsyncMock(return_value=(7, 2))
    await handle_admin_callback(cq, repo, settings, FakeBot(), FakePlex(), sync_called)  # type: ignore[arg-type]
    sync_called.assert_awaited_once()
    text = cq.message.edit_calls[-1]["text"]
    assert "7" in text and "2" in text


async def test_admin_menu_callback_returns_to_panel(
    repo: Repo, settings: Settings
) -> None:
    cq = FakeCQ(-100, "admin:menu")
    await handle_admin_callback(cq, repo, settings, FakeBot(), FakePlex(), _stub_run_sync)  # type: ignore[arg-type]
    last = cq.message.edit_calls[-1]
    assert last["text"] == t("admin.panel_title")


async def test_admin_callback_from_non_admin_chat_blocks(
    repo: Repo, settings: Settings
) -> None:
    cq = FakeCQ(123, "admin:users:page:1")
    await handle_admin_callback(cq, repo, settings, FakeBot(), FakePlex(), _stub_run_sync)  # type: ignore[arg-type]
    assert cq.message.edit_calls == []
    assert cq.answer_calls[-1]["show_alert"] is True
    assert cq.answer_calls[-1]["text"] == t("admin.not_authorized")
