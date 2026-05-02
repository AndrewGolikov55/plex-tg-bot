from __future__ import annotations

import pathlib
import time
from types import SimpleNamespace
from typing import Any

import pytest

from plex_tg_bot.bot.apps import handle_apps_callback, handle_apps_message
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
def settings(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> Settings:
    for k, v in {
        "TELEGRAM_BOT_TOKEN": "t",
        "ADMIN_CHAT_ID": "-100",
        "PLEX_TOKEN": "p",
        "BOT_LANG": "en",
        "APPS_MARKDOWN_PATH": str(tmp_path / "apps.md"),
    }.items():
        monkeypatch.setenv(k, v)
    return Settings()  # type: ignore[call-arg]


@pytest.fixture(autouse=True)
def _set_lang() -> None:
    set_lang("en")


async def test_apps_no_access_replies_access_required(
    repo: Repo, settings: Settings
) -> None:
    msg = MockMessage(tg_id=42)
    await handle_apps_message(msg, repo, settings)  # type: ignore[arg-type]
    assert len(msg.answer_calls) == 1
    text, kb = msg.answer_calls[0]
    assert text == t("request.access_required")
    assert kb is None


async def test_apps_with_access_uses_apps_md_when_present(
    repo: Repo, settings: Settings, tmp_path: pathlib.Path
) -> None:
    # Give user active access
    await repo.upsert_user(7, "u", "U", "en")
    now = int(time.time())
    await repo.upsert_shared_user("u@e.com", 7, 1111, now, now)

    # Write the markdown file (sync write OK in test setup, not in async handler)
    md_file = pathlib.Path(settings.apps_markdown_path)
    md_file.write_text("# Get Plex\nInstall the app!", encoding="utf-8")  # noqa: ASYNC240

    msg = MockMessage(tg_id=7)
    await handle_apps_message(msg, repo, settings)  # type: ignore[arg-type]
    assert len(msg.answer_calls) == 1
    text, kb = msg.answer_calls[0]
    assert text == "# Get Plex\nInstall the app!"
    assert kb is not None
    # Verify 3 URL buttons
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(buttons) == 3
    urls = [b.url for b in buttons]
    assert any("apple.com" in (u or "") for u in urls)
    assert any("play.google.com" in (u or "") for u in urls)
    assert any("app.plex.tv" in (u or "") for u in urls)


async def test_apps_with_access_falls_back_when_md_missing(
    repo: Repo, settings: Settings
) -> None:
    # Give user active access — apps.md path points to non-existent file by fixture default
    await repo.upsert_user(8, "u2", "U2", "en")
    now = int(time.time())
    await repo.upsert_shared_user("u2@e.com", 8, 2222, now, now)

    msg = MockMessage(tg_id=8)
    await handle_apps_message(msg, repo, settings)  # type: ignore[arg-type]
    assert len(msg.answer_calls) == 1
    text, kb = msg.answer_calls[0]
    assert text == t("apps.fallback", url="https://www.plex.tv/media-server-downloads/")
    assert kb is not None
    buttons = [btn for row in kb.inline_keyboard for btn in row]
    assert len(buttons) == 3


async def test_apps_callback_no_access(repo: Repo, settings: Settings) -> None:
    inner_msg = MockMessage(tg_id=99)

    answer_calls: list[tuple[str, Any]] = []

    async def _answer(
        text: str, reply_markup: object = None, parse_mode: str | None = None
    ) -> None:
        answer_calls.append((text, reply_markup))

    inner_msg.answer = _answer  # type: ignore[method-assign]

    cq_answer_calls: list[tuple[Any, ...]] = []

    async def _cq_answer(*args: Any, **kwargs: Any) -> None:
        cq_answer_calls.append(args)

    cq = SimpleNamespace(
        from_user=SimpleNamespace(id=99),
        message=inner_msg,
        answer=_cq_answer,
        data="apps:show",
    )
    await handle_apps_callback(cq, repo, settings)  # type: ignore[arg-type]
    assert len(answer_calls) == 1
    assert answer_calls[0][0] == t("request.access_required")
    assert len(cq_answer_calls) == 1
