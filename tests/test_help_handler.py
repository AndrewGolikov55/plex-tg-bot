from __future__ import annotations

from typing import Any

import pytest

from plex_tg_bot.bot.help import handle_help_message
from plex_tg_bot.i18n import set_lang, t


class MockMessage:
    def __init__(self) -> None:
        self.answer_calls: list[tuple[str, Any]] = []

    async def answer(
        self, text: str, reply_markup: object = None, parse_mode: str | None = None
    ) -> None:
        self.answer_calls.append((text, reply_markup))


@pytest.fixture(autouse=True)
def _set_lang() -> None:
    set_lang("en")


async def test_help_message() -> None:
    msg = MockMessage()
    await handle_help_message(msg)  # type: ignore[arg-type]
    assert len(msg.answer_calls) == 1
    text, kb = msg.answer_calls[0]
    assert text == t("help.text")
    assert kb is None
