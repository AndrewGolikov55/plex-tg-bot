"""Tests for reject callback + reject reason FSM (Task 7.2)."""
from __future__ import annotations

import pathlib
from types import SimpleNamespace
from typing import Any

import pytest

from plex_tg_bot.bot.approve import (
    handle_reject,
    handle_reject_cancel,
    handle_reject_reason,
    handle_reject_skip,
)
from plex_tg_bot.bot.states import RejectFSM
from plex_tg_bot.config import Settings
from plex_tg_bot.db.repo import Repo
from plex_tg_bot.i18n import set_lang, t

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeCQ:
    def __init__(self, data: str, admin_id: int = 7, username: str = "admin1") -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=admin_id, username=username, first_name="Admin")
        self.message = SimpleNamespace(
            message_id=99999, chat=SimpleNamespace(id=-100123)
        )
        self.answer_calls: list[dict[str, object]] = []

    async def answer(self, text: str | None = None, show_alert: bool = False) -> None:
        self.answer_calls.append({"text": text, "show_alert": show_alert})


class FakeBot:
    def __init__(self) -> None:
        self.edits: list[dict[str, object]] = []
        self.sent: list[dict[str, object]] = []

    async def edit_message_text(
        self, chat_id: int, message_id: int, text: str
    ) -> None:
        self.edits.append({"chat_id": chat_id, "message_id": message_id, "text": text})

    async def send_message(
        self, chat_id: int, text: str, reply_to_message_id: int | None = None
    ) -> None:
        self.sent.append(
            {"chat_id": chat_id, "text": text, "reply_to_message_id": reply_to_message_id}
        )


class FakeFSM:
    def __init__(self) -> None:
        self._state: str | None = None
        self._data: dict[str, Any] = {}

    async def set_state(self, state: Any) -> None:
        self._state = str(state)

    async def get_state(self) -> str | None:
        return self._state

    async def update_data(self, **kwargs: Any) -> None:
        self._data.update(kwargs)

    async def get_data(self) -> dict[str, Any]:
        return dict(self._data)

    async def clear(self) -> None:
        self._state = None
        self._data = {}


class FakeMessage:
    def __init__(
        self,
        text: str,
        from_user_id: int = 7,
        username: str = "admin1",
        reply_to_message: Any | None = None,
    ) -> None:
        self.text = text
        self.from_user = SimpleNamespace(
            id=from_user_id, username=username, first_name="Admin"
        )
        self.reply_to_message = reply_to_message


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
        "SHARED_LIBRARY_IDS": "1,2,3",
    }.items():
        monkeypatch.setenv(k, v)
    return Settings()  # type: ignore[call-arg]


