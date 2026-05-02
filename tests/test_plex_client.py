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


# --- list_shared tests ---

LIST_SHARED_URL = "https://plex.tv/api/v2/shared_servers"


@respx.mock
async def test_list_shared_happy_path(plex_client: PlexClient) -> None:
    respx.get(LIST_SHARED_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"invitedEmail": "alice@example.com", "userId": 111},
                {"email": "bob@example.com", "user": {"id": 222}},
            ],
        )
    )
    result = await plex_client.list_shared("MACHINEID")
    assert result == [
        {"email": "alice@example.com", "plex_user_id": 111},
        {"email": "bob@example.com", "plex_user_id": 222},
    ]


@respx.mock
async def test_list_shared_skips_items_without_email(plex_client: PlexClient) -> None:
    respx.get(LIST_SHARED_URL).mock(
        return_value=httpx.Response(
            200,
            json=[
                {"invitedEmail": "alice@example.com", "userId": 111},
                {"userId": 999},
                {"user": {"id": 888}},
            ],
        )
    )
    result = await plex_client.list_shared("MACHINEID")
    assert result == [{"email": "alice@example.com", "plex_user_id": 111}]


@respx.mock
async def test_list_shared_401_raises_auth_error(plex_client: PlexClient) -> None:
    respx.get(LIST_SHARED_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(PlexAuthError):
        await plex_client.list_shared("MACHINEID")


@respx.mock
async def test_list_shared_5xx_raises_unreachable(plex_client: PlexClient) -> None:
    respx.get(LIST_SHARED_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(PlexUnreachable):
        await plex_client.list_shared("MACHINEID")


@respx.mock
async def test_list_shared_network_error_raises_unreachable(plex_client: PlexClient) -> None:
    respx.get(LIST_SHARED_URL).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(PlexUnreachable):
        await plex_client.list_shared("MACHINEID")


@respx.mock
async def test_list_shared_empty_returns_empty_list(plex_client: PlexClient) -> None:
    respx.get(LIST_SHARED_URL).mock(return_value=httpx.Response(200, json=[]))
    result = await plex_client.list_shared("MACHINEID")
    assert result == []
