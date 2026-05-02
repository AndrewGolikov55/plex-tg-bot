import time
from collections.abc import AsyncGenerator
from pathlib import Path

import pytest_asyncio

from plex_tg_bot.db.repo import Repo


@pytest_asyncio.fixture
async def repo(tmp_path: Path) -> AsyncGenerator[Repo, None]:
    r = Repo(str(tmp_path / "test.sqlite"))
    await r.connect()
    yield r
    await r.close()


async def test_upsert_user(repo: Repo) -> None:
    await repo.upsert_user(telegram_id=42, username="vasya", display_name="V", language="en")
    u = await repo.get_user(42)
    assert u is not None
    assert u["username"] == "vasya"


async def test_create_request_and_lookup(repo: Repo) -> None:
    await repo.upsert_user(42, "v", "V", "en")
    rid = await repo.create_request(
        telegram_id=42, email="v@e.com", referrer="From Andrey",
        admin_chat_id=-100, admin_msg_id=None,
    )
    pending = await repo.get_pending_request_for_user(42)
    assert pending is not None and pending["id"] == rid


async def test_claim_request_atomically(repo: Repo) -> None:
    await repo.upsert_user(42, "v", "V", "en")
    rid = await repo.create_request(42, "v@e.com", "ref", -100, None)
    ok = await repo.claim_request(rid, decided_by=99, decided_at=int(time.time()))
    assert ok is True
    ok2 = await repo.claim_request(rid, decided_by=100, decided_at=int(time.time()))
    assert ok2 is False  # already claimed


async def test_rollback_claim(repo: Repo) -> None:
    await repo.upsert_user(42, "v", "V", "en")
    rid = await repo.create_request(42, "v@e.com", "ref", -100, None)
    await repo.claim_request(rid, decided_by=99, decided_at=int(time.time()))
    await repo.rollback_claim(rid)
    ok_again = await repo.claim_request(rid, decided_by=100, decided_at=int(time.time()))
    assert ok_again is True  # back to pending


async def test_rollback_claim_does_not_touch_finalized(repo: Repo) -> None:
    await repo.upsert_user(42, "v", "V", "en")
    rid = await repo.create_request(42, "v@e.com", "ref", -100, None)
    await repo.claim_request(rid, decided_by=99, decided_at=int(time.time()))
    await repo.finalize_approve(rid)
    await repo.rollback_claim(rid)  # must be a no-op on approved
    req = await repo.get_request(rid)
    assert req is not None
    assert req["status"] == "approved"
    assert req["decided_by"] == 99
    assert req["decided_at"] is not None


async def test_connect_idempotent(tmp_path: Path) -> None:
    r = Repo(str(tmp_path / "x.sqlite"))
    await r.connect()
    await r.connect()  # second call must be a no-op
    await r.upsert_user(1, "u", "U", "en")
    u = await r.get_user(1)
    assert u is not None
    await r.close()
    await r.close()  # second close must be safe


async def test_finalize_approve_and_shared_users(repo: Repo) -> None:
    await repo.upsert_user(42, "v", "V", "en")
    rid = await repo.create_request(42, "v@e.com", "ref", -100, None)
    await repo.claim_request(rid, decided_by=99, decided_at=int(time.time()))
    await repo.upsert_shared_user(
        email="v@e.com", telegram_id=42, plex_user_id=1234,
        shared_at=int(time.time()), last_seen_in_plex=int(time.time()),
    )
    await repo.finalize_approve(rid)
    su = await repo.get_shared_user_by_email("v@e.com")
    assert su is not None
    assert su["status"] == "active"
    assert (await repo.has_active_access(42)) is True


async def test_finalize_reject(repo: Repo) -> None:
    await repo.upsert_user(42, "v", "V", "en")
    rid = await repo.create_request(42, "v@e.com", "ref", -100, None)
    await repo.claim_request(rid, decided_by=99, decided_at=int(time.time()))
    await repo.finalize_reject(rid, reason="spam")
    pend = await repo.get_pending_request_for_user(42)
    assert pend is None


async def test_daily_sync_revokes_missing(repo: Repo) -> None:
    now = int(time.time())
    await repo.upsert_shared_user("a@e.com", None, 1, now, now)
    await repo.upsert_shared_user("b@e.com", None, 2, now, now - 86400 * 2)
    await repo.mark_revoked_if_stale(threshold_ts=now - 86400)
    a = await repo.get_shared_user_by_email("a@e.com")
    b = await repo.get_shared_user_by_email("b@e.com")
    assert a is not None
    assert b is not None
    assert a["status"] == "active"
    assert b["status"] == "revoked"


async def test_plex_server_cache(repo: Repo) -> None:
    await repo.upsert_plex_server_cache("MID", "MyServer")
    c = await repo.get_plex_server_cache()
    assert c is not None
    assert c["machine_identifier"] == "MID"
