from __future__ import annotations

import httpx


class PlexAuthError(Exception):
    pass


class PlexUnreachable(Exception):
    pass


class PlexAlreadyShared(Exception):
    pass


class PlexClient:
    BASE = "https://plex.tv/api/v2"

    def __init__(self, token: str, client_identifier: str, http: httpx.AsyncClient) -> None:
        self._token = token
        self._cid = client_identifier
        self._http = http

    def _headers(self) -> dict[str, str]:
        return {
            "X-Plex-Token": self._token,
            "X-Plex-Client-Identifier": self._cid,
            "Accept": "application/json",
        }

    async def discover_server(self) -> tuple[str, str]:
        r = await self._http.get(
            f"{self.BASE}/resources",
            headers=self._headers(),
            params={"includeHttps": 1},
        )
        if r.status_code == 401:
            raise PlexAuthError()
        if r.status_code >= 500:
            raise PlexUnreachable()
        r.raise_for_status()
        for item in r.json():
            provides = item.get("provides", "")
            if "server" in provides and item.get("owned"):
                return item["clientIdentifier"], item["name"]
        raise PlexUnreachable("no owned server found")