async def _seed_request(repo: Repo, tg_id: int = 42) -> int:
    await repo.upsert_user(tg_id, "vasya", "Vasya", "en")
    return await repo.create_request(
        telegram_id=tg_id,
        email="vasya@example.com",
        referrer="From Andrey",
        admin_chat_id=-100123,
        admin_msg_id=99999,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_reject_claim_and_prompt(repo: Repo, settings: Settings) -> None:
    """First reject click claims request and asks for reason."""
    rid = await _seed_request(repo)
    bot = FakeBot()
    cq = FakeCQ(data=f"reject:{rid}", admin_id=7, username="admin1")
    state = FakeFSM()

    await handle_reject(cq, repo, bot, settings, state)  # type: ignore[arg-type]

    # FSM in correct state
    assert await state.get_state() == str(RejectFSM.awaiting_reason)
    data = await state.get_data()
    assert data["request_id"] == rid
    assert data["card_msg_id"] == 99999
    assert data["admin_chat_id"] == -100123

    # Bot asked for reason with reply_to
    assert len(bot.sent) == 1
    sent = bot.sent[0]
    assert "admin1" in sent["text"]
    assert sent["reply_to_message_id"] == 99999

    # cq.answer called without show_alert
    assert len(cq.answer_calls) == 1
    assert cq.answer_calls[0]["show_alert"] is False

    # DB: request is claimed (decided_by set)
    req = await repo.get_request(rid)
    assert req is not None
    assert req["decided_by"] == 7


async def test_reject_with_reason_finalizes_and_notifies(
    repo: Repo, settings: Settings
) -> None:
    """Admin replies (reply_to=card) with reason → finalize_reject + DM user."""
    rid = await _seed_request(repo)
    bot = FakeBot()
    state = FakeFSM()

    # Pre-claim and set FSM state as if handle_reject already ran
    import time as _time
    await repo.claim_request(rid, 7, int(_time.time()))
    await state.set_state(RejectFSM.awaiting_reason)
    await state.update_data(request_id=rid, card_msg_id=99999, admin_chat_id=-100123)

    card_stub = SimpleNamespace(message_id=99999)
    msg = FakeMessage(
        text="spam",
        from_user_id=7,
        username="admin1",
        reply_to_message=card_stub,
    )

    await handle_reject_reason(msg, state, repo, bot)  # type: ignore[arg-type]

    # DB finalized
    req = await repo.get_request(rid)
    assert req is not None
    assert req["status"] == "rejected"
    assert req["reject_reason"] == "spam"

    # Admin card edited
    assert len(bot.edits) == 1
    edit = bot.edits[0]
    assert edit["chat_id"] == -100123
    assert edit["message_id"] == 99999
    assert "admin1" in str(edit["text"])

    # User DM contains reason
    assert len(bot.sent) == 1
    dm = bot.sent[0]
    assert dm["chat_id"] == 42
    assert "spam" in dm["text"]

    # FSM cleared
    assert await state.get_state() is None


async def test_reject_skip_finalizes_without_reason(
    repo: Repo, settings: Settings
) -> None:
    """Admin /skip → finalize with reason=None, user DM is rejected_no_reason."""
    rid = await _seed_request(repo)
    bot = FakeBot()
    state = FakeFSM()

    import time as _time
    await repo.claim_request(rid, 7, int(_time.time()))
    await state.set_state(RejectFSM.awaiting_reason)
    await state.update_data(request_id=rid, card_msg_id=99999, admin_chat_id=-100123)

    msg = FakeMessage(text="/skip", from_user_id=7, username="admin1")

    await handle_reject_skip(msg, state, repo, bot)  # type: ignore[arg-type]

    req = await repo.get_request(rid)
    assert req is not None
    assert req["status"] == "rejected"
    assert req["reject_reason"] is None

    # User DM is rejected_no_reason
    assert len(bot.sent) == 1
    dm = bot.sent[0]
    assert dm["chat_id"] == 42
    assert dm["text"] == t("notify_user.rejected_no_reason")

    # FSM cleared
    assert await state.get_state() is None


async def test_reject_cancel_rolls_back_claim(repo: Repo) -> None:
    """Admin /cancel → request returns to pending, FSM cleared."""
    rid = await _seed_request(repo)
    state = FakeFSM()

    import time as _time
    await repo.claim_request(rid, 7, int(_time.time()))
    await state.set_state(RejectFSM.awaiting_reason)
    await state.update_data(request_id=rid, card_msg_id=99999, admin_chat_id=-100123)

    msg = FakeMessage(text="/cancel", from_user_id=7, username="admin1")

    await handle_reject_cancel(msg, state, repo)  # type: ignore[arg-type]

    # decided_by / decided_at rolled back
    req = await repo.get_request(rid)
    assert req is not None
    assert req["decided_by"] is None
    assert req["decided_at"] is None
    assert req["status"] == "pending"

    # Still retrievable as pending
    pending = await repo.get_pending_request_for_user(42)
    assert pending is not None
    assert pending["id"] == rid

    # FSM cleared
    assert await state.get_state() is None


async def test_reject_reason_ignored_if_not_reply(repo: Repo) -> None:
    """Text without reply_to_message is ignored — no DB write, FSM unchanged."""
    rid = await _seed_request(repo)
    bot = FakeBot()
    state = FakeFSM()

    import time as _time
    await repo.claim_request(rid, 7, int(_time.time()))
    await state.set_state(RejectFSM.awaiting_reason)
    await state.update_data(request_id=rid, card_msg_id=99999, admin_chat_id=-100123)

    msg = FakeMessage(text="some chatter", reply_to_message=None)

    await handle_reject_reason(msg, state, repo, bot)  # type: ignore[arg-type]

    # No DB write
    req = await repo.get_request(rid)
    assert req is not None
    assert req["status"] == "pending"

    # No bot messages
    assert len(bot.sent) == 0
    assert len(bot.edits) == 0

    # FSM still active
    assert await state.get_state() == str(RejectFSM.awaiting_reason)


async def test_reject_reason_ignored_if_reply_to_other_message(repo: Repo) -> None:
    """Reply to a different message id is ignored."""
    rid = await _seed_request(repo)
    bot = FakeBot()
    state = FakeFSM()

    import time as _time
    await repo.claim_request(rid, 7, int(_time.time()))
    await state.set_state(RejectFSM.awaiting_reason)
    await state.update_data(request_id=rid, card_msg_id=99999, admin_chat_id=-100123)

    other_msg = SimpleNamespace(message_id=11111)  # NOT 99999
    msg = FakeMessage(text="wrong reply", reply_to_message=other_msg)

    await handle_reject_reason(msg, state, repo, bot)  # type: ignore[arg-type]

    req = await repo.get_request(rid)
    assert req is not None
    assert req["status"] == "pending"

    assert len(bot.sent) == 0
    assert len(bot.edits) == 0

    assert await state.get_state() == str(RejectFSM.awaiting_reason)


async def test_reject_double_click_shows_already_handled(
    repo: Repo, settings: Settings
) -> None:
    """Second admin clicks reject after first claim → already_handled."""
    rid = await _seed_request(repo)
    bot = FakeBot()

    # First click — succeeds
    state1 = FakeFSM()
    cq1 = FakeCQ(data=f"reject:{rid}", admin_id=7, username="admin1")
    await handle_reject(cq1, repo, bot, settings, state1)  # type: ignore[arg-type]
    assert await state1.get_state() == str(RejectFSM.awaiting_reason)

    # Second click — different admin
    bot2 = FakeBot()
    state2 = FakeFSM()
    cq2 = FakeCQ(data=f"reject:{rid}", admin_id=8, username="admin2")
    await handle_reject(cq2, repo, bot2, settings, state2)  # type: ignore[arg-type]

    # cq2 answered with show_alert=True
    assert len(cq2.answer_calls) == 1
    ans = cq2.answer_calls[0]
    assert ans["show_alert"] is True
    assert "Already handled" in str(ans["text"])

    # Second bot sent nothing
    assert len(bot2.sent) == 0

    # FSM2 not entered
    assert await state2.get_state() is None
