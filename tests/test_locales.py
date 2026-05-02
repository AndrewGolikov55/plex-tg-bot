import re
from pathlib import Path

import yaml

from plex_tg_bot.i18n.loader import _flatten, set_lang, t

LOCALES_DIR = Path(__file__).resolve().parent.parent / "src" / "plex_tg_bot" / "i18n"
PLACEHOLDER_RE = re.compile(r"\{(\w+)\}")


def _load(name: str) -> dict[str, str]:
    raw = yaml.safe_load((LOCALES_DIR / f"{name}.yml").read_text(encoding="utf-8"))
    return _flatten(raw)


def test_keys_match() -> None:
    en = _load("en")
    ru = _load("ru")
    assert set(en.keys()) == set(ru.keys())


def test_placeholders_match() -> None:
    en = _load("en")
    ru = _load("ru")
    for k in en:
        en_p = set(PLACEHOLDER_RE.findall(en[k]))
        ru_p = set(PLACEHOLDER_RE.findall(ru[k]))
        assert en_p == ru_p, f"placeholder mismatch on key {k}"


def test_t_substitutes() -> None:
    set_lang("en")
    assert "vasya@example.com" in t("notify_user.approved", email="vasya@example.com")


def test_t_unknown_key_raises() -> None:
    set_lang("en")
    import pytest
    with pytest.raises(KeyError):
        t("nonexistent.key")
