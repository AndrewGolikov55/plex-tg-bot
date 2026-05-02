from __future__ import annotations

import httpx


class OverseerrError(Exception):
    pass


class OverseerrClient:
    def __init__(self, base_url: str, api_key: str, http: httpx.AsyncClient) -> None:
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._http = http

    async def import_from_plex(self, plex_user_ids: list[int]) -> None:
        try:
            r = await self._http.post(
                f"{self._base}/api/v1/user/import-from-plex",
                headers={"X-Api-Key": self._key, "Content-Type": "application/json"},
                json={"plexIds": [str(uid) for uid in plex_user_ids]},
            )
        except httpx.HTTPError as e:
            raise OverseerrError(str(e)) from e
        if r.status_code >= 400:
            raise OverseerrError(f"status {r.status_code}")
