from __future__ import annotations

import pathlib
import time
from types import SimpleNamespace
from typing import Any

import pytest

from plex_tg_bot.bot.overseerr import handle_overseerr
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
def settings_no_overseerr(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for k, v in {
        "TELEGRAM_BOT_TOKEN": "t",
        "ADMIN_CHAT_ID": "-100",
        "PLEX_TOKEN": "p",
        "BOT_LANG": "en",
    }.items():
        monkeypatch.setenv(k, v)
    return Settings()  # type: ignore[call-arg]


@pytest.fixture
def settings_with_overseerr(monkeypatch: pytest.MonkeyPatch) -> Settings:
    for k, v in {
        "TELEGRAM_BOT_TOKEN": "t",
        "ADMIN_CHAT_ID": "-100",
        "PLEX_TOKEN": "p",
        "BOT_LANG": "en",
        "OVERSEERR_PUBLIC_URL": "https://overseerr.example.com/",
        "OVERSEERR_API_KEY": "secret-key",
    }.items():
        monkeypatch.setenv(k, v)
    return Settings()  # type: ignore[call-arg]


@pytest.fixture(autouse=True)
def _set_lang() -> None:
    set_lang("en")


async def test_overseerr_disabled(
    repo: Repo, settings_no_overseerr: Settings
) -> None:
    msg = MockMessage(tg_id=20)
    await handle_overseerr(msg, repo, settings_no_overseerr)  # type: ignore[arg-type]
    assert len(msg.answer_calls) == 1
    text, kb = msg.answer_calls[0]
    assert text == t("errors.feature_disabled")
    assert kb is None


async def test_overseerr_enabled_no_access(
    repo: Repo, settings_with_overseerr: Settings
) -> None:
    msg = MockMessage(tg_id=21)
    await handle_overseerr(msg, repo, settings_with_overseerr)  # type: ignore[arg-type]
    assert len(msg.answer_calls) == 1
    text, kb = msg.answer_calls[0]
    assert text == t("request.access_required")
    assert kb is None


async def test_overseerr_enabled_with_access(
    repo: Repo, settings_with_overseerr: Settings
) -> None:
    await repo.upsert_user(22, "o", "O", "en")
    now = int(time.time())
    await repo.upsert_shared_user("o@e.com", 22, 9999, now, now)

    msg = MockMessage(tg_id=22)
    await handle_overseerr(msg, repo, settings_with_overseerr)  # type: ignore[arg-type]
    assert len(msg.answer_calls) == 1
    text, kb = msg.answer_calls[0]
    assert text == t("menu.overseerr")
    assert kb is not None
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(buttons) == 1
    assert buttons[0].url == "https://overseerr.example.com/"
