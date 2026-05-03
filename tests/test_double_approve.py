"""Tests for the double-approve race condition."""
from __future__ import annotations

import pathlib
from types import SimpleNamespace

import pytest

from plex_tg_bot.bot.approve import handle_approve
from plex_tg_bot.config import Settings
from plex_tg_bot.db.repo import Repo
from plex_tg_bot.i18n import set_lang

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

    async def send_message(self, chat_id: int, text: str, reply_markup: object = None) -> None:
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})


class FakePlex:
    def __init__(
        self,
        share_side_effect: BaseException | None = None,
        share_return: tuple[int, str | None] = (1234, "test-invite-token"),
    ) -> None:
        self.share_calls: list[dict[str, object]] = []
        self._side_effect = share_side_effect
        self._return = share_return

    async def share_server(self, **kwargs: object) -> tuple[int, str | None]:
        self.share_calls.append(kwargs)
        if self._side_effect is not None:
            raise self._side_effect
        return self._return

    async def list_shared(self, machine_identifier: str) -> list[dict[str, object]]:
        return []


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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_double_approve_second_click_shows_already_handled(
    repo: Repo, settings: Settings
) -> None:
    """Second click on an already-approved request shows 'already_handled' without calling Plex."""
    await repo.upsert_user(42, "vasya", "Vasya", "en")
    rid = await repo.create_request(
        telegram_id=42,
        email="vasya@example.com",
        referrer="ref",
        admin_chat_id=-100123,
        admin_msg_id=99999,
    )
    await repo.upsert_plex_server_cache("MACHINE_ID", "MyPlex")

    plex = FakePlex(share_return=(1234, "test-invite-token"))
    bot = FakeBot()

    # First click — succeeds
    cq1 = FakeCQ(data=f"approve:{rid}", admin_id=7, username="admin1")
    await handle_approve(cq1, repo, bot, settings, plex, None)  # type: ignore[arg-type]
    assert len(plex.share_calls) == 1

    # Second click — different admin, same request
    cq2 = FakeCQ(data=f"approve:{rid}", admin_id=8, username="admin2")
    bot2 = FakeBot()
    await handle_approve(cq2, repo, bot2, settings, plex, None)  # type: ignore[arg-type]

    # Plex NOT called again
    assert len(plex.share_calls) == 1

    # cq2 answered with already_handled and show_alert=True
    assert len(cq2.answer_calls) == 1
    ans = cq2.answer_calls[0]
    assert ans["show_alert"] is True
    # The text should be the admin.already_handled i18n string (with some admin label filled in)
    assert "Already handled by" in str(ans["text"])

    # No card edit, no DM from second attempt
    assert len(bot2.edits) == 0
    assert len(bot2.sent) == 0
