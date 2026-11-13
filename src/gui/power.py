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
        self.fullscreen_rect: Optional[QRect] = None  # önplandaki başka süreç penceresinin dikdörtgeni (mantıksal px)
        self._is_fullscreen = False
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
        """Kilitliyse her zaman. Widget "Her Zaman Üstte" DEĞİLSE ve önplandaki başka bir pencere (tam ekran ya da
        değil) widget'ı TAMAMEN örtüyorsa da durur — görünmeyen widget hiç tick atmaz."""
        if self.locked:
            return True
        if self.fullscreen_rect is not None and not always_on_top:
            return self.fullscreen_rect.contains(rect) or self.fullscreen_rect.intersects(rect) and self._is_fullscreen
        return False

    # --- yoklama ---

    def poll(self) -> None:
        if os.name != "nt":
            return
        try:
            locked = self._poll_locked()
            on_batt = self._poll_battery()
            fg = self._poll_foreground() if not locked else None
        except Exception:
            log.debug("güç/oturum yoklaması başarısız", exc_info=True)
            return
        fs, is_full = (fg if fg is not None else (None, False))
        if locked != self.locked or on_batt != self.on_battery or fs != self.fullscreen_rect or is_full != self._is_fullscreen:
            self.locked, self.on_battery, self.fullscreen_rect, self._is_fullscreen = locked, on_batt, fs, is_full
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
    def _poll_foreground() -> Optional[tuple]:
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
        # Win32 fiziksel piksel → Qt mantıksal piksel (birincil ekranın ölçeğiyle yaklaşık)
        from PyQt6.QtGui import QGuiApplication

        scr = QGuiApplication.primaryScreen()
        k = scr.devicePixelRatio() if scr is not None else 1.0
        if rect.left <= m.left and rect.top <= m.top and rect.right >= m.right and rect.bottom >= m.bottom:
            return QRect(int(m.left / k), int(m.top / k), int((m.right - m.left) / k), int((m.bottom - m.top) / k)), True
        return QRect(int(rect.left / k), int(rect.top / k), int((rect.right - rect.left) / k), int((rect.bottom - rect.top) / k)), False
