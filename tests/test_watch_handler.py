from __future__ import annotations

import pathlib
import time
from types import SimpleNamespace
from typing import Any

import pytest

from plex_tg_bot.bot.watch import handle_watch
from plex_tg_bot.config import Settings
from plex_tg_bot.db import Repo
from plex_tg_bot.i18n import set_lang, t


class MockMessage:
    def __init__(self, tg_id: int) -> None:
        self.from_user = SimpleNamespace(id=tg_id)
        self.answer_calls: list[tuple[str, Any]] = []

    async def answer(
        self, text: str, reply_markup: object = None, parse_mode: str | None = None
    ) -> None:
        self.answer_calls.append((text, reply_markup))


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
        "WATCH_URL": "https://watch.example.com/",
    }.items():
        monkeypatch.setenv(k, v)
    return Settings()  # type: ignore[call-arg]


@pytest.fixture(autouse=True)
def _set_lang() -> None:
    set_lang("en")


async def test_watch_no_access(repo: Repo, settings: Settings) -> None:
    msg = MockMessage(tg_id=10)
    await handle_watch(msg, repo, settings)  # type: ignore[arg-type]
    assert len(msg.answer_calls) == 1
    text, kb = msg.answer_calls[0]
    assert text == t("request.access_required")
    assert kb is None


async def test_watch_with_access(repo: Repo, settings: Settings) -> None:
    await repo.upsert_user(11, "w", "W", "en")
    now = int(time.time())
    await repo.upsert_shared_user("w@e.com", 11, 5555, now, now)

    msg = MockMessage(tg_id=11)
    await handle_watch(msg, repo, settings)  # type: ignore[arg-type]
    assert len(msg.answer_calls) == 1
    text, kb = msg.answer_calls[0]
    assert text == t("menu.watch")
    assert kb is not None
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(buttons) == 1
    assert buttons[0].url == "https://watch.example.com/"


async def test_watch_no_from_user(repo: Repo, settings: Settings) -> None:
    """Handler silently returns when from_user is None."""
    msg = MockMessage(tg_id=0)
    msg.from_user = None  # type: ignore[assignment]
    await handle_watch(msg, repo, settings)  # type: ignore[arg-type]
    assert msg.answer_calls == []
