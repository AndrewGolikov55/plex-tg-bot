import httpx
import pytest
import respx

from plex_tg_bot.services.plex import PlexAlreadyShared, PlexAuthError, PlexClient, PlexUnreachable

SHARE_URL = "https://plex.tv/api/v2/shared_servers"


@pytest.fixture
def plex_client() -> PlexClient:
    return PlexClient(
        token="tok",
        client_identifier="plex-tg-bot/0.1.0",
        http=httpx.AsyncClient(),
    )


def _share_kwargs() -> dict[str, object]:
    return {
        "machine_identifier": "MACHINEID",
        "email": "user@example.com",
        "library_section_ids": [1, 2],
        "allow_sync": "0",
        "allow_camera_upload": "0",
        "allow_channels": "0",
    }


@respx.mock
async def test_discover_server_picks_owned(plex_client: PlexClient) -> None:
    respx.get("https://plex.tv/api/v2/resources").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "name": "Other",
                    "clientIdentifier": "OTHER",
                    "owned": False,
                    "provides": "server",
                },
                {
                    "name": "Mine",
                    "clientIdentifier": "MID",
                    "owned": True,
                    "provides": "server",
                },
            ],
        )
    )
    out = await plex_client.discover_server()
    assert out == ("MID", "Mine")


# --- share_server tests ---


@respx.mock
async def test_share_server_success_user_id(plex_client: PlexClient) -> None:
    respx.post(SHARE_URL).mock(return_value=httpx.Response(200, json={"userId": 1234}))
    uid = await plex_client.share_server(**_share_kwargs())  # type: ignore[arg-type]
    assert uid == 1234


@respx.mock
async def test_share_server_success_user_id_nested(plex_client: PlexClient) -> None:
    respx.post(SHARE_URL).mock(
        return_value=httpx.Response(200, json={"user": {"id": 5678}})
    )
    uid = await plex_client.share_server(**_share_kwargs())  # type: ignore[arg-type]
    assert uid == 5678


@respx.mock
async def test_share_server_422_with_user_id(plex_client: PlexClient) -> None:
    respx.post(SHARE_URL).mock(return_value=httpx.Response(422, json={"userId": 7}))
    with pytest.raises(PlexAlreadyShared) as exc_info:
        await plex_client.share_server(**_share_kwargs())  # type: ignore[arg-type]
    assert exc_info.value.args[0] == 7


@respx.mock
async def test_share_server_422_without_user_id(plex_client: PlexClient) -> None:
    respx.post(SHARE_URL).mock(return_value=httpx.Response(422, json={"error": "already shared"}))
    with pytest.raises(PlexAlreadyShared) as exc_info:
        await plex_client.share_server(**_share_kwargs())  # type: ignore[arg-type]
    assert exc_info.value.args[0] == 0


@respx.mock
async def test_share_server_422_non_json(plex_client: PlexClient) -> None:
    respx.post(SHARE_URL).mock(
        return_value=httpx.Response(
            422, content=b"not json", headers={"Content-Type": "text/plain"}
        )
    )
    with pytest.raises(PlexAlreadyShared) as exc_info:
        await plex_client.share_server(**_share_kwargs())  # type: ignore[arg-type]
    assert exc_info.value.args[0] == 0


@respx.mock
async def test_share_server_401_raises_auth_error(plex_client: PlexClient) -> None:
    respx.post(SHARE_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(PlexAuthError):
        await plex_client.share_server(**_share_kwargs())  # type: ignore[arg-type]


@respx.mock
async def test_share_server_5xx_raises_unreachable(plex_client: PlexClient) -> None:
    respx.post(SHARE_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(PlexUnreachable):
        await plex_client.share_server(**_share_kwargs())  # type: ignore[arg-type]


@respx.mock
async def test_share_server_network_error_raises_unreachable(plex_client: PlexClient) -> None:
    respx.post(SHARE_URL).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(PlexUnreachable):
        await plex_client.share_server(**_share_kwargs())  # type: ignore[arg-type]


@respx.mock
@pytest.mark.parametrize("status", [400, 403, 404, 429])
async def test_share_server_other_4xx_raises_unreachable(
    plex_client: PlexClient, status: int
) -> None:
    respx.post(SHARE_URL).mock(return_value=httpx.Response(status))
    with pytest.raises(PlexUnreachable):
        await plex_client.share_server(**_share_kwargs())  # type: ignore[arg-type]


# --- list_shared tests (uses /api/v2/friends?includeSharedServers=1) ---

FRIENDS_LIST_URL = "https://plex.tv/api/v2/friends"


def _friend(
    email: str,
    user_id: int,
    *,
    shared_id: int = 0,
    machine_identifier: str = "MID",
    invite_token: str | None = None,
    deleted_at: str | None = None,
    left_at: str | None = None,
) -> dict[str, object]:
    """Build a minimal /api/v2/friends record with one sharedServer entry."""
    return {
        "id": user_id,
        "email": email,
        "status": "accepted",
        "sharedServers": [
            {
                "id": shared_id,
                "machineIdentifier": machine_identifier,
                "inviteToken": invite_token,
                "deletedAt": deleted_at,
                "leftAt": left_at,
            }
        ],
    }


@respx.mock
async def test_list_shared_happy_path(plex_client: PlexClient) -> None:
    respx.get(FRIENDS_LIST_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                _friend("alice@example.com", 111, shared_id=11, invite_token="tokA"),
                _friend("bob@example.com", 222, shared_id=12),
            ],
        )
    )
    result = await plex_client.list_shared("MID")
    assert result == [
        {"id": 11, "email": "alice@example.com", "plex_user_id": 111, "invite_token": "tokA"},
        {"id": 12, "email": "bob@example.com", "plex_user_id": 222, "invite_token": None},
    ]


