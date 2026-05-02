"""Tests for the happy-path approve callback and PlexAlreadyShared variant."""
from __future__ import annotations

import pathlib
import time
from types import SimpleNamespace

import pytest

from plex_tg_bot.bot.approve import handle_approve
from plex_tg_bot.config import Settings
from plex_tg_bot.db.repo import Repo
from plex_tg_bot.i18n import set_lang, t
from plex_tg_bot.services.overseerr import OverseerrError
from plex_tg_bot.services.plex import PlexAlreadyShared

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


class FakeOverseerr:
    def __init__(self, side_effect: BaseException | None = None) -> None:
        self.calls: list[list[int]] = []
        self._side_effect = side_effect

    async def import_from_plex(self, ids: list[int]) -> None:
        self.calls.append(ids)
        if self._side_effect is not None:
            raise self._side_effect


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
        "SHARED_LIBRARY_IDS": "1,2,3",
    }.items():
        monkeypatch.setenv(k, v)
    return Settings()  # type: ignore[call-arg]


async def _seed_request(repo: Repo, tg_id: int = 42) -> int:
    """Create a user + pending request, return the request id."""
    await repo.upsert_user(tg_id, "vasya", "Vasya", "en")
    return await repo.create_request(
        telegram_id=tg_id,
        email="vasya@example.com",
        referrer="From Andrey",
        admin_chat_id=-100123,
        admin_msg_id=99999,
    )


async def _seed_server_cache(repo: Repo) -> None:
    await repo.upsert_plex_server_cache("MACHINE_ID", "MyPlex")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_approve_happy_path(repo: Repo, settings: Settings) -> None:
    """Full success: share succeeds, overseerr called, admin card edited, DM sent."""
    rid = await _seed_request(repo)
    await _seed_server_cache(repo)

    plex = FakePlex(share_return=1234)
    overseerr = FakeOverseerr()
    bot = FakeBot()
    cq = FakeCQ(data=f"approve:{rid}")

    await handle_approve(cq, repo, bot, settings, plex, overseerr)  # type: ignore[arg-type]

    # DB state
    assert await repo.has_active_access(42)
    req = await repo.get_request(rid)
    assert req is not None
    assert req["status"] == "approved"

    # Plex called once with expected args
    assert len(plex.share_calls) == 1
    call = plex.share_calls[0]
    assert call["machine_identifier"] == "MACHINE_ID"
    assert call["email"] == "vasya@example.com"
    assert call["library_section_ids"] == [1, 2, 3]

    # Overseerr called with the plex_user_id
    assert len(overseerr.calls) == 1
    assert overseerr.calls[0] == [1234]

    # Admin card edited once
    assert len(bot.edits) == 1
    edit = bot.edits[0]
    assert edit["chat_id"] == -100123
    assert edit["message_id"] == 99999
    assert t("admin.approved_by", admin="@admin1", time="") in str(edit["text"]) or \
        "@admin1" in str(edit["text"])

    # DM sent to the user
    assert len(bot.sent) == 1
    assert "vasya@example.com" in str(bot.sent[0]["text"])
    assert t("notify_user.approved", email="vasya@example.com") == str(bot.sent[0]["text"])

    # cq.answer called (no show_alert)
    assert len(cq.answer_calls) >= 1
    last_answer = cq.answer_calls[-1]
    assert last_answer["show_alert"] is False


async def test_approve_already_shared_treated_as_success(
    repo: Repo, settings: Settings
) -> None:
    """PlexAlreadyShared(99) → treated as success with plex_user_id=99."""
    rid = await _seed_request(repo)
    await _seed_server_cache(repo)

    plex = FakePlex(share_side_effect=PlexAlreadyShared(99))
    overseerr = FakeOverseerr()
    bot = FakeBot()
    cq = FakeCQ(data=f"approve:{rid}")

    await handle_approve(cq, repo, bot, settings, plex, overseerr)  # type: ignore[arg-type]

    req = await repo.get_request(rid)
    assert req is not None
    assert req["status"] == "approved"
    assert await repo.has_active_access(42)

    # plex_user_id=99 used for overseerr
    assert len(overseerr.calls) == 1
    assert overseerr.calls[0] == [99]

    # Admin card edited, DM sent
    assert len(bot.edits) == 1
    assert len(bot.sent) == 1

    assert len(cq.answer_calls) >= 1
    assert cq.answer_calls[-1]["show_alert"] is False


