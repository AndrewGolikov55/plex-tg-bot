"""Apps handler — renders i18n/apps/<BOT_LANG>.html as Telegram HTML."""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from plex_tg_bot.bot.apps import (
    _apps_keyboard,
    _build_apps_payload,
    handle_apps_message,
)
from plex_tg_bot.config import Settings
from plex_tg_bot.db import Repo
from plex_tg_bot.i18n import set_lang, t


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("ADMIN_CHAT_ID", "-100")
    monkeypatch.setenv("PLEX_TOKEN", "p")
    monkeypatch.setenv("BOT_LANG", "en")
    return Settings()  # type: ignore[call-arg]


def test_build_apps_payload_returns_en_when_lang_en(settings: Settings) -> None:
    set_lang("en")
    text, kb = _build_apps_payload(settings)
    assert "Plex apps" in text
    assert "<b>" in text  # uses Telegram-HTML tags
    assert kb is not None
    assert len(kb.inline_keyboard) >= 1


def test_build_apps_payload_returns_ru_when_lang_ru(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("ADMIN_CHAT_ID", "-100")
    monkeypatch.setenv("PLEX_TOKEN", "p")
    monkeypatch.setenv("BOT_LANG", "ru")
    s = Settings()  # type: ignore[call-arg]
    set_lang("ru")
    text, _ = _build_apps_payload(s)
    assert "Приложения Plex" in text


def test_apps_keyboard_has_three_url_buttons() -> None:
    kb = _apps_keyboard()
    urls = [
        btn.url for row in kb.inline_keyboard for btn in row if btn.url is not None
    ]
    assert len(urls) == 3
    assert any("apple.com" in u for u in urls)
    assert any("play.google.com" in u for u in urls)
    assert any("app.plex.tv" in u for u in urls)


# --- access gating ---


class _MockMessage:
    def __init__(self, tg_id: int) -> None:
        self.from_user = SimpleNamespace(id=tg_id)
        self.answer_calls: list[dict[str, Any]] = []

    async def answer(
        self, text: str, reply_markup: object = None, parse_mode: str | None = None
    ) -> None:
        self.answer_calls.append(
            {"text": text, "reply_markup": reply_markup, "parse_mode": parse_mode}
        )


@pytest.fixture
async def repo(tmp_path):  # type: ignore[no-untyped-def]
    r = Repo(str(tmp_path / "test.sqlite"))
    await r.connect()
    yield r
    await r.close()


async def test_apps_no_access_replies_access_required(
    repo: Repo, settings: Settings
) -> None:
    set_lang("en")
    msg = _MockMessage(42)
    await handle_apps_message(msg, repo, settings)  # type: ignore[arg-type]
    assert msg.answer_calls[-1]["text"] == t("request.access_required")


async def test_apps_with_access_renders_html(
    repo: Repo, settings: Settings
) -> None:
    set_lang("en")
    import time
    now = int(time.time())
    await repo.upsert_user(42, "v", "V", "en")
    await repo.upsert_shared_user("v@e.com", 42, 1, now, now)
    msg = _MockMessage(42)
    await handle_apps_message(msg, repo, settings)  # type: ignore[arg-type]
    last = msg.answer_calls[-1]
    assert "Plex apps" in last["text"]
    assert last["parse_mode"] == "HTML"
    assert last["reply_markup"] is not None
