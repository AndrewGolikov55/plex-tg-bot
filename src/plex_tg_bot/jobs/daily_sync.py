from __future__ import annotations

import logging
import time

from plex_tg_bot.db import Repo
from plex_tg_bot.services.plex import PlexAuthError, PlexClient, PlexUnreachable

log = logging.getLogger(__name__)


async def run_daily_sync(repo: Repo, plex: PlexClient) -> tuple[int, int]:
    cache = await repo.get_plex_server_cache()
    if cache is None:
        log.warning("daily_sync: no server cache")
        return (0, 0)

    now = int(time.time())
    window_start = now

    try:
        items = await plex.list_shared(cache["machine_identifier"])
    except (PlexUnreachable, PlexAuthError) as e:
        log.warning("daily_sync: plex error %s", e)
        return (0, 0)

    for item in items:
        await repo.upsert_shared_user(
            email=str(item["email"]),
            telegram_id=None,
            plex_user_id=int(item["plex_user_id"] or 0),
            shared_at=now,
            last_seen_in_plex=now,
        )

    threshold = now - 86400
    await repo.mark_revoked_if_stale(threshold)

    active = await repo.count_active_shared()
    revoked = await repo.count_revoked_in_window(window_start)
    return (active, revoked)