async def test_approve_already_shared_no_uid_uses_zero(
    repo: Repo, settings: Settings
) -> None:
    """PlexAlreadyShared(0) → flow completes; overseerr is SKIPPED (plex_user_id=0 is falsy)."""
    rid = await _seed_request(repo)
    await _seed_server_cache(repo)

    plex = FakePlex(share_side_effect=PlexAlreadyShared(0))
    overseerr = FakeOverseerr()
    bot = FakeBot()
    cq = FakeCQ(data=f"approve:{rid}")

    await handle_approve(cq, repo, bot, settings, plex, overseerr)  # type: ignore[arg-type]

    req = await repo.get_request(rid)
    assert req is not None
    assert req["status"] == "approved"

    # overseerr skipped because plex_user_id=0 is falsy
    assert len(overseerr.calls) == 0

    # Admin card + DM still happen
    assert len(bot.edits) == 1
    assert len(bot.sent) == 1

    assert len(cq.answer_calls) >= 1
    assert cq.answer_calls[-1]["show_alert"] is False


async def test_approve_no_overseerr(repo: Repo, settings: Settings) -> None:
    """overseerr=None → no overseerr call; rest of the flow works."""
    rid = await _seed_request(repo)
    await _seed_server_cache(repo)

    plex = FakePlex(share_return=1234)
    bot = FakeBot()
    cq = FakeCQ(data=f"approve:{rid}")

    await handle_approve(cq, repo, bot, settings, plex, None)  # type: ignore[arg-type]

    req = await repo.get_request(rid)
    assert req is not None
    assert req["status"] == "approved"

    assert len(bot.edits) == 1
    assert len(bot.sent) == 1
    assert len(cq.answer_calls) >= 1
    assert cq.answer_calls[-1]["show_alert"] is False


async def test_approve_overseerr_fails_does_not_block(
    repo: Repo, settings: Settings
) -> None:
    """OverseerrError is best-effort: approve still completes, card edited, DM sent."""
    rid = await _seed_request(repo)
    await _seed_server_cache(repo)

    plex = FakePlex(share_return=1234)
    overseerr = FakeOverseerr(side_effect=OverseerrError("timeout"))
    bot = FakeBot()
    cq = FakeCQ(data=f"approve:{rid}")

    await handle_approve(cq, repo, bot, settings, plex, overseerr)  # type: ignore[arg-type]

    req = await repo.get_request(rid)
    assert req is not None
    assert req["status"] == "approved"
    assert await repo.has_active_access(42)

    # overseerr was attempted
    assert len(overseerr.calls) == 1

    # Admin card and DM still delivered
    assert len(bot.edits) == 1
    assert len(bot.sent) == 1

    assert len(cq.answer_calls) >= 1
    assert cq.answer_calls[-1]["show_alert"] is False


async def test_approve_used_timestamp_not_zero(repo: Repo, settings: Settings) -> None:
    """decided_at is set to a recent timestamp after approval, not NULL."""
    rid = await _seed_request(repo)
    await _seed_server_cache(repo)

    plex = FakePlex(share_return=1234)
    bot = FakeBot()
    cq = FakeCQ(data=f"approve:{rid}")

    before = int(time.time())
    await handle_approve(cq, repo, bot, settings, plex, None)  # type: ignore[arg-type]
    after = int(time.time())

    req = await repo.get_request(rid)
    assert req is not None
    assert req["decided_at"] is not None
    assert before <= int(req["decided_at"]) <= after
