"""Apps content (Telegram-HTML) lives in src/plex_tg_bot/i18n/apps/<lang>.html.

Bot loads at startup via load_apps(lang) — fail-fast on missing locale.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from plex_tg_bot.i18n.loader import load_apps

LOCALES_DIR = Path(__file__).resolve().parent.parent / "src" / "plex_tg_bot" / "i18n"
APPS_DIR = LOCALES_DIR / "apps"

ALLOWED_TAGS = {
    "b", "strong", "i", "em", "u", "s", "strike", "del",
    "a", "code", "pre", "blockquote", "tg-spoiler", "tg-emoji",
    "br",  # not officially in Telegram allow-list but harmless
}
TAG_RE = re.compile(r"<\s*/?\s*([a-zA-Z][\w-]*)")


def _shipped_locales() -> list[str]:
    return sorted(p.stem for p in LOCALES_DIR.glob("*.yml"))


@pytest.mark.parametrize("lang", _shipped_locales())
def test_apps_html_exists_and_nonempty(lang: str) -> None:
    text = load_apps(lang)
    assert text.strip(), f"i18n/apps/{lang}.html is empty"


@pytest.mark.parametrize("lang", _shipped_locales())
def test_apps_html_uses_only_allowed_tags(lang: str) -> None:
    text = load_apps(lang)
    used = {m.group(1).lower() for m in TAG_RE.finditer(text)}
    bad = used - ALLOWED_TAGS
    assert not bad, f"i18n/apps/{lang}.html uses tags Telegram won't render: {bad}"


def test_load_apps_missing_locale_raises() -> None:
    with pytest.raises(FileNotFoundError, match="missing"):
        load_apps("xx-not-a-locale")


def test_load_apps_returns_str() -> None:
    text = load_apps("en")
    assert isinstance(text, str)