@respx.mock
async def test_list_shared_filters_by_machine_identifier(plex_client: PlexClient) -> None:
    """Friends sharing OTHER servers (not ours) must be excluded."""
    respx.get(FRIENDS_LIST_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                _friend("alice@example.com", 111, shared_id=11, machine_identifier="MID"),
                _friend("bob@example.com", 222, shared_id=22, machine_identifier="OTHER"),
            ],
        )
    )
    result = await plex_client.list_shared("MID")
    assert len(result) == 1
    assert result[0]["email"] == "alice@example.com"


@respx.mock
async def test_list_shared_skips_deleted_or_left_shares(plex_client: PlexClient) -> None:
    respx.get(FRIENDS_LIST_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                _friend("alice@example.com", 111, shared_id=11),
                _friend(
                    "bob@example.com", 222, shared_id=22, deleted_at="2026-05-04T00:00:00Z"
                ),
                _friend(
                    "carol@example.com", 333, shared_id=33, left_at="2026-05-04T00:00:00Z"
                ),
            ],
        )
    )
    result = await plex_client.list_shared("MID")
    assert [r["email"] for r in result] == ["alice@example.com"]


@respx.mock
async def test_list_shared_skips_friends_without_email(plex_client: PlexClient) -> None:
    respx.get(FRIENDS_LIST_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                _friend("alice@example.com", 111, shared_id=11),
                {
                    "id": 222,
                    "email": None,
                    "sharedServers": [
                        {"id": 22, "machineIdentifier": "MID", "inviteToken": None}
                    ],
                },
            ],
        )
    )
    result = await plex_client.list_shared("MID")
    assert len(result) == 1
    assert result[0]["email"] == "alice@example.com"


@respx.mock
async def test_list_shared_401_raises_auth_error(plex_client: PlexClient) -> None:
    respx.get(FRIENDS_LIST_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(PlexAuthError):
        await plex_client.list_shared("MID")


@respx.mock
async def test_list_shared_5xx_raises_unreachable(plex_client: PlexClient) -> None:
    respx.get(FRIENDS_LIST_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(PlexUnreachable):
        await plex_client.list_shared("MID")


@respx.mock
async def test_list_shared_network_error_raises_unreachable(plex_client: PlexClient) -> None:
    respx.get(FRIENDS_LIST_URL).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(PlexUnreachable):
        await plex_client.list_shared("MID")


@respx.mock
async def test_list_shared_empty_returns_empty_list(plex_client: PlexClient) -> None:
    respx.get(FRIENDS_LIST_URL).mock(return_value=httpx.Response(200, json=[]))
    result = await plex_client.list_shared("MID")
    assert result == []


# --- revoke_share tests (uses /api/v2/friends/{plex_user_id}) ---

FRIEND_URL = "https://plex.tv/api/v2/friends/42"


@respx.mock
async def test_revoke_share_happy_path(plex_client: PlexClient) -> None:
    delete_route = respx.delete(FRIEND_URL).mock(return_value=httpx.Response(200))
    await plex_client.revoke_share(42)
    assert delete_route.called


@respx.mock
async def test_revoke_share_204_treated_as_success(plex_client: PlexClient) -> None:
    respx.delete(FRIEND_URL).mock(return_value=httpx.Response(204))
    await plex_client.revoke_share(42)  # no raise


@respx.mock
async def test_revoke_share_zero_user_id_is_noop(plex_client: PlexClient) -> None:
    """plex_user_id == 0 means we never got a real id from Plex (e.g. pending
    invite). Don't even try the API — caller will still purge the local row."""
    delete_route = respx.delete(url__regex=r".+/friends/.+").mock(
        return_value=httpx.Response(200)
    )
    await plex_client.revoke_share(0)
    assert not delete_route.called


@respx.mock
async def test_revoke_share_404_treated_as_success(plex_client: PlexClient) -> None:
    respx.delete(FRIEND_URL).mock(return_value=httpx.Response(404))
    await plex_client.revoke_share(42)  # no raise


@respx.mock
async def test_revoke_share_401_raises_auth_error(plex_client: PlexClient) -> None:
    respx.delete(FRIEND_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(PlexAuthError):
        await plex_client.revoke_share(42)


@respx.mock
async def test_revoke_share_405_raises_unreachable(plex_client: PlexClient) -> None:
    """Regression: prior /shared_servers/{id} endpoint returned 405 in production.
    Any non-2xx, non-401, non-404 must raise PlexUnreachable so the admin
    panel shows the retry card."""
    respx.delete(FRIEND_URL).mock(return_value=httpx.Response(405))
    with pytest.raises(PlexUnreachable):
        await plex_client.revoke_share(42)


@respx.mock
async def test_revoke_share_5xx_raises_unreachable(plex_client: PlexClient) -> None:
    respx.delete(FRIEND_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(PlexUnreachable):
        await plex_client.revoke_share(42)


@respx.mock
async def test_revoke_share_network_error(plex_client: PlexClient) -> None:
    respx.delete(FRIEND_URL).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(PlexUnreachable):
        await plex_client.revoke_share(42)
