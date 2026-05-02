from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from plex_tg_bot.bot.start import handle_start
from plex_tg_bot.config import Settings
from plex_tg_bot.db import Repo
from plex_tg_bot.i18n import set_lang, t


class MockMessage:
    def __init__(self, tg_id: int) -> None:
        self.from_user = SimpleNamespace(
            id=tg_id,
            username="vasya",
            first_name="V",
            last_name="",
        )
        self.chat = SimpleNamespace(id=tg_id)
        self.answer_calls: list[tuple[str, object]] = []

    async def answer(self, text: str, reply_markup: object = None) -> None:
        self.answer_calls.append((text, reply_markup))


@pytest.fixture
async def repo(tmp_path: pytest.TempPathFactory) -> Repo:  # type: ignore[misc]
    import pathlib

    r = Repo(str(pathlib.Path(str(tmp_path)) / "test.sqlite"))
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


@pytest.fixture(autouse=True)
def _set_lang() -> None:
    set_lang("en")


async def test_start_no_access(repo: Repo, settings: Settings) -> None:
    msg = MockMessage(tg_id=42)
    await handle_start(msg, repo, settings)  # type: ignore[arg-type]
    assert len(msg.answer_calls) == 1
    text, kb = msg.answer_calls[0]
    # server_name falls back to "Plex" when no cache and plex_server_name is None
    assert "Plex" in text
    assert kb is not None


async def test_start_pending(repo: Repo, settings: Settings) -> None:
    await repo.upsert_user(42, "v", "V", "en")
    await repo.create_request(42, "v@e.com", "ref", -100, None)
    msg = MockMessage(tg_id=42)
    await handle_start(msg, repo, settings)  # type: ignore[arg-type]
    text, kb = msg.answer_calls[0]
    assert text == t("welcome.pending")
    assert kb is not None


async def test_start_has_access(repo: Repo, settings: Settings) -> None:
    await repo.upsert_user(42, "v", "V", "en")
    now = int(time.time())
    await repo.upsert_shared_user("v@e.com", 42, 1234, now, now)
    msg = MockMessage(tg_id=42)
    await handle_start(msg, repo, settings)  # type: ignore[arg-type]
    text, kb = msg.answer_calls[0]
    # welcome.has_access contains {server_name} filled with "Plex" fallback
    assert "Plex" in text
    assert kb is not None


async def test_start_server_name_from_settings(repo: Repo, monkeypatch: pytest.MonkeyPatch) -> None:
    """plex_server_name in settings takes priority over cache."""
    for k, v in {
        "TELEGRAM_BOT_TOKEN": "t",
        "ADMIN_CHAT_ID": "-100",
        "PLEX_TOKEN": "p",
        "BOT_LANG": "en",
        "PLEX_SERVER_NAME": "MyPlex",
    }.items():
        monkeypatch.setenv(k, v)
    s = Settings()  # type: ignore[call-arg]
    msg = MockMessage(tg_id=99)
    await handle_start(msg, repo, s)  # type: ignore[arg-type]
    text, _ = msg.answer_calls[0]
    assert "MyPlex" in text


async def test_start_server_name_from_cache(repo: Repo, settings: Settings) -> None:
    """friendly_name from plex_server_cache is used when settings has no plex_server_name."""
    await repo.upsert_plex_server_cache("abc123", "CachedPlex")
    msg = MockMessage(tg_id=55)
    await handle_start(msg, repo, settings)  # type: ignore[arg-type]
    text, _ = msg.answer_calls[0]
    assert "CachedPlex" in text
