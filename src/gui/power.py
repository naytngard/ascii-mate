"""Pil / oturum kilidi / tam ekran uygulama farkındalığı (Windows). Tek bir 2 sn'lik yoklama zamanlayıcısı kullanır.

Amaç: ekran kilitliyken ya da widget tam ekran bir uygulamanın arkasında kalıyorken çizimi durdurmak,
pildeyken FPS'i otomatik düşürmek. Windows dışı sistemlerde her şey "normal" döner.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from typing import Optional

from PyQt6.QtCore import QObject, QRect, QTimer, pyqtSignal

from src.core.app_logging import get_logger

log = get_logger("power")

POLL_MS = 2000
_DESKTOP_SWITCHDESKTOP = 0x0100
_SHELL_CLASSES = {"Progman", "WorkerW", "Shell_TrayWnd", "Shell_SecondaryTrayWnd"}


class _SYSTEM_POWER_STATUS(ctypes.Structure):
    _fields_ = [
        ("ACLineStatus", ctypes.c_ubyte),
        ("BatteryFlag", ctypes.c_ubyte),
        ("BatteryLifePercent", ctypes.c_ubyte),
        ("SystemStatusFlag", ctypes.c_ubyte),
        ("BatteryLifeTime", wintypes.DWORD),
        ("BatteryFullLifeTime", wintypes.DWORD),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


class PowerMonitor(QObject):
    """Tekil yoklayıcı. Durum değişince `changed` yayar; widget'lar kendi durumlarını yeniden hesaplar."""

    changed = pyqtSignal()
    _instance: Optional["PowerMonitor"] = None

    @classmethod
    def instance(cls) -> "PowerMonitor":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        super().__init__()
        self.locked: bool = False
        self.on_battery: bool = False
        self.fullscreen_rect: Optional[QRect] = None  # tam ekran önplan penceresinin (başka süreç) ekranı
        self.battery_saver_enabled: bool = True  # "pildeyken otomatik düşür" (genel ayar)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.poll)
        if os.name == "nt":
            self._timer.start(POLL_MS)
            self.poll()

    # --- sorgular ---

    def fps_factor(self) -> float:
        """Pilde (ve tasarruf açıkken) FPS çarpanı."""
        return 0.6 if (self.on_battery and self.battery_saver_enabled) else 1.0

    def is_suspended_for(self, rect: QRect, always_on_top: bool) -> bool:
        """Kilitliyse her zaman; tam ekran uygulama aynı ekranı kaplıyorsa ve widget en üstte DEĞİLSE (arkada kalır)."""
        if self.locked:
            return True
        if self.fullscreen_rect is not None and not always_on_top:
            return self.fullscreen_rect.intersects(rect)
        return False

    # --- yoklama ---

    def poll(self) -> None:
        if os.name != "nt":
            return
        try:
            locked = self._poll_locked()
            on_batt = self._poll_battery()
            fs = self._poll_fullscreen() if not locked else None
        except Exception:
            log.debug("güç/oturum yoklaması başarısız", exc_info=True)
            return
        if locked != self.locked or on_batt != self.on_battery or fs != self.fullscreen_rect:
            self.locked, self.on_battery, self.fullscreen_rect = locked, on_batt, fs
            self.changed.emit()

    @staticmethod
    def _poll_locked() -> bool:
        user32 = ctypes.windll.user32
        user32.OpenInputDesktop.restype = wintypes.HANDLE
        hdesk = user32.OpenInputDesktop(0, False, _DESKTOP_SWITCHDESKTOP)
        if not hdesk:
            return True  # kilit ekranı / güvenli masaüstü: erişilemiyor
        user32.CloseDesktop(hdesk)
        return False

    @staticmethod
    def _poll_battery() -> bool:
        st = _SYSTEM_POWER_STATUS()
        if not ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(st)):
            return False
        return st.ACLineStatus == 0

    @staticmethod
    def _poll_fullscreen() -> Optional[QRect]:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd or user32.IsIconic(hwnd):
            return None
        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == os.getpid():
            return None
        buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(hwnd, buf, 64)
        if buf.value in _SHELL_CLASSES:
            return None
        rect = wintypes.RECT()
        if not user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            return None
        hmon = user32.MonitorFromWindow(hwnd, 2)  # MONITOR_DEFAULTTONEAREST
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if not hmon or not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            return None
        m = mi.rcMonitor
        if rect.left <= m.left and rect.top <= m.top and rect.right >= m.right and rect.bottom >= m.bottom:
            return QRect(m.left, m.top, m.right - m.left, m.bottom - m.top)
        return None
