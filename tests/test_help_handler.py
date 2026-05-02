from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from plex_tg_bot.bot.help import handle_help_callback, handle_help_message
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


async def test_help_callback() -> None:
    inner_msg = MockMessage()
    cq_answer_calls: list[tuple[Any, ...]] = []

    async def _cq_answer(*args: Any, **kwargs: Any) -> None:
        cq_answer_calls.append(args)

    cq = SimpleNamespace(
        message=inner_msg,
        answer=_cq_answer,
        data="help:show",
    )
    await handle_help_callback(cq)  # type: ignore[arg-type]
    assert len(inner_msg.answer_calls) == 1
    assert inner_msg.answer_calls[0][0] == t("help.text")
    assert len(cq_answer_calls) == 1


async def test_help_callback_no_message() -> None:
    """cq.answer is still called even when message is None."""
    cq_answer_calls: list[tuple[Any, ...]] = []

    async def _cq_answer(*args: Any, **kwargs: Any) -> None:
        cq_answer_calls.append(args)

    cq = SimpleNamespace(
        message=None,
        answer=_cq_answer,
        data="help:show",
    )
    await handle_help_callback(cq)  # type: ignore[arg-type]
    assert len(cq_answer_calls) == 1
