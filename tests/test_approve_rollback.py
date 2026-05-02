"""Tests for approve callback rollback when Plex API fails."""
from __future__ import annotations

import pathlib
from types import SimpleNamespace

import pytest

from plex_tg_bot.bot.approve import handle_approve
from plex_tg_bot.config import Settings
from plex_tg_bot.db.repo import Repo
from plex_tg_bot.i18n import set_lang, t
from plex_tg_bot.services.plex import PlexAuthError, PlexUnreachable

# ---------------------------------------------------------------------------
# Fakes (duplicated locally to keep test files independent)
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

    async def send_message(self, chat_id: int, text: str) -> None:
        self.sent.append({"chat_id": chat_id, "text": text})


class FakePlex:
    def __init__(
        self,
        share_side_effect: BaseException | None = None,
        share_return: int = 1234,
    ) -> None:
        self.share_calls: list[dict[str, object]] = []
        self._side_effect = share_side_effect
        self._return = share_return

    async def share_server(self, **kwargs: object) -> int:
        self.share_calls.append(kwargs)
        if self._side_effect is not None:
            raise self._side_effect
        return self._return


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
        "SHARED_LIBRARY_IDS": "1,2",
    }.items():
        monkeypatch.setenv(k, v)
    return Settings()  # type: ignore[call-arg]


async def _seed(repo: Repo, tg_id: int = 42) -> int:
    await repo.upsert_user(tg_id, "vasya", "Vasya", "en")
    rid = await repo.create_request(
        telegram_id=tg_id,
        email="vasya@example.com",
        referrer="ref",
        admin_chat_id=-100123,
        admin_msg_id=99999,
    )
    await repo.upsert_plex_server_cache("MACHINE_ID", "MyPlex")
    return rid


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_approve_rollback_on_plex_unreachable(
    repo: Repo, settings: Settings
) -> None:
    """PlexUnreachable → claim rolled back, request still pending, no card edit, no DM."""
    rid = await _seed(repo)
    plex = FakePlex(share_side_effect=PlexUnreachable("down"))
    bot = FakeBot()
    cq = FakeCQ(data=f"approve:{rid}")

    await handle_approve(cq, repo, bot, settings, plex, None)  # type: ignore[arg-type]

    # Request remains pending
    pending = await repo.get_pending_request_for_user(42)
    assert pending is not None
    assert pending["id"] == rid

    # decided_by and decided_at are NULL (rolled back)
    req = await repo.get_request(rid)
    assert req is not None
    assert req["decided_by"] is None
    assert req["decided_at"] is None

    # callback.answer with show_alert=True and errors.plex_temporary
    assert len(cq.answer_calls) == 1
    ans = cq.answer_calls[0]
    assert ans["show_alert"] is True
    assert ans["text"] == t("errors.plex_temporary")

    # No admin card edit, no DM
    assert len(bot.edits) == 0
    assert len(bot.sent) == 0


async def test_approve_rollback_on_plex_auth_error(
    repo: Repo, settings: Settings
) -> None:
    """PlexAuthError → same rollback behavior as PlexUnreachable."""
    rid = await _seed(repo)
    plex = FakePlex(share_side_effect=PlexAuthError("401"))
    bot = FakeBot()
    cq = FakeCQ(data=f"approve:{rid}")

    await handle_approve(cq, repo, bot, settings, plex, None)  # type: ignore[arg-type]

    # Request remains pending
    pending = await repo.get_pending_request_for_user(42)
    assert pending is not None
    assert pending["id"] == rid

    req = await repo.get_request(rid)
    assert req is not None
    assert req["decided_by"] is None
    assert req["decided_at"] is None

    assert len(cq.answer_calls) == 1
    ans = cq.answer_calls[0]
    assert ans["show_alert"] is True
    assert ans["text"] == t("errors.plex_temporary")

    assert len(bot.edits) == 0
    assert len(bot.sent) == 0


async def test_approve_retry_after_rollback_succeeds(
    repo: Repo, settings: Settings
) -> None:
    """After rollback, a second click with Plex now succeeding completes the flow."""
    rid = await _seed(repo)

    # First attempt – Plex unreachable
    plex_fail = FakePlex(share_side_effect=PlexUnreachable("down"))
    bot1 = FakeBot()
    cq1 = FakeCQ(data=f"approve:{rid}")
    await handle_approve(cq1, repo, bot1, settings, plex_fail, None)  # type: ignore[arg-type]

    # Confirm still pending
    assert await repo.get_pending_request_for_user(42) is not None

    # Second attempt – Plex succeeds
    plex_ok = FakePlex(share_return=1234)
    bot2 = FakeBot()
    cq2 = FakeCQ(data=f"approve:{rid}")
    await handle_approve(cq2, repo, bot2, settings, plex_ok, None)  # type: ignore[arg-type]

    # Now approved
    req = await repo.get_request(rid)
    assert req is not None
    assert req["status"] == "approved"
    assert await repo.has_active_access(42)

    # card edited + DM sent on second attempt
    assert len(bot2.edits) == 1
    assert len(bot2.sent) == 1

    assert len(cq2.answer_calls) >= 1
    assert cq2.answer_calls[-1]["show_alert"] is False
