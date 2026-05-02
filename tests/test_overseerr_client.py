import httpx
import pytest
import respx

from plex_tg_bot.services.overseerr import OverseerrClient, OverseerrError

IMPORT_URL = "https://o.example.com/api/v1/user/import-from-plex"


@pytest.fixture
def client() -> OverseerrClient:
    return OverseerrClient("https://o.example.com", "key", httpx.AsyncClient())


@respx.mock
async def test_import_ok(client: OverseerrClient) -> None:
    respx.post(IMPORT_URL).mock(return_value=httpx.Response(200, json=[{"id": 1}]))
    await client.import_from_plex([1234])  # no exception


@respx.mock
async def test_import_5xx_raises(client: OverseerrClient) -> None:
    respx.post(IMPORT_URL).mock(return_value=httpx.Response(503))
    with pytest.raises(OverseerrError):
        await client.import_from_plex([1234])


@respx.mock
async def test_import_network_error_raises(client: OverseerrClient) -> None:
    respx.post(IMPORT_URL).mock(side_effect=httpx.ConnectError("boom"))
    with pytest.raises(OverseerrError):
        await client.import_from_plex([1234])


@respx.mock
async def test_import_401_raises(client: OverseerrClient) -> None:
    respx.post(IMPORT_URL).mock(return_value=httpx.Response(401))
    with pytest.raises(OverseerrError):
        await client.import_from_plex([1234])


@respx.mock
async def test_import_4xx_raises(client: OverseerrClient) -> None:
    respx.post(IMPORT_URL).mock(return_value=httpx.Response(404))
    with pytest.raises(OverseerrError):
        await client.import_from_plex([1234])
