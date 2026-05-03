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

    async def share_server(
        self,
        machine_identifier: str,
        email: str,
        library_section_ids: list[int],
        allow_sync: str,
        allow_camera_upload: str,
        allow_channels: str,
    ) -> tuple[int, str | None]:
        body = {
            "machineIdentifier": machine_identifier,
            "invitedEmail": email,
            "librarySectionIds": library_section_ids,
            "settings": {
                "allowSync": allow_sync,
                "allowCameraUpload": allow_camera_upload,
                "allowChannels": allow_channels,
            },
        }
        try:
            r = await self._http.post(
                f"{self.BASE}/shared_servers",
                headers={**self._headers(), "Content-Type": "application/json"},
                json=body,
            )
        except httpx.HTTPError as e:
            raise PlexUnreachable(str(e)) from e
        if r.status_code == 401:
            raise PlexAuthError()
        if r.status_code == 422:
            try:
                data = r.json()
                uid = int(data.get("userId") or 0)
                token = data.get("inviteToken")
            except (ValueError, TypeError, AttributeError):
                uid = 0
                token = None
            raise PlexAlreadyShared(uid, token)
        if r.status_code >= 400:
            # any other 4xx/5xx is treated as transient — Phase 7 will rollback
            raise PlexUnreachable(f"status {r.status_code}")
        data = r.json()
        uid = int(data.get("userId") or data.get("user", {}).get("id") or 0)
        token = data.get("inviteToken")
        return (uid, token)

    async def list_shared(
        self, machine_identifier: str
    ) -> list[dict[str, str | int | None]]:
        """List users who currently have access to our server.

        Plex deprecated `GET /api/v2/shared_servers` (now returns 405). The
        replacement walks `/api/v2/friends?includeSharedServers=1` and filters
        each friend's `sharedServers` array by our machine_identifier. Skips
        entries with `deletedAt` or `leftAt` set (revoked / left voluntarily).

        Returned dicts carry the same `id` / `email` / `plex_user_id` keys as
        before for caller compatibility, plus a new `invite_token` field
        (string or None) — the per-share token Plex Web uses to construct the
        accept URL `https://app.plex.tv/desktop/#!/sharing-invite?inviteToken=<...>`.
        """
        try:
            # includeSharedServers=1 makes the response significantly larger,
            # giving the Plex backend more work — bump the per-request timeout.
            r = await self._http.get(
                f"{self.BASE}/friends",
                headers=self._headers(),
                params={"includeSharedServers": "1"},
                timeout=60.0,
            )
        except httpx.HTTPError as e:
            raise PlexUnreachable(str(e)) from e
        if r.status_code == 401:
            raise PlexAuthError()
        if r.status_code >= 400:
            raise PlexUnreachable(f"status {r.status_code}")
        out: list[dict[str, str | int | None]] = []
        for friend in r.json():
            email = friend.get("email") or ""
            plex_user_id = int(friend.get("id") or 0)
            if not email:
                continue
            for ss in friend.get("sharedServers") or []:
                if ss.get("machineIdentifier") != machine_identifier:
                    continue
                if ss.get("deletedAt") or ss.get("leftAt"):
                    continue
                out.append(
                    {
                        "id": int(ss.get("id") or 0),
                        "email": email,
                        "plex_user_id": plex_user_id,
                        "invite_token": ss.get("inviteToken"),
                    }
                )
        return out

    async def revoke_share(self, plex_user_id: int) -> None:
        """Revoke access for a Plex user via the friends endpoint.

        Uses `DELETE /api/v2/friends/{plex_user_id}` — the same endpoint
        python-plexapi's `MyPlexAccount.removeFriend()` calls. It removes
        the friend relationship, which includes server share. Returns
        silently on 404 (already gone). 200 / 204 are both treated as
        success. Raises PlexAuthError on 401 or PlexUnreachable on
        network / 4xx-other / 5xx.

        Note: we deliberately switched away from
        `DELETE /api/v2/shared_servers/{id}` because Plex returns
        HTTP 405 (Method Not Allowed) on that path — the v2 API does
        not support DELETE on shared_servers."""
        if plex_user_id <= 0:
            # No usable Plex id (e.g. invite still pending). Nothing to revoke
            # server-side; caller will still purge the local DB row.
            return
        try:
            r = await self._http.delete(
                f"{self.BASE}/friends/{plex_user_id}",
                headers=self._headers(),
            )
        except httpx.HTTPError as e:
            raise PlexUnreachable(str(e)) from e
        if r.status_code == 401:
            raise PlexAuthError()
        if r.status_code == 404:
            return
        if r.status_code >= 400:
            raise PlexUnreachable(f"status {r.status_code}")

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
