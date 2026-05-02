"""Tests for plex_tg_bot.jobs.daily_sync.run_daily_sync."""
from __future__ import annotations

import pathlib
import time
from unittest.mock import AsyncMock

import pytest

from plex_tg_bot.db.repo import Repo
from plex_tg_bot.jobs.daily_sync import run_daily_sync
from plex_tg_bot.services.plex import PlexUnreachable

# ---------------------------------------------------------------------------
# Fake PlexClient
# ---------------------------------------------------------------------------


class FakePlex:
    def __init__(
        self,
        items: list[dict[str, str | int]] | None = None,
        side_effect: Exception | None = None,
    ) -> None:
        if side_effect is not None:
            self.list_shared: AsyncMock = AsyncMock(side_effect=side_effect)
        else:
            self.list_shared = AsyncMock(return_value=items or [])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def repo(tmp_path: pathlib.Path) -> Repo:  # type: ignore[misc]
    r = Repo(str(tmp_path / "test.sqlite"))
    await r.connect()
    yield r
    await r.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_run_daily_sync_no_cache(repo: Repo) -> None:
    """When there is no server cache, returns (0, 0) without calling plex."""
    plex = FakePlex(items=[{"email": "user@x.com", "plex_user_id": 1}])

    result = await run_daily_sync(repo, plex)  # type: ignore[arg-type]

    assert result == (0, 0)
    plex.list_shared.assert_not_called()


async def test_run_daily_sync_happy_path(repo: Repo) -> None:
    """Happy path: upserts seen users, revokes stale ones, returns (2, 1)."""
    now = int(time.time())

    # Populate cache
    await repo.upsert_plex_server_cache("MID", "X")

    # Pre-populate three shared users:
    # a — recently seen (will remain active after sync)
    await repo.upsert_shared_user("a@x.com", None, 1, shared_at=now, last_seen_in_plex=now)
    # b — stale, but plex will report it as still shared
    await repo.upsert_shared_user(
        "b@x.com", None, 2, shared_at=now, last_seen_in_plex=now - 2 * 86400
    )
    # c — stale AND not in plex response → should be revoked
    await repo.upsert_shared_user(
        "c@x.com", None, 3, shared_at=now, last_seen_in_plex=now - 2 * 86400
    )

    plex = FakePlex(
        items=[
            {"email": "a@x.com", "plex_user_id": 1},
            {"email": "b@x.com", "plex_user_id": 2},
        ]
    )

    active, revoked = await run_daily_sync(repo, plex)  # type: ignore[arg-type]

    assert active == 2
    assert revoked == 1

    # Verify c is actually revoked
    c_row = await repo.get_shared_user_by_email("c@x.com")
    assert c_row is not None
    assert c_row["status"] == "revoked"

    # Verify a and b are active
    a_row = await repo.get_shared_user_by_email("a@x.com")
    assert a_row is not None
    assert a_row["status"] == "active"

    b_row = await repo.get_shared_user_by_email("b@x.com")
    assert b_row is not None
    assert b_row["status"] == "active"


async def test_run_daily_sync_plex_failure_returns_zeros(repo: Repo) -> None:
    """When plex.list_shared raises PlexUnreachable, returns (0, 0) without mutating DB."""
    now = int(time.time())

    await repo.upsert_plex_server_cache("MID", "X")
    await repo.upsert_shared_user("u@x.com", None, 7, shared_at=now, last_seen_in_plex=now)

    plex = FakePlex(side_effect=PlexUnreachable("boom"))

    result = await run_daily_sync(repo, plex)  # type: ignore[arg-type]

    assert result == (0, 0)

    # Pre-existing row was not mutated
    row = await repo.get_shared_user_by_email("u@x.com")
    assert row is not None
    assert row["status"] == "active"
