"""Contract tests linking emitter (menu / commands list) to consumer (routers).

These exist because handler-level unit tests test functions in isolation and
menu builder tests assert which `callback_data` strings are emitted, but
nothing previously verified that emitted strings actually match a registered
handler. Same for slash commands — each command name must have a router
wired in __main__.py.

The tests build every router with stub deps, walk each router's
observers, and run aiogram filters against synthetic events.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import pytest_asyncio
from aiogram import Router

from plex_tg_bot.bot.admin import make_admin_router
from plex_tg_bot.bot.approve import make_approve_router
from plex_tg_bot.bot.apps import make_apps_router
from plex_tg_bot.bot.help import make_help_router
from plex_tg_bot.bot.menu import build_main_menu
from plex_tg_bot.bot.overseerr import make_overseerr_router
from plex_tg_bot.bot.request import make_request_router
from plex_tg_bot.bot.start import make_start_router
from plex_tg_bot.bot.watch import make_watch_router
from plex_tg_bot.config import Settings
from plex_tg_bot.db import Repo

EXPECTED_COMMANDS = {"start", "request", "apps", "watch", "overseerr", "help", "admin"}


# ---------------------------------------------------------------------------
# Fixtures and stubs
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def repo(tmp_path: Path) -> AsyncGenerator[Repo, None]:
    r = Repo(str(tmp_path / "test.sqlite"))
    await r.connect()
    yield r
    await r.close()


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> Settings:
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("ADMIN_CHAT_ID", "-100")
    monkeypatch.setenv("PLEX_TOKEN", "p")
    monkeypatch.setenv("OVERSEERR_PUBLIC_URL", "https://o.example.com")
    monkeypatch.setenv("OVERSEERR_API_KEY", "k")
    monkeypatch.setenv("BOT_LANG", "en")
    return Settings()  # type: ignore[call-arg]


class _StubBot:
    """Just enough surface for aiogram filters that may touch bot.me()."""

    id = 1
    username = "stub_bot"

    async def me(self) -> Any:
        return SimpleNamespace(id=self.id, username=self.username, is_bot=True)


class _StubPlex:
    async def share_server(self, **_: Any) -> int:
        return 0

    async def list_shared(self, *_: Any) -> list[Any]:
        return []

    async def discover_server(self) -> tuple[str, str]:
        return ("MID", "Stub")


async def _stub_run_sync() -> tuple[int, int]:
    return (0, 0)


@pytest.fixture
def routers(repo: Repo, settings: Settings) -> list[Router]:
    """Mirror __main__.py's wiring exactly."""
    bot = _StubBot()
    plex = _StubPlex()
    return [
        make_admin_router(repo, settings, bot, plex, _stub_run_sync),  # type: ignore[arg-type]
        make_start_router(repo, settings),
        make_request_router(repo, bot, settings),  # type: ignore[arg-type]
        make_approve_router(repo, bot, settings, plex, None),  # type: ignore[arg-type]
        make_apps_router(repo, settings),
        make_watch_router(repo, settings),
        make_overseerr_router(repo, settings),
        make_help_router(),
    ]


# ---------------------------------------------------------------------------
# Helpers — collecting emitted callback_data, resolving against routers
# ---------------------------------------------------------------------------


def _collect_menu_callbacks() -> set[str]:
    """All callback_data values that build_main_menu can emit."""
    seen: set[str] = set()
    for state in ("no_access", "pending", "has_access"):
        for ovs in (False, True):
            kb = build_main_menu(
                state,  # type: ignore[arg-type]
                overseerr_enabled=ovs,
                watch_url="https://app.plex.tv/desktop/",
                overseerr_url="https://o.example.com" if ovs else None,
            )
            for row in kb.inline_keyboard:
                for btn in row:
                    if btn.callback_data is not None:
                        seen.add(btn.callback_data)
    return seen


def _make_cq(data: str) -> Any:
    """A duck-typed CallbackQuery sufficient for F.data filter checks."""
    return SimpleNamespace(
        data=data,
        from_user=SimpleNamespace(id=42, username="v", first_name="V", is_bot=False),
        message=SimpleNamespace(
            message_id=1,
            chat=SimpleNamespace(id=42),
            from_user=SimpleNamespace(id=99, is_bot=True),
        ),
    )


async def _resolves_callback(routers_: list[Router], data: str) -> bool:
    cq = _make_cq(data)
    for router in routers_:
        for handler in router.callback_query.handlers:
            matched, _ = await handler.check(cq)
            if matched:
                return True
    return False


def _collect_command_filters(routers_: list[Router]) -> set[str]:
    """Inspect each router's message handlers for Command(...) filters and
    return the union of declared command names."""
    out: set[str] = set()
    for router in routers_:
        for handler in router.message.handlers:
            for f in handler.filters or ():
                # aiogram.filters.Command stores names in `.commands`
                callable_ = getattr(f, "callback", None)
                names = getattr(callable_, "commands", None)
                if names:
                    out.update(names)
    return out


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_every_menu_callback_has_handler(routers: list[Router]) -> None:
    """Every callback_data emitted by build_main_menu must match some handler."""
    emitted = _collect_menu_callbacks()
    assert emitted, "menu builder produced no callback buttons — regression?"

    missing = []
    for cb in sorted(emitted):
        if not await _resolves_callback(routers, cb):
            missing.append(cb)
    assert not missing, (
        f"menu emits callback_data without handler: {missing}. "
        "Add a callback_query handler in the corresponding router."
    )


async def test_known_dynamic_callback_prefixes_have_handlers(routers: list[Router]) -> None:
    """Dynamic callbacks (approve:N, reject:N) are not produced by build_main_menu
    but ARE generated at runtime by /request. Verify their handlers exist too."""
    for cb in ("approve:123", "reject:123"):
        assert await _resolves_callback(routers, cb), f"no handler for {cb}"


def test_all_expected_commands_have_routers(routers: list[Router]) -> None:
    """Every slash command the bot should expose must have a Command filter."""
    declared = _collect_command_filters(routers)
    missing = EXPECTED_COMMANDS - declared
    assert not missing, (
        f"slash commands without a registered handler: {sorted(missing)}. "
        f"Either add a router or update EXPECTED_COMMANDS."
    )


def test_no_unexpected_commands_are_declared(routers: list[Router]) -> None:
    """Catch the reverse drift — declared command without it being in the
    documented set (so README/help.text and EXPECTED_COMMANDS stay in sync)."""
    declared = _collect_command_filters(routers)
    unexpected = declared - EXPECTED_COMMANDS
    assert not unexpected, (
        f"router declares commands not in EXPECTED_COMMANDS: {sorted(unexpected)}. "
        "Document them in help.text and add to EXPECTED_COMMANDS."
    )
