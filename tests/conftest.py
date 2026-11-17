import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
if str(BASE) not in sys.path:
    sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "tests"))

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _ui_language_tr():
    """Mevcut testler Türkçe arayüz metnine bağlı; dil açıkça sabitlenir (varsayılan uygulama dili İngilizce).
    İngilizce testleri tests/test_i18n.py kendisi ayarlar."""
    from src.core import i18n

    i18n.set_language("tr")
    yield
    i18n.set_language("en")


@pytest.fixture(scope="session", autouse=True)
def _qapp_session():
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app

