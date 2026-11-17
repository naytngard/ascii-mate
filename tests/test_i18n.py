"""Arayüz dili: İngilizce varsayılan, Türkçe seçenek; menü metinleri iki dilde offscreen doğrulanır."""

from __future__ import annotations

import json
import string
import sys
from pathlib import Path

import pytest

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "tools"))

from src.core import i18n  # noqa: E402
from src.core.config_manager import ConfigManager  # noqa: E402
from src.core.i18n_en import EN  # noqa: E402
from src.core.library import AnimationLibrary, ThemeLibrary  # noqa: E402

ANIM = BASE / "assets" / "animations"
TURKISH_CHARS = set("çğıöşüÇĞİÖŞÜ")


def _fields(s: str):
    return [(f or "", spec or "", conv or "") for _, f, spec, conv in string.Formatter().parse(s) if _ is not None or f is not None]


def test_default_language_is_english_and_switches():
    import importlib

    importlib.reload(i18n)  # modül varsayılanı (conftest 'tr' ayarını geçici olarak sıfırlar)
    assert i18n.get_language() == "en"
    assert i18n.tr("Tüm Widget'ları Kapat") == "Close All Widgets"
    assert i18n.tr("🧹 Tüm Widget'ları Kapat") == "🧹 Close All Widgets"  # emoji öneki korunur
    assert i18n.tr("Bilinmeyen anahtar metni") == "Bilinmeyen anahtar metni"  # bilinmeyen → kaynak metin
    i18n.set_language("tr")
    assert i18n.tr("Tüm Widget'ları Kapat") == "Tüm Widget'ları Kapat"
    assert i18n.set_language("xx") == "en"  # geçersiz kod → varsayılan


def test_translation_placeholders_match_source():
    for src, en in EN.items():
        assert [f[0] and "x" or "" for f in _fields(src)] == [f[0] and "x" or "" for f in _fields(en)] or src.count("{") == en.count("{"), src
        assert src.count("{}") == en.count("{}"), src  # konumsal alan sayısı aynı


def test_asset_label_uses_name_en_when_present():
    class A:
        name, name_en = "Şövalye", "Knight"

    class B:
        name, name_en = "Kedi", ""

    i18n.set_language("en")
    assert i18n.asset_label(A) == "Knight" and i18n.asset_label(B) == "Kedi"
    i18n.set_language("tr")
    assert i18n.asset_label(A) == "Şövalye"


def test_name_en_roundtrips_in_asset_model():
    from src.core.models import AnimationAsset

    d = {"id": "x", "name": "Kedi", "name_en": "Cat", "category": "Retro & Geek", "frames": ["a"]}
    a = AnimationAsset.from_dict(d)
    assert a.name_en == "Cat" and a.to_dict()["name_en"] == "Cat"
    assert "name_en" not in AnimationAsset.from_dict({"id": "y", "name": "K", "category": "c", "frames": ["a"]}).to_dict()


@pytest.fixture
def qapp():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance()


def _manager(tmp_path, qapp):
    from src.gui.tray_manager import WidgetHostManager

    cfg = ConfigManager(tmp_path / "cfg.json")
    return WidgetHostManager(qapp, BASE, AnimationLibrary(ANIM), ThemeLibrary(BASE / "assets" / "themes.json"), cfg, enable_ipc=False), cfg


def _texts(menu):
    out = []
    for a in menu.actions():
        out.append(a.text())
        if a.menu() is not None:
            out += _texts(a.menu())
    return out


def test_tray_menu_texts_en_and_tr(tmp_path, qapp):
    m, cfg = _manager(tmp_path, qapp)
    i18n.set_language("en")
    m._rebuild_tray_menu()
    en = _texts(m.tray.contextMenu())
    assert any("Open New Character (Quick Pick)..." in t for t in en)
    assert any("HD Mode (uses more CPU/RAM)" in t for t in en)
    assert any("No active widgets" in t for t in en)
    assert any("Language" in t for t in en) and "English" in en and "Türkçe" in en
    assert not [t for t in en if TURKISH_CHARS & set(t) and t != "Türkçe"], [t for t in en if TURKISH_CHARS & set(t)]
    # dil seçimi: config'e yazılır ve menü Türkçeye döner
    m.set_language("tr")
    assert cfg.get_global("language") == "tr" and i18n.get_language() == "tr"
    tr_texts = _texts(m.tray.contextMenu())
    assert any("Yeni Karakter Aç (Hızlı Seç)..." in t for t in tr_texts)
    assert any("HD Mod (daha fazla CPU/RAM kullanır)" in t for t in tr_texts)


def test_context_menu_texts_en_and_tr(tmp_path, qapp):
    from src.gui.companion_widget import CompanionWidget
    from src.gui.context_menu import build_context_menu

    lib = AnimationLibrary(ANIM)
    cfg = ConfigManager(tmp_path / "c.json")
    th = ThemeLibrary(BASE / "assets" / "themes.json")
    w = CompanionWidget("t", lib.get("saturn_3d"), lib, th, cfg)
    try:
        i18n.set_language("en")
        en = _texts(build_context_menu(w))
        assert any("Fine-Tuning Panel (Sliders)..." in t for t in en)
        assert any("Always on Top" in t for t in en)
        assert any("Close This Widget" in t for t in en)
        left = [t for t in en if TURKISH_CHARS & set(t)]
        assert not left, left
        i18n.set_language("tr")
        trt = _texts(build_context_menu(w))
        assert any("İnce Ayar Paneli (Slider'lar)..." in t for t in trt)
    finally:
        w.close_widget()


def test_language_setting_loaded_from_config(tmp_path):
    cfg = ConfigManager(tmp_path / "c.json")
    assert cfg.get_global("language", i18n.DEFAULT_LANGUAGE) == "en"
    cfg.set_global("language", "tr")
    assert ConfigManager(tmp_path / "c.json").get_global("language") == "tr"
    json.loads((tmp_path / "c.json").read_text(encoding="utf-8"))


def test_settings_dialog_texts_english(tmp_path, qapp):
    from PyQt6.QtWidgets import QCheckBox, QComboBox, QLabel, QPushButton, QWidget

    from src.gui.companion_widget import CompanionWidget
    from src.gui.settings_dialog import SettingsDialog

    lib = AnimationLibrary(ANIM)
    cfg = ConfigManager(tmp_path / "c.json")
    w = CompanionWidget("t", lib.get("hd_poppy_field"), lib, ThemeLibrary(BASE / "assets" / "themes.json"), cfg)
    try:
        i18n.set_language("en")
        dlg = SettingsDialog(w)
        out = [dlg.windowTitle()]
        for c in dlg.findChildren(QWidget):
            if isinstance(c, (QLabel, QCheckBox, QPushButton)):
                out.append(c.text())
            if isinstance(c, QComboBox):
                out += [c.itemText(i) for i in range(c.count())]
        assert not [t for t in out if TURKISH_CHARS & set(t)], [t for t in out if TURKISH_CHARS & set(t)]
        assert any("Opacity" in t for t in out) and any("Always on Top" in t for t in out)
    finally:
        w.close_widget()


def test_hub_banner_and_shortcuts_follow_language():
    from src.cli.terminal_hub import NAV_SHORTCUTS, build_banner_text

    i18n.set_language("en")
    txt, _ = build_banner_text(120)
    assert "Floating Desktop Buddy" in txt.plain
    assert [i18n.tr(d) for _, d in NAV_SHORTCUTS][:3] == ["Select", "Category", "Place on Desktop"]
    i18n.set_language("tr")
    assert "Yüzen Masaüstü Arkadaşın" in build_banner_text(120)[0].plain