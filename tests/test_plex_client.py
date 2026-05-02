import httpx
import pytest
import respx

from plex_tg_bot.services.plex import PlexClient


@pytest.fixture
def plex_client() -> PlexClient:
    return PlexClient(
        token="tok",
        client_identifier="plex-tg-bot/0.1.0",
        http=httpx.AsyncClient(),
    )


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
