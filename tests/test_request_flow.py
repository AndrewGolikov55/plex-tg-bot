from __future__ import annotations

import pathlib
import time
from types import SimpleNamespace
from typing import Any

import pytest

from plex_tg_bot.bot.request import (
    handle_email_text,
    handle_referrer_text,
    handle_request_cmd,
)
from plex_tg_bot.bot.states import RequestFSM
from plex_tg_bot.config import Settings
from plex_tg_bot.db import Repo
from plex_tg_bot.i18n import set_lang, t

# ---------------------------------------------------------------------------
# Helpers / fakes
# ---------------------------------------------------------------------------


class MockMessage:
    def __init__(self, tg_id: int, text: str = "") -> None:
        self.from_user = SimpleNamespace(
            id=tg_id,
            username="vasya",
            first_name="Vasya",
            last_name="",
        )
        self.chat = SimpleNamespace(id=tg_id)
        self.text = text
        self.answer_calls: list[tuple[str, object]] = []

    async def answer(self, text: str, reply_markup: object = None) -> None:
        self.answer_calls.append((text, reply_markup))


class FakeFSM:
    def __init__(self) -> None:
        self._state: object = None
        self._data: dict[str, object] = {}

    async def set_state(self, s: object) -> None:
        self._state = s

    async def get_state(self) -> object:
        return self._state

    async def update_data(self, **kwargs: object) -> None:
        self._data.update(kwargs)

    async def get_data(self) -> dict[str, object]:
        return dict(self._data)

    async def clear(self) -> None:
        self._state = None
        self._data.clear()

    def state(self) -> object:
        return self._state


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []

    async def send_message(
        self, chat_id: int, text: str, reply_markup: object = None
    ) -> SimpleNamespace:
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return SimpleNamespace(message_id=99999)


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
        "ADMIN_CHAT_ID": "-100",
        "PLEX_TOKEN": "p",
        "BOT_LANG": "en",
    }.items():
        monkeypatch.setenv(k, v)
    return Settings()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_request_already_has_access(repo: Repo, settings: Settings) -> None:
    """User with active shared_users row gets 'already_have_access' and no FSM transition."""
    await repo.upsert_user(42, "v", "V", "en")
    now = int(time.time())
    await repo.upsert_shared_user("v@e.com", 42, 1, now, now)

    msg = MockMessage(42, text="/request")
    fsm = FakeFSM()
    await handle_request_cmd(msg, fsm, repo)  # type: ignore[arg-type]

    assert msg.answer_calls[-1][0] == t("request.already_have_access")
    assert fsm.state() is None


async def test_request_already_pending(repo: Repo, settings: Settings) -> None:
    """User with a pending request row gets 'already_pending' and no FSM transition."""
    await repo.upsert_user(42, "v", "V", "en")
    await repo.create_request(42, "v@e.com", "ref", -100, None)

    msg = MockMessage(42, text="/request")
    fsm = FakeFSM()
    await handle_request_cmd(msg, fsm, repo)  # type: ignore[arg-type]

    assert msg.answer_calls[-1][0] == t("request.already_pending")
    assert fsm.state() is None


async def test_request_starts_email_collection(repo: Repo, settings: Settings) -> None:
    """Fresh user gets asked for email and FSM enters awaiting_email."""
    msg = MockMessage(42, text="/request")
    fsm = FakeFSM()
    await handle_request_cmd(msg, fsm, repo)  # type: ignore[arg-type]

    assert msg.answer_calls[-1][0] == t("request.ask_email")
    assert fsm.state() == RequestFSM.awaiting_email


async def test_email_invalid_stays_in_state() -> None:
    """Invalid email causes error reply; FSM state stays awaiting_email."""
    msg = MockMessage(42, text="not-an-email")
    fsm = FakeFSM()
    await fsm.set_state(RequestFSM.awaiting_email)
    await handle_email_text(msg, fsm)  # type: ignore[arg-type]

    assert msg.answer_calls[-1][0] == t("request.invalid_email")
    assert fsm.state() == RequestFSM.awaiting_email


async def test_email_valid_advances_to_referrer(monkeypatch: pytest.MonkeyPatch) -> None:
    """Valid email (MX check bypassed) advances FSM to awaiting_referrer."""
    monkeypatch.setattr("plex_tg_bot.bot.request.is_valid_email", lambda a, **k: True)

    msg = MockMessage(42, text="user@example.com")
    fsm = FakeFSM()
    await fsm.set_state(RequestFSM.awaiting_email)
    await handle_email_text(msg, fsm)  # type: ignore[arg-type]

    assert msg.answer_calls[-1][0] == t("request.ask_referrer")
    assert fsm.state() == RequestFSM.awaiting_referrer


async def test_referrer_creates_request_and_admin_card(
    repo: Repo, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Full flow: valid email + referrer → request row + admin card + user notified."""
    monkeypatch.setattr("plex_tg_bot.bot.request.is_valid_email", lambda a, **k: True)

    # Step 1: email collection
    msg_email = MockMessage(42, text="user@example.com")
    fsm = FakeFSM()
    await fsm.set_state(RequestFSM.awaiting_email)
    await handle_email_text(msg_email, fsm)  # type: ignore[arg-type]

    # Step 2: referrer submission
    msg_ref = MockMessage(42, text="From Andrew")
    bot = FakeBot()
    await handle_referrer_text(msg_ref, fsm, repo, bot, settings)  # type: ignore[arg-type]

    # Admin card was sent exactly once
    assert len(bot.sent) == 1
    card = bot.sent[0]
    assert card["chat_id"] == settings.admin_chat_id
    assert "user@example.com" in card["text"]
    assert "From Andrew" in card["text"]
    # Inline markup present
    assert card["reply_markup"] is not None

    # Request row exists in DB
    pending = await repo.get_pending_request_for_user(42)
    assert pending is not None
    assert pending["email"] == "user@example.com"
    assert pending["admin_msg_id"] == 99999  # FakeBot returns this

    # FSM is cleared
    assert fsm.state() is None

    # User receives submitted message
    assert msg_ref.answer_calls[-1][0] == t("request.submitted")


async def test_admin_card_buttons_reference_request_id(
    repo: Repo, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inline keyboard callback_data contains approve:/reject: with the real request_id."""
    monkeypatch.setattr("plex_tg_bot.bot.request.is_valid_email", lambda a, **k: True)

    msg_email = MockMessage(55, text="foo@bar.com")
    fsm = FakeFSM()
    await fsm.set_state(RequestFSM.awaiting_email)
    await handle_email_text(msg_email, fsm)  # type: ignore[arg-type]

    msg_ref = MockMessage(55, text="colleague")
    bot = FakeBot()
    await handle_referrer_text(msg_ref, fsm, repo, bot, settings)  # type: ignore[arg-type]

    pending = await repo.get_pending_request_for_user(55)
    assert pending is not None
    rid = pending["id"]

    markup = bot.sent[0]["reply_markup"]
    # InlineKeyboardMarkup stores rows in inline_keyboard
    buttons = [btn for row in markup.inline_keyboard for btn in row]  # type: ignore[union-attr]
    callback_datas = {btn.callback_data for btn in buttons}
    assert f"approve:{rid}" in callback_datas
    assert f"reject:{rid}" in callback_datas
