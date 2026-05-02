import pytest

from plex_tg_bot.config import Settings


def _base_env() -> dict[str, str]:
    return {
        "TELEGRAM_BOT_TOKEN": "123:abc",
        "ADMIN_CHAT_ID": "-100123",
        "PLEX_TOKEN": "tok",
    }


def test_required_only(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.telegram_bot_token == "123:abc"
    assert s.admin_chat_id == -100123
    assert s.plex_token == "tok"
    assert s.bot_lang == "en"
    assert s.health_port == 9095
    assert s.daily_sync_cron == "0 4 * * *"
    assert s.allow_sync == "1"
    assert s.proxy_url is None
    assert s.shared_library_ids == []


def test_missing_required_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("TELEGRAM_BOT_TOKEN", "ADMIN_CHAT_ID", "PLEX_TOKEN"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(Exception):  # noqa: B017
        Settings()


def test_overseerr_partial_invalid(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("OVERSEERR_PUBLIC_URL", "https://o.example.com")
    monkeypatch.delenv("OVERSEERR_API_KEY", raising=False)
    with pytest.raises(ValueError, match="OVERSEERR_API_KEY"):
        Settings()


def test_overseerr_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    s = Settings()
    assert s.overseerr_enabled is False


def test_proxy_url_propagates(monkeypatch: pytest.MonkeyPatch) -> None:
    for k, v in _base_env().items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("PROXY_URL", "socks5://1.2.3.4:1080")
    s = Settings()
    assert s.proxy_url == "socks5://1.2.3.4:1080"
