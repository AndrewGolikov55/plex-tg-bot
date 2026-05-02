"""Tests for /admin list|pending|sync command handler."""
from __future__ import annotations

import pathlib
import time
from unittest.mock import AsyncMock

import pytest

from plex_tg_bot.bot.admin import handle_admin
from plex_tg_bot.config import Settings
from plex_tg_bot.db.repo import Repo
from plex_tg_bot.i18n import set_lang, t

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeChat:
    def __init__(self, chat_id: int) -> None:
        self.id = chat_id


class MockMessage:
    def __init__(self, chat_id: int, text: str = "/admin") -> None:
        self.chat = FakeChat(chat_id)
        self.text = text
        self.answer_calls: list[str] = []

    async def answer(self, text: str) -> None:
        self.answer_calls.append(text)


class FakeCmd:
    def __init__(self, args: str | None) -> None:
        self.args = args


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _set_lang() -> None:
    set_lang("en")


@pytest.fixture
async def repo(tmp_path: pathlib.Path) -> Repo:  # type: ignore[misc]
    r = Repo(str(tmp_path / "test.sqlite"))
    await r.connect()
    yield r  # type: ignore[misc]
    await r.close()


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for k, v in {
        "TELEGRAM_BOT_TOKEN": "t",
        "ADMIN_CHAT_ID": "-100123",
        "PLEX_TOKEN": "p",
        "BOT_LANG": "en",
    }.items():
        monkeypatch.setenv(k, v)
    return Settings()  # type: ignore[call-arg]


async def _dummy_run_sync() -> tuple[int, int]:
    return (0, 0)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_admin_not_authorized_for_non_admin_chat(
    repo: Repo, settings: Settings
) -> None:
    """Non-admin chat_id → answer is admin.not_authorized."""
    msg = MockMessage(chat_id=999)  # not admin_chat_id
    cmd = FakeCmd(args="list")

    await handle_admin(msg, cmd, repo, settings, _dummy_run_sync)  # type: ignore[arg-type]

    assert len(msg.answer_calls) == 1
    assert msg.answer_calls[0] == t("admin.not_authorized")


async def test_admin_list_returns_users(repo: Repo, settings: Settings) -> None:
    """Admin chat + 'list' sub → output starts with list_header and contains user row."""
    now = int(time.time())
    await repo.upsert_user(42, "vasya", "Vasya Petrov", "en")
    await repo.upsert_shared_user("vasya@example.com", 42, 1234, now, now)

    msg = MockMessage(chat_id=-100123)
    cmd = FakeCmd(args="list")

    await handle_admin(msg, cmd, repo, settings, _dummy_run_sync)  # type: ignore[arg-type]

    assert len(msg.answer_calls) == 1
    reply = msg.answer_calls[0]
    assert reply.startswith(t("admin.list_header"))
    assert "vasya" in reply
    assert "vasya@example.com" in reply


async def test_admin_pending_returns_pending_requests(
    repo: Repo, settings: Settings
) -> None:
    """Admin chat + 'pending' sub → output contains email and referrer."""
    await repo.upsert_user(55, "bob", "Bob", "en")
    await repo.create_request(
        telegram_id=55,
        email="bob@example.com",
        referrer="From Alice",
        admin_chat_id=-100123,
        admin_msg_id=None,
    )

    msg = MockMessage(chat_id=-100123)
    cmd = FakeCmd(args="pending")

    await handle_admin(msg, cmd, repo, settings, _dummy_run_sync)  # type: ignore[arg-type]

    assert len(msg.answer_calls) == 1
    reply = msg.answer_calls[0]
    assert t("admin.pending_header") in reply
    assert "bob@example.com" in reply
    assert "From Alice" in reply


async def test_admin_sync_invokes_run_sync_and_reports(
    repo: Repo, settings: Settings
) -> None:
    """Admin chat + 'sync' sub → run_sync called once; answer matches admin.sync_done."""
    run_sync = AsyncMock(return_value=(5, 1))

    msg = MockMessage(chat_id=-100123)
    cmd = FakeCmd(args="sync")

    await handle_admin(msg, cmd, repo, settings, run_sync)  # type: ignore[arg-type]

    run_sync.assert_called_once()
    assert len(msg.answer_calls) == 1
    assert msg.answer_calls[0] == t("admin.sync_done", active=5, revoked=1)


async def test_admin_unknown_subcommand_shows_usage(
    repo: Repo, settings: Settings
) -> None:
    """Admin chat + unknown sub → usage hint."""
    msg = MockMessage(chat_id=-100123)
    cmd = FakeCmd(args="garbage")

    await handle_admin(msg, cmd, repo, settings, _dummy_run_sync)  # type: ignore[arg-type]

    assert len(msg.answer_calls) == 1
    assert "Usage" in msg.answer_calls[0]
