from __future__ import annotations

import time
from collections.abc import AsyncGenerator

import pytest
from aiohttp.test_utils import TestClient, TestServer

from plex_tg_bot.http_server import Observability, make_http_app


@pytest.fixture
async def client() -> AsyncGenerator[TestClient, None]:
    obs = Observability()
    app = make_http_app(obs)
    server = TestServer(app)
    tc = TestClient(server)
    await tc.start_server()
    try:
        yield tc
    finally:
        await tc.close()


async def test_healthz_ok_when_recent(client: TestClient) -> None:
    r = await client.get("/healthz")
    assert r.status == 200
    body = await r.json()
    assert body["status"] == "ok"


async def test_healthz_stale_returns_503() -> None:
    obs = Observability()
    obs.last_tg_update.set(time.time() - 700)  # stale
    app = make_http_app(obs)
    server = TestServer(app)
    tc = TestClient(server)
    await tc.start_server()
    try:
        r = await tc.get("/healthz")
        assert r.status == 503
        body = await r.json()
        assert body["status"] == "stale"
    finally:
        await tc.close()


async def test_metrics_exposes_known_metric_names(client: TestClient) -> None:
    r = await client.get("/metrics")
    assert r.status == 200
    text = await r.text()
    assert "plexbot_telegram_last_update_ts" in text
    assert "plexbot_pending_requests" in text
    assert "plexbot_requests_total" in text


async def test_healthz_response_contains_last_tg_update_field(client: TestClient) -> None:
    r = await client.get("/healthz")
    body = await r.json()
    assert "last_tg_update" in body
    assert isinstance(body["last_tg_update"], float)


async def test_metrics_exposes_all_defined_metrics(client: TestClient) -> None:
    r = await client.get("/metrics")
    text = await r.text()
    for name in [
        "plexbot_telegram_last_update_ts",
        "plexbot_pending_requests",
        "plexbot_shared_users_active",
        "plexbot_requests_total",
        "plexbot_plex_api_errors_total",
        "plexbot_plex_auth_errors_total",
        "plexbot_overseerr_import_errors_total",
        "plexbot_daily_sync_last_ts",
        "plexbot_daily_sync_failures_total",
    ]:
        assert name in text, f"{name} not found in /metrics output"
