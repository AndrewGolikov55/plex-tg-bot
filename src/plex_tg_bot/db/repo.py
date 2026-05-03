from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


class Repo:
    def __init__(self, db_path: str) -> None:
        self._path = db_path
        self._db: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        if self._db is not None:
            return
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("Repo not connected; call await repo.connect() first")
        return self._db

    async def upsert_user(self, telegram_id: int, username: str | None,
                          display_name: str, language: str) -> None:
        now = int(time.time())
        await self.db.execute(
            """INSERT INTO users
                 (telegram_id, username, display_name, language, created_at, updated_at)
               VALUES(?, ?, ?, ?, ?, ?)
               ON CONFLICT(telegram_id) DO UPDATE SET
                 username=excluded.username, display_name=excluded.display_name,
                 language=excluded.language, updated_at=excluded.updated_at""",
            (telegram_id, username, display_name, language, now, now),
        )
        await self.db.commit()

    async def get_user(self, telegram_id: int) -> dict[str, Any] | None:
        async with self.db.execute(
            "SELECT * FROM users WHERE telegram_id=?", (telegram_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def create_request(self, telegram_id: int, email: str, referrer: str,
                             admin_chat_id: int, admin_msg_id: int | None) -> int:
        now = int(time.time())
        async with self.db.execute(
            """INSERT INTO requests(telegram_id, email, referrer, status,
                                    admin_chat_id, admin_msg_id, created_at)
               VALUES(?, ?, ?, 'pending', ?, ?, ?)""",
            (telegram_id, email, referrer, admin_chat_id, admin_msg_id, now),
        ) as cur:
            await self.db.commit()
            return cur.lastrowid  # type: ignore[return-value]

    async def set_request_admin_msg_id(self, request_id: int, admin_msg_id: int) -> None:
        await self.db.execute(
            "UPDATE requests SET admin_msg_id=? WHERE id=?", (admin_msg_id, request_id)
        )
        await self.db.commit()

    async def get_pending_request_for_user(self, telegram_id: int) -> dict[str, Any] | None:
        async with self.db.execute(
            "SELECT * FROM requests"
            " WHERE telegram_id=? AND status='pending' ORDER BY id DESC LIMIT 1",
            (telegram_id,),
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def get_request(self, request_id: int) -> dict[str, Any] | None:
        async with self.db.execute(
            "SELECT * FROM requests WHERE id=?", (request_id,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def claim_request(self, request_id: int, decided_by: int, decided_at: int) -> bool:
        async with self.db.execute(
            """UPDATE requests SET decided_by=?, decided_at=?
               WHERE id=? AND status='pending' AND decided_at IS NULL""",
            (decided_by, decided_at, request_id),
        ) as cur:
            await self.db.commit()
            return cur.rowcount == 1

    async def rollback_claim(self, request_id: int) -> None:
        await self.db.execute(
            "UPDATE requests SET decided_by=NULL, decided_at=NULL "
            "WHERE id=? AND status='pending'",
            (request_id,),
        )
        await self.db.commit()

    async def finalize_approve(self, request_id: int) -> None:
        await self.db.execute(
            "UPDATE requests SET status='approved' WHERE id=?", (request_id,)
        )
        await self.db.commit()

    async def finalize_reject(self, request_id: int, reason: str | None) -> None:
        await self.db.execute(
            "UPDATE requests SET status='rejected', reject_reason=? WHERE id=?",
            (reason, request_id),
        )
        await self.db.commit()

    async def list_pending_requests(self) -> list[dict[str, Any]]:
        async with self.db.execute(
            "SELECT * FROM requests WHERE status='pending' ORDER BY id DESC"
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def list_users_overview(self) -> list[dict[str, Any]]:
        async with self.db.execute(
            """SELECT u.telegram_id, u.username, u.display_name,
                      su.email, su.status AS shared_status, su.shared_at
               FROM users u LEFT JOIN shared_users su ON su.telegram_id = u.telegram_id"""
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def upsert_shared_user(self, email: str, telegram_id: int | None,
                                 plex_user_id: int, shared_at: int,
                                 last_seen_in_plex: int) -> None:
        await self.db.execute(
            """INSERT INTO shared_users
                 (email, telegram_id, plex_user_id, status, shared_at, last_seen_in_plex)
               VALUES(?, ?, ?, 'active', ?, ?)
               ON CONFLICT(email) DO UPDATE SET
                 telegram_id=COALESCE(excluded.telegram_id, shared_users.telegram_id),
                 plex_user_id=excluded.plex_user_id,
                 status='active',
                 last_seen_in_plex=excluded.last_seen_in_plex,
                 revoked_at=NULL""",
            (email, telegram_id, plex_user_id, shared_at, last_seen_in_plex),
        )
        await self.db.commit()

    async def get_shared_user_by_email(self, email: str) -> dict[str, Any] | None:
        async with self.db.execute(
            "SELECT * FROM shared_users WHERE email=?", (email,)
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def has_active_access(self, telegram_id: int) -> bool:
        async with self.db.execute(
            "SELECT 1 FROM shared_users WHERE telegram_id=? AND status='active' LIMIT 1",
            (telegram_id,),
        ) as cur:
            return (await cur.fetchone()) is not None

    async def update_last_seen(self, email: str, ts: int) -> None:
        await self.db.execute(
            "UPDATE shared_users"
            " SET last_seen_in_plex=?, status='active', revoked_at=NULL WHERE email=?",
            (ts, email),
        )
        await self.db.commit()

    async def mark_revoked_if_stale(self, threshold_ts: int) -> None:
        now = int(time.time())
        await self.db.execute(
            """UPDATE shared_users SET status='revoked', revoked_at=?
               WHERE status='active' AND last_seen_in_plex < ?""",
            (now, threshold_ts),
        )
        await self.db.commit()

    async def count_active_shared(self) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) AS c FROM shared_users WHERE status='active'"
        ) as cur:
            row = await cur.fetchone()
            return int(row["c"]) if row else 0

    async def count_shared_users(self) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) AS c FROM shared_users"
        ) as cur:
            row = await cur.fetchone()
            return int(row["c"]) if row else 0

    async def list_shared_users_paginated(
        self, offset: int, limit: int
    ) -> list[dict[str, Any]]:
        async with self.db.execute(
            """SELECT su.email, su.status, su.shared_at, su.last_seen_in_plex,
                      su.telegram_id, u.username, u.display_name
               FROM shared_users su
               LEFT JOIN users u ON u.telegram_id = su.telegram_id
               ORDER BY su.shared_at DESC
               LIMIT ? OFFSET ?""",
            (limit, offset),
        ) as cur:
            return [dict(r) for r in await cur.fetchall()]

    async def delete_shared_user(self, email: str) -> None:
        await self.db.execute(
            "DELETE FROM shared_users WHERE email=?", (email,)
        )
        await self.db.commit()

    async def count_pending_requests(self) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) AS c FROM requests WHERE status='pending'"
        ) as cur:
            row = await cur.fetchone()
            return int(row["c"]) if row else 0

    async def upsert_plex_server_cache(self, machine_identifier: str, friendly_name: str) -> None:
        now = int(time.time())
        await self.db.execute(
            """INSERT INTO plex_server_cache(id, machine_identifier, friendly_name, refreshed_at)
               VALUES(1, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET
                 machine_identifier=excluded.machine_identifier,
                 friendly_name=excluded.friendly_name,
                 refreshed_at=excluded.refreshed_at""",
            (machine_identifier, friendly_name, now),
        )
        await self.db.commit()

    async def get_plex_server_cache(self) -> dict[str, Any] | None:
        async with self.db.execute(
            "SELECT * FROM plex_server_cache WHERE id=1"
        ) as cur:
            row = await cur.fetchone()
            return dict(row) if row else None

    async def count_revoked_in_window(self, since_ts: int) -> int:
        async with self.db.execute(
            "SELECT COUNT(*) AS c FROM shared_users WHERE status='revoked' AND revoked_at >= ?",
            (since_ts,),
        ) as cur:
            row = await cur.fetchone()
            return int(row["c"]) if row else 0
