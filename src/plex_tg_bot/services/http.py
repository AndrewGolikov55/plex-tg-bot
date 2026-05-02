from __future__ import annotations

import os

import httpx


def make_async_client(proxy_url: str | None, no_proxy: str | None,
                      timeout_s: float = 30.0) -> httpx.AsyncClient:
    if proxy_url:
        # Set env so httpx picks them up, including NO_PROXY semantics
        os.environ.setdefault("HTTPS_PROXY", proxy_url)
        os.environ.setdefault("HTTP_PROXY", proxy_url)
    if no_proxy:
        os.environ.setdefault("NO_PROXY", no_proxy)
    return httpx.AsyncClient(timeout=httpx.Timeout(timeout_s), trust_env=True)
