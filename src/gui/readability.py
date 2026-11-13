"""Akıllı okunabilirlik (V1): widget'ın altındaki ekran yazıya benziyorsa o hücrelerde widget'ı soluklaştırır.

Nasıl çalışır (OCR yok, dil bağımsız, ucuz):
  1. Widget'ın karakter ızgarasını kaplayan ekran dikdörtgeni düşük frekansta (~1,4 Hz) yakalanır.
     Widget'ın KENDİ penceresi `SetWindowDisplayAffinity(WDA_EXCLUDEFROMCAPTURE)` ile yakalamadan hariç tutulur.
  2. Yüksek frekans enerjisi (görüntü − bulanık kopya, Qt'nin Difference birleştirmesiyle) hücre ızgarasına indirilir.
     Enerjisi eşiğin üstündeki hücreler "yazı benzeri" sayılır; ortalama parlaklık zıt renk seçmek için kullanılır.
  3. Hücre başına üstel ortalama (EMA) + 4 kademe ile geçişler yumuşatılır; titreme olmaz.
Gizlilik: yakalanan görüntü yalnızca bellekte işlenir, diske yazılmaz, ağa gönderilmez; mod kapalıyken yakalama YAPILMAZ.
Ekran içeriği ve widget konumu değişmediyse (özet karşılaştırması) analiz atlanır ve yoklama seyrelir.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, List, Optional, Tuple

from PyQt6.QtCore import QObject, QRect, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QGuiApplication, QImage, QPainter

from src.core.app_logging import get_logger

if TYPE_CHECKING:  # pragma: no cover
    from src.gui.companion_widget import CompanionWidget

log = get_logger("readability")

WDA_NONE = 0x0
WDA_EXCLUDEFROMCAPTURE = 0x11
FAST_MS = 700
SLOW_MS = 1500

_active_count = 0
_capture_excluded = False


def is_supported() -> bool:
    """Windows 10 2004+ (WDA_EXCLUDEFROMCAPTURE) gerekir."""
    if os.name != "nt":
        return False
    try:
        import sys

        return sys.getwindowsversion().build >= 19041  # type: ignore[attr-defined]
    except Exception:
        return False


def set_display_affinity(widget: "CompanionWidget", exclude: bool) -> bool:
    if os.name != "nt":
        return False
    try:
        import ctypes

        hwnd = int(widget.winId())
        return bool(ctypes.windll.user32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE if exclude else WDA_NONE))
    except Exception:
        log.debug("SetWindowDisplayAffinity başarısız", exc_info=True)
        return False


def capture_excluded() -> bool:
    return _capture_excluded


def _set_global_exclusion(exclude: bool) -> None:
    """Herhangi bir widget'ta mod açıkken TÜM ASCII Mate widget'ları yakalamadan hariç tutulur (diğerleri 'yazı' sanılmasın).
    Mod tamamen kapanınca normal ekran kayıtlarında/görüntülerinde yeniden görünürler."""
    global _capture_excluded
    if exclude == _capture_excluded:
        return
    _capture_excluded = exclude
    from src.gui.companion_widget import CompanionWidget

    from PyQt6.QtWidgets import QApplication

    for w in QApplication.topLevelWidgets():
        if isinstance(w, CompanionWidget):
            set_display_affinity(w, exclude)


class ReadabilityAnalyzer(QObject):
    """Tek widget için yakalama + analiz döngüsü. `levels[row][col]` 0..3 (3 = tam soluk), `light[row][col]` arka plan açık mı."""

    mask_changed = pyqtSignal()

    def __init__(self, widget: "CompanionWidget") -> None:
        super().__init__(widget)
        self.w = widget
        self.levels: List[List[int]] = []
        self.light: List[List[bool]] = []
        self._amt: List[List[float]] = []
        self._sig: Optional[int] = None
        self._last_rect: Optional[Tuple[int, int, int, int, int, int]] = None
        self._same_count = 0
        self._running = False
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # --- yaşam döngüsü
    def start(self) -> bool:
        global _active_count
        if self._running:
            return True
        if not is_supported():
            log.warning("akıllı okunabilirlik bu Windows sürümünde desteklenmiyor (WDA_EXCLUDEFROMCAPTURE yok)")
            return False
        self._running = True
        _active_count += 1
        _set_global_exclusion(True)
        set_display_affinity(self.w, True)
        self._timer.start(FAST_MS)
        return True

    def stop(self) -> None:
        global _active_count
        if not self._running:
            return
        self._running = False
        self._timer.stop()
        _active_count = max(0, _active_count - 1)
        if _active_count == 0:
            _set_global_exclusion(False)
        self.levels, self.light, self._amt, self._sig = [], [], [], None
        self.mask_changed.emit()

    def pause(self, paused: bool) -> None:
        if not self._running:
            return
        if paused:
            self._timer.stop()
        elif not self._timer.isActive():
            self._timer.start(FAST_MS)

    @property
    def running(self) -> bool:
        return self._running

    # --- analiz
    def _tick(self) -> None:
        w = self.w
        try:
            if w._dragging or w._resize_mode is not None or w._orbiting or w._suspended or not w.isVisible():
                return
            region = w.readability_region()
            if region is None:
                return
            rect, cols, rows = region
            screen = QGuiApplication.screenAt(rect.center()) or QGuiApplication.primaryScreen()
            if screen is None or cols < 1 or rows < 1:
                return
            sg = screen.geometry()
            pix = screen.grabWindow(0, rect.x() - sg.x(), rect.y() - sg.y(), rect.width(), rect.height())
            if pix.isNull():
                return
            img = pix.toImage()
            result = self._analyze(img, cols, rows, w.state.behind_text_sensitivity)
            if result is None:
                return
            edge, lum, stride = result
            sig = hash((edge, lum, rect.x(), rect.y(), cols, rows))
            rect_key = (rect.x(), rect.y(), rect.width(), rect.height(), cols, rows)
            if sig == self._sig and rect_key == self._last_rect:
                self._same_count += 1
                if self._same_count >= 4 and self._timer.interval() != SLOW_MS:
                    self._timer.setInterval(SLOW_MS)
                return  # içerik değişmedi: hiçbir şey yapma
            self._sig, self._last_rect, self._same_count = sig, rect_key, 0
            if self._timer.interval() != FAST_MS:
                self._timer.setInterval(FAST_MS)
            self._update_mask(edge, lum, stride, cols, rows, w.state.behind_text_sensitivity)
        except Exception:
            log.exception("okunabilirlik analizi başarısız")

    @staticmethod
    def _analyze(img: QImage, cols: int, rows: int, sensitivity: float) -> Optional[Tuple[bytes, bytes, int]]:
        w, h = img.width(), img.height()
        if w < cols or h < rows or w < 8 or h < 8:
            return None
        # Maliyet düşürmek için yarı çözünürlükte çalış (yazı ayrıntısı hâlâ yeterli)
        ign = Qt.AspectRatioMode.IgnoreAspectRatio
        smooth = Qt.TransformationMode.SmoothTransformation
        half = img.convertToFormat(QImage.Format.Format_RGB32).scaled(
            max(cols, w // 2), max(rows, h // 2), ign, Qt.TransformationMode.FastTransformation
        )
        hw, hh = half.width(), half.height()
        small = half.scaled(max(1, hw // 4), max(1, hh // 4), ign, smooth)
        blur = small.scaled(hw, hh, ign, smooth)
        diff = half.copy()
        p = QPainter(diff)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Difference)
        p.drawImage(0, 0, blur)
        p.end()
        edge_img = diff.convertToFormat(QImage.Format.Format_Grayscale8).scaled(cols, rows, ign, smooth)
        lum_img = small.convertToFormat(QImage.Format.Format_Grayscale8).scaled(cols, rows, ign, smooth)
        stride = edge_img.bytesPerLine()
        eb = edge_img.constBits()
        eb.setsize(edge_img.sizeInBytes())
        lb = lum_img.constBits()
        lb.setsize(lum_img.sizeInBytes())
        return bytes(eb), bytes(lb), stride

    def _update_mask(self, edge: bytes, lum: bytes, stride: int, cols: int, rows: int, sensitivity: float) -> None:
        thr = 26.0 - 20.0 * max(0.0, min(1.0, sensitivity))  # 0 → 26 (katı), 1 → 6 (hassas)
        if len(self._amt) != rows or (rows and len(self._amt[0]) != cols):
            self._amt = [[0.0] * cols for _ in range(rows)]
        # 1) ham metin benzeri hücreler
        raw = [[edge[r * stride + c] > thr for c in range(cols)] for r in range(rows)]
        # 2) boşluk doldurma: iki metin hücresi arasında kalan hücre de metin sayılır (satır arası şeritlenmeyi önler)
        def eff(r: int, c: int) -> bool:
            if raw[r][c]:
                return True
            if 0 < r < rows - 1 and raw[r - 1][c] and raw[r + 1][c]:
                return True
            return 0 < c < cols - 1 and raw[r][c - 1] and raw[r][c + 1]

        levels: List[List[int]] = []
        light: List[List[bool]] = []
        changed = False
        for r in range(rows):
            base = r * stride
            arow = self._amt[r]
            lrow: List[int] = []
            brow: List[bool] = []
            for c in range(cols):
                a = arow[c] * 0.55 + (0.45 if eff(r, c) else 0.0)  # EMA: ~1 sn'de oturur, titreme yok
                arow[c] = a
                lv = 0 if a < 0.22 else (1 if a < 0.45 else (2 if a < 0.70 else 3))
                lrow.append(lv)
                brow.append(lum[base + c] > 128)
            levels.append(lrow)
            light.append(brow)
        if levels != self.levels or light != self.light:
            changed = True
        self.levels, self.light = levels, light
        if changed:
            self.mask_changed.emit()
