"""Minimal UI translation layer (no dependencies).

Source strings in the code are Turkish and act as the lookup key: ``tr("Kapat")`` returns the English text when the
language is "en" (default) and the Turkish source text when it is "tr". Unknown keys fall back to the source text.
Leading symbols/emoji and surrounding whitespace are not part of the key (they are re-attached), so
``tr("🧹 Tüm Widget'ları Kapat")`` finds "Tüm Widget'ları Kapat".
Asset/category ids and file names are never translated; only what the user sees.
"""

from __future__ import annotations

import re
from typing import Optional

LANGUAGES = {"en": "English", "tr": "Türkçe"}
DEFAULT_LANGUAGE = "en"
_lang = DEFAULT_LANGUAGE
_PREFIX = re.compile(r"^[^A-Za-z0-9çğıöşüÇĞİÖŞÜ\[\(\{%'\"\\]*")


def set_language(code: Optional[str]) -> str:
    global _lang
    _lang = code if code in LANGUAGES else DEFAULT_LANGUAGE
    return _lang


def get_language() -> str:
    return _lang


def tr(text: str) -> str:
    """Translate a (Turkish) source string for the current language."""
    if _lang == "tr":
        return text
    from src.core.i18n_en import EN  # lazy: keeps import cost off the Turkish path

    hit = EN.get(text)
    if hit is not None:
        return hit
    pre = _PREFIX.match(text).group(0)
    rest = text[len(pre):]
    core = rest.rstrip()
    hit = EN.get(core)
    return pre + hit + rest[len(core):] if hit is not None else text


def category_label(category: str) -> str:
    """Displayed category name (the stored category string is never changed, so favourites keep working)."""
    return tr(category)


def asset_label(asset) -> str:
    """Displayed asset name: `name_en` (optional JSON field) in English, otherwise `name`."""
    if _lang == "en":
        en = getattr(asset, "name_en", "") or ""
        if en:
            return en
        from src.core.i18n_names_en import NAMES_EN

        return NAMES_EN.get(asset.name, asset.name)
    return asset.name
