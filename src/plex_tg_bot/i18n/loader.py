from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

_LOCALES: dict[str, dict[str, str]] = {}
_LANG: str = "en"
_DIR = Path(__file__).resolve().parent


def _flatten(d: dict[str, Any], prefix: str = "") -> dict[str, str]:
    out: dict[str, str] = {}
    for k, v in d.items():
        key = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flatten(v, key))
        else:
            out[key] = str(v)
    return out


def _load(lang: str) -> dict[str, str]:
    path = _DIR / f"{lang}.yml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _flatten(raw)


def set_lang(lang: str) -> None:
    global _LANG
    if lang not in _LOCALES:
        _LOCALES[lang] = _load(lang)
    _LANG = lang


def t(key: str, **kwargs: Any) -> str:
    if _LANG not in _LOCALES:
        _LOCALES[_LANG] = _load(_LANG)
    try:
        template = _LOCALES[_LANG][key]
    except KeyError:
        raise KeyError(f"{key!r} not found in locale '{_LANG}'") from None
    return template.format(**kwargs) if kwargs else template
