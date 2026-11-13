"""Floating transparent, frameless, draggable, scalable PyQt6 ASCII widget with offscreen QPixmap cache and HD multi-color 3D support."""

from __future__ import annotations

import math
import re
import time
from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QPoint, QPointF, QRect, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QFontMetricsF,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from src.core.app_logging import get_logger
from src.core.config_manager import ConfigManager
from src.core.converter import import_file_to_community
from src.core.library import AnimationLibrary, ThemeLibrary
from src.core.models import AnimationAsset, WidgetState
from src.core.particle_engine import ParticleEngine
from src.core.procedural_engine import (
    BaseProceduralRenderer,
    Fireworks3DRenderer,
    create_procedural_renderer,
)
from src.gui.context_menu import build_context_menu
from src.gui.hd_renderer import HD_ABS_FPS_CAP, HD_QUALITY, HDPlayer
from src.gui.power import PowerMonitor
from src.gui.readability import ReadabilityAnalyzer, capture_excluded, is_supported, set_display_affinity

RGB = Tuple[int, int, int]

SHADER_DEFAULT_FPS_CAP = 15.0  # 3B shader varsayılan FPS tavanı (kullanıcı özel FPS ile değiştirebilir)

log = get_logger("widget")

_NA = r"(?<![A-Za-z0-9])"
_NB = r"(?![A-Za-z0-9])"
# Varsayılan göz kırpma kalıpları: yalnızca göz benzeri bağlamlarda eşleşir (düz yazıdaki "o o" gibi yerlere dokunmaz).
_DEFAULT_BLINK_RULES: List[Tuple["re.Pattern[str]", str]] = [
    (re.compile(_NA + r"[oO^•◉]([._])[oO^•◉]" + _NB), lambda m: "-" + m.group(1) + "-")  # type: ignore[arg-type]
] + [
    (re.compile(r"([(\[{|<]\s?)" + pat + r"(\s?[)\]}|>])"), rep)
    for pat, rep in (
        (r"[oO0^] [oO0^]", r"\1- -\2"),
        (r"[oO0^],[oO0^]", r"\1-,-\2"),
    )
] + [
    (re.compile(r"\(o \)"), "(- )"),
    (re.compile(r"\( o\)"), "( -)"),
    (re.compile(r"[oO^]ω[oO^]"), "-ω-"),
]

MIN_FONT_SIZE = 6
MAX_FONT_SIZE = 48
EDGE_GRAB_MARGIN = 10
CORNER_GRAB_MARGIN = 16

GRID_PRESETS: Dict[str, Tuple[int, int]] = {
    "compact": (38, 18),
    "standard": (52, 24),
    "hd": (64, 30),
    "ultra": (74, 34),
}

MIRROR_CHAR_MAP = str.maketrans({
    "/": "\\",
    "\\": "/",
    "(": ")",
    ")": "(",
    "[": "]",
    "]": "[",
    "{": "}",
    "}": "{",
    "<": ">",
    ">": "<",
    "´": "`",
    "`": "´",
})


def _quantize(rgb: RGB, enabled: bool) -> RGB:
    """Her kanalı 32'lik basamaklara indirir (3B karelerde komşu hücreler aynı rengi paylaşsın)."""
    if not enabled:
        return rgb
    return (rgb[0] & 0xE0 | 16, rgb[1] & 0xE0 | 16, rgb[2] & 0xE0 | 16)


class CompanionWidget(QWidget):
    """Transparent floating ASCII study companion widget."""

    closed = pyqtSignal(str)  # emits instance_id

    def __init__(
        self,
        instance_id: str,
        asset: AnimationAsset,
        library: AnimationLibrary,
        theme_lib: ThemeLibrary,
        config_mgr: ConfigManager,
        manager_callbacks: Optional[Dict[str, Callable]] = None,
        slot: int = 0,
    ) -> None:
        super().__init__()
        self.instance_id = instance_id
        self.slot = slot  # aynı animasyonun n. kopyası: ayar/konum (asset_id, slot) ile saklanır
        self.asset = asset
        self.library = library
        self.theme_lib = theme_lib
        self.config_mgr = config_mgr
        self.manager_callbacks = manager_callbacks or {}

        self.state: WidgetState = self.config_mgr.get_widget_state(asset.id, slot)
        self.particle_engine = ParticleEngine()

        # Optional live 3D / shader procedural engine
        self._procedural: Optional[BaseProceduralRenderer] = (
            create_procedural_renderer(asset.procedural, asset.procedural_params)
            if asset.procedural
            else None
        )
        self._sync_procedural_grid()

        # Runtime animation state
        self._frame_idx: int = 0
        self._frame_accum: float = 0.0
        self._paused: bool = False
        self._hovered: bool = False
        self._dragging: bool = False
        self._drag_offset: QPoint = QPoint()
        self._orbiting: bool = False
        self._orbit_start_global: QPoint = QPoint()
        self._orbit_start_yaw: float = 0.0
        self._orbit_start_pitch: float = 0.0
        self._resize_mode: Optional[str] = None
        self._resize_hover_mode: Optional[str] = None
        self._resize_start_global: QPoint = QPoint()
        self._resize_start_geom = self.geometry()
        self._resize_start_font: int = self.state.font_size
        self._rainbow_hue: float = 0.0
        self._lightning_flash: bool = False
        self._last_tick_time: float = time.monotonic()
        self._last_timer_sec: int = -1
        self._cursor_look: Tuple[float, float] = (0.0, 0.0)
        self._close_notified: bool = False
        self._suspended: bool = False
        self._readability: Optional[ReadabilityAnalyzer] = None
        self._paused_by_user_hidden: bool = False

        # Eye blink state
        self._blink_timer: float = 0.0
        self._is_blinking: bool = False

        # Study timer / Pomodoro fireworks & break countdown state
        self._remaining_seconds: float = float(self.state.duration_minutes * 60) if self.state.duration_minutes > 0 else 0.0
        # Süre ayarı (duration_minutes) kayıtlı kalır ama sayaç açılışta KENDİLİĞİNDEN başlamaz; menüden/profilden başlatılır.
        self._timer_active: bool = False
        self._celebration_mode: bool = False
        self._celebration_elapsed: float = 0.0
        self._celebration_renderer: Optional[Fireworks3DRenderer] = None
        self._break_countdown_mode: bool = False
        self._break_mode: bool = False
        self._break_elapsed: float = 0.0
        self._fade_factor: float = 1.0

        # Offscreen QPixmap art cache
        self._art_pixmap: Optional[QPixmap] = None
        self._art_dirty: bool = True
        self._cached_font: Optional[QFont] = None
        self._cached_font_metrics: Optional[Tuple[int, float, float, float]] = None  # (size, char_w, line_h, ascent)

        # Initial frame
        self._current_lines: List[str] = []
        self._current_colors: Optional[List[List[Optional[RGB]]]] = None
        # HD (3.0) varlık: ayrı, NumPy glyph atlaslı hızlı yol
        self._hd: Optional[HDPlayer] = None
        self._hd_frame: int = 0
        self._hd_accum: float = 0.0
        if asset.is_hd:
            try:
                self._hd = HDPlayer(asset)
            except Exception:
                log.exception("HD varlık açılamadı: %s", asset.id)
        self._init_first_frame()

        # Window setup
        self.setWindowTitle(f"ASCII Mate — {self.asset.name}")
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self._apply_window_flags(initial=True)

        # Position restoration or smart corner placement
        self._recalculate_size()
        self._restore_or_place_position()

        # Adaptive render timer (33ms / ~30 FPS for 3D shaders, 62ms / ~16 FPS otherwise)
        self._tick_timer = QTimer(self)
        self._tick_timer.timeout.connect(self._on_tick)
        self._update_timer_interval()
        PowerMonitor.instance().changed.connect(self._evaluate_suspension)

    def _compute_target_3d_grid(self) -> Tuple[int, int]:
        res = self.state.grid_resolution
        if res in GRID_PRESETS:
            return GRID_PRESETS[res]
        # Auto mode: scales monotonically with font_size from base asset dimensions
        base_w, base_h = self.asset.dimensions
        if base_w <= 0 or base_h <= 0:
            base_w, base_h = 50, 22
        scale = max(0.76, min(1.65, self.state.font_size / 14.0))
        return max(32, min(88, int(round(base_w * scale)))), max(16, min(40, int(round(base_h * scale))))

    def _sync_procedural_grid(self) -> None:
        if self._procedural is not None:
            gw, gh = self._compute_target_3d_grid()
            self._procedural.set_grid_size(gw, gh)

    def _compute_cursor_look(self) -> Tuple[float, float]:
        if not self.state.track_cursor:
            return (0.0, 0.0)
        cur = QCursor.pos()
        center = self.mapToGlobal(self.rect().center())
        nx = max(-1.0, min(1.0, (cur.x() - center.x()) / 320.0))
        ny = max(-1.0, min(1.0, (cur.y() - center.y()) / 220.0))
        return (nx, ny)

    # --- HD yol yardımcıları ---

    def _hd_cell_px(self) -> Tuple[int, int]:
        """Yazı boyutundan HD hücre pikseli (1:2 en-boy)."""
        cw = max(2, int(round(self.state.font_size * 0.36)))
        return cw, cw * 2

    def _hd_fps(self) -> float:
        cap = self.state.hd_fps_cap or HD_QUALITY[self.state.hd_quality][1]
        fps = self.state.custom_fps or self.asset.default_fps
        return max(1.0, min(fps, cap, HD_ABS_FPS_CAP))

    def _hd_configure(self) -> None:
        hd = self._hd
        if hd is None:
            return
        cw, ch = self._hd_cell_px()
        hd.configure(cw, ch, HD_QUALITY[self.state.hd_quality][0], self.state.opacity * self._fade_factor)
        self._current_lines = [" " * hd.dcols] * hd.drows
        self._hd_sync_mask()
        if hd._full_dirty:
            try:
                hd.render(self._hd_frame)
            except Exception:
                log.exception("HD kare çizilemedi")
            self.update()

    def _hd_sync_mask(self) -> None:
        hd = self._hd
        if hd is None:
            return
        rd = self._readability
        if self.state.behind_text_enabled and rd is not None and rd.running and rd.levels:
            import numpy as np

            lv = np.asarray(rd.levels, dtype=np.int8)
            lt = np.asarray(rd.light, dtype=bool)
            hd.set_mask(lv, lt, max(0.08, min(0.6, self.state.behind_text_fade)))
        else:
            hd.set_mask(None, None, self.state.behind_text_fade)

    def _on_tick_hd(self) -> None:
        hd = self._hd
        assert hd is not None
        now = time.monotonic()
        dt = min(0.5, max(0.01, now - self._last_tick_time))
        self._last_tick_time = now
        n = self.asset.frame_count
        if n > 1 and not self._paused:
            self._hd_accum += dt * self._hd_fps() * self.state.speed_multiplier
            if self._hd_accum >= 1.0:
                steps = int(self._hd_accum)
                self._hd_accum -= steps
                self._hd_frame = (self._hd_frame + steps) % n
        if hd._last_idx != self._hd_frame or hd._full_dirty:
            try:
                if hd.render(self._hd_frame):
                    self.update()
            except Exception:
                log.exception("HD kare çizilemedi")

    def _init_first_frame(self) -> None:
        if self._hd is not None:
            self._hd_configure()
            return
        if self._procedural is not None:
            self._sync_procedural_grid()
            pf = self._procedural.step(
                0.0,
                1.0,
                yaw_offset=self.state.orbit_yaw,
                pitch_offset=self.state.orbit_pitch,
                cursor_look=self._cursor_look,
                progress=self._pomodoro_progress(),
            )
            self._current_lines = pf.lines
            self._current_colors = pf.colors
        else:
            self._current_lines, self._current_colors = self._get_static_frame(0)

    def _pomodoro_progress(self) -> Optional[float]:
        if not self._timer_active or self.state.duration_minutes <= 0 or self._break_countdown_mode:
            return None
        total = max(1.0, float(self.state.duration_minutes * 60))
        return max(0.0, min(1.0, self._remaining_seconds / total))

    def _needs_fast_static_tick(self) -> bool:
        """Statik animasyonda parçacık/gökkuşağı/göz kırpma/imleç takibi varsa ~8 FPS gerekir; yoksa kare hızı yeter."""
        return bool(
            self.is_particles_active()
            or self.state.sleep_zzz_enabled
            or self.state.eye_blink_enabled
            or self.state.track_cursor
            or bool(self._current_theme_info().get("is_rainbow"))
        )

    def _target_tick_ms(self) -> int:
        """Gerçek ihtiyaca göre tick aralığı. 3B shader: varsayılan ≤18 FPS (ayarlanabilir); statik: 1-8 FPS."""
        if self._suspended:
            return 1000  # yalnızca durum değişimini yakalamak için seyrek uyan
        factor = PowerMonitor.instance().fps_factor()
        user_fps = self.state.custom_fps
        if self._hd is not None:
            if self.asset.frame_count <= 1:
                return 500  # durağan HD: yalnızca ayar/maske değişimini yakalamak için seyrek uyan
            return int(max(66, min(1000, round(1000.0 / max(1.0, self._hd_fps() * factor)))))
        if self._procedural is not None:
            fps = user_fps if user_fps else min(self.asset.default_fps, SHADER_DEFAULT_FPS_CAP)
            fps = max(6.0, min(30.0, fps)) * factor
            return max(33, int(round(1000.0 / max(4.0, fps))))
        base = (user_fps if user_fps else self.asset.default_fps) * self.state.speed_multiplier
        eff = max(0.5, base)
        if self._needs_fast_static_tick():
            eff = max(eff, 8.0)
        elif self._timer_active:
            eff = max(eff, 2.0)  # sayaç saniyede bir güncellenir
        eff = max(1.0, min(30.0, eff * factor))
        # Ekran kilidi/kapanış/olay tepkisi için en fazla 250 ms uyku
        return int(max(33, min(250, round(1000.0 / eff))))

    def _update_timer_interval(self) -> None:
        interval = self._target_tick_ms()
        if not self._tick_timer.isActive() or self._tick_timer.interval() != interval:
            self._tick_timer.start(interval)

    def _evaluate_suspension(self) -> None:
        """Kilit ekranı / tam ekran uygulamanın arkasında kalma durumunda çizimi durdurur, dönünce devam ettirir."""
        mon = PowerMonitor.instance()
        suspended = (
            mon.is_suspended_for(self.frameGeometry(), self.state.always_on_top)
            or self._paused_by_user_hidden
        )
        if suspended != self._suspended:
            self._suspended = suspended
            if not suspended:
                self._last_tick_time = time.monotonic()  # uzun uykudan sonra zıplama olmasın
                self._invalidate_art()
        if self._readability is not None:
            self._readability.pause(self._suspended)
        self._tick_timer.stop()
        self._update_timer_interval()

    def _read_levels(self) -> Optional[List[List[int]]]:
        if self._readability is not None and self._readability.running:
            return self._readability.levels or None
        return None

    def readability_region(self) -> Optional[Tuple[QRect, int, int]]:
        """Akıllı okunabilirlik için yakalanacak ekran dikdörtgeni (global piksel) ve karakter ızgarası boyutu."""
        if self._hd is not None:
            hd = self._hd
            origin = self.mapToGlobal(QPoint(12, 10))
            return QRect(origin.x(), origin.y(), hd.dcols * hd.cw, hd.drows * hd.ch), hd.dcols, hd.drows
        lines = self._current_lines
        if not lines:
            return None
        cols = max((len(l) for l in lines), default=0)
        rows = len(lines)
        if cols < 1 or rows < 1:
            return None
        char_w, line_h, _ = self._get_font_metrics()
        origin = self.mapToGlobal(QPoint(12, 10))
        return QRect(origin.x(), origin.y(), max(1, int(cols * char_w)), max(1, int(rows * line_h))), cols, rows

    def _sync_readability(self) -> None:
        """Mod açıksa analiz döngüsünü başlatır, kapalıysa durdurur (yakalama yalnızca mod açıkken çalışır)."""
        if self.state.behind_text_enabled:
            if self._readability is None:
                self._readability = ReadabilityAnalyzer(self)
                self._readability.mask_changed.connect(self._on_readability_changed)
            if not self._readability.start():
                self.state.behind_text_enabled = False
                self._readability = None
        elif self._readability is not None:
            self._readability.stop()
            self._readability = None
            self._invalidate_art()
            self.update()

    def _on_readability_changed(self) -> None:
        self._invalidate_art()
        self.update()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        if capture_excluded():
            set_display_affinity(self, True)
        if self.state.behind_text_enabled and self._readability is None:
            QTimer.singleShot(0, self._sync_readability)

    def set_behind_text(self, enabled: bool) -> None:
        if enabled and not is_supported():
            QMessageBox.information(self, "Desteklenmiyor", "Akıllı okunabilirlik Windows 10 (2004) veya üstünü gerektirir.")
            enabled = False
        self.state.behind_text_enabled = bool(enabled)
        self._sync_readability()
        self._save_state()

    def set_hd_quality(self, quality: str) -> None:
        if quality not in HD_QUALITY:
            quality = "medium"
        self.state.hd_quality = quality
        self._recalculate_size()
        self._update_timer_interval()
        self._save_state()
        self.update()

    def set_hd_fps_cap(self, fps: Optional[float]) -> None:
        self.state.hd_fps_cap = None if not fps else max(1.0, min(HD_ABS_FPS_CAP, float(fps)))
        self._update_timer_interval()
        self._save_state()

    def set_behind_text_sensitivity(self, value: float) -> None:
        self.state.behind_text_sensitivity = max(0.0, min(1.0, float(value)))
        if self._readability is not None:
            self._readability._sig = None  # yeniden analiz
        self._save_state()

    def set_behind_text_fade(self, value: float) -> None:
        self.state.behind_text_fade = max(0.08, min(0.6, float(value)))
        self._invalidate_art()
        self._save_state()
        self.update()

    def _invalidate_art(self) -> None:
        self._art_dirty = True
        if self._hd is not None:
            self._hd.invalidate()
            self._hd_configure()

    def _apply_window_flags(self, initial: bool = False) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.state.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        if self.state.click_through:
            flags |= Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)
        if not initial:
            self.show()

    def _screen_geometry_for(self, x: int, y: int):
        """(x, y) noktasını (widget merkezi) içeren ekranın kullanılabilir alanı; yoksa en yakın ekran, o da yoksa birincil."""
        center = QPoint(x + self.width() // 2, y + self.height() // 2)
        screen = QGuiApplication.screenAt(center)
        if screen is None:
            best, best_d = None, None
            for sc in QGuiApplication.screens():
                g = sc.geometry()
                dx = max(g.left() - center.x(), 0, center.x() - g.right())
                dy = max(g.top() - center.y(), 0, center.y() - g.bottom())
                d = dx * dx + dy * dy
                if best_d is None or d < best_d:
                    best, best_d = sc, d
            screen = best
        if screen is None:
            screen = QGuiApplication.primaryScreen()
        return screen.availableGeometry() if screen else QRectF(0, 0, 1280, 720).toRect()

    def _restore_or_place_position(self) -> None:
        if self.state.x is not None and self.state.y is not None:
            avail = self._screen_geometry_for(self.state.x, self.state.y)
            nx = max(avail.left(), min(avail.right() - self.width(), self.state.x))
            ny = max(avail.top(), min(avail.bottom() - self.height(), self.state.y))
            self.move(nx, ny)
        else:
            screen = QGuiApplication.primaryScreen()
            avail = screen.availableGeometry() if screen else QRectF(0, 0, 1280, 720).toRect()
            offset = (self.slot % 5) * 36 + (abs(hash(self.asset.id)) % 3) * 36
            nx = avail.right() - self.width() - 40 - offset
            ny = avail.bottom() - self.height() - 40 - offset
            self.move(max(avail.left(), nx), max(avail.top(), ny))

    def _build_font(self) -> QFont:
        if self._cached_font is None or self._cached_font.pointSize() != self.state.font_size:
            font = QFont()
            font.setFamilies(["Cascadia Mono", "Consolas", "Courier New", "Monospace"])
            font.setStyleHint(QFont.StyleHint.Monospace)
            font.setPointSize(self.state.font_size)
            font.setFixedPitch(True)
            self._cached_font = font
            self._cached_font_metrics = None
        return self._cached_font

    def _get_font_metrics(self) -> Tuple[float, float, float]:
        font = self._build_font()
        ls = self.state.line_spacing
        if self._cached_font_metrics is None or self._cached_font_metrics[0] != self.state.font_size or abs(self._cached_font_metrics[4] - ls) > 1e-4:  # type: ignore[index]
            fm = QFontMetricsF(font)
            char_w = max(6.0, fm.horizontalAdvance("M"))
            line_h = max(8.0, fm.height() * ls)
            ascent = fm.ascent()
            self._cached_font_metrics = (self.state.font_size, char_w, line_h, ascent, ls)  # type: ignore[assignment]
        _, char_w, line_h, ascent, _ = self._cached_font_metrics  # type: ignore[misc]
        return char_w, line_h, ascent

    def _get_static_frame(self, idx: int) -> Tuple[List[str], Optional[List[List[Optional[RGB]]]]]:
        if not self.asset.frames:
            return ["(Boş)"], None
        raw = self.asset.frames[idx % len(self.asset.frames)]
        lines = raw.split("\n")
        colors = self.asset.get_frame_colors(idx)
        if self.state.flip_horizontal:
            max_w = max((len(l) for l in lines), default=0)
            lines = [l.ljust(max_w)[::-1].translate(MIRROR_CHAR_MAP) for l in lines]
            if colors is not None:
                colors = [
                    (row + [None] * max(0, max_w - len(row)))[:max_w][::-1]
                    for row in colors
                ]
        return lines, colors

    def _apply_eye_blink(self, lines: List[str]) -> List[str]:
        if not self._is_blinking:
            return lines
        custom = self.asset.blink_patterns
        out: List[str] = []
        for l in lines:
            if custom:
                for src, dst in custom:
                    if src in l:
                        l = l.replace(src, dst)
            else:
                for rx, rep in _DEFAULT_BLINK_RULES:
                    l = rx.sub(rep, l)
            out.append(l)
        return out

    def is_particles_active(self) -> bool:
        if self.state.particle_override_type is not None:
            return self.state.particle_override_type != "none"
        if self.state.particles_enabled is not None:
            return self.state.particles_enabled
        return self.asset.particles.enabled_by_default

    def _is_multicolor_active(self) -> bool:
        if self._celebration_mode and self._current_colors is not None:
            return True
        if self._current_colors is None or self._lightning_flash or self._break_mode:
            return False
        return self.state.color_theme in ("auto", "auto_hd")

    def _recalculate_size(self) -> None:
        if self._hd is not None:
            self._hd_configure()
            pw, ph = self._hd.pixel_size
            new_w, new_h = pw + 24, ph + 22
            if new_w != self.width() or new_h != self.height():
                self.resize(new_w, new_h)
            return
        char_w, line_h, _ = self._get_font_metrics()
        fm = QFontMetricsF(self._build_font())
        lines = self._current_lines or ["(Boş)"]
        cols = max((len(l) for l in lines), default=10)
        max_px = max(cols * char_w, max((fm.horizontalAdvance(l) for l in lines), default=0.0))
        rows = len(lines)

        pad_x = 24
        pad_y = 22
        extra_timer_h = int(math.ceil(line_h * 1.1)) if (self._timer_active and self.state.show_timer_below) else 0

        w = int(math.ceil(max_px)) + pad_x
        h = int(math.ceil(rows * line_h)) + pad_y + extra_timer_h
        new_w, new_h = max(90, w), max(60, h)
        if new_w != self.width() or new_h != self.height():
            self.resize(new_w, new_h)
            self._invalidate_art()

    def _apply_cursor_track_static(self, lines: List[str]) -> List[str]:
        if not self.state.track_cursor:
            return lines
        nx = self._cursor_look[0]
        if nx < -0.25:
            pairs = (("( o.o )", "(o.o  )"), ("( O.O )", "(O.O  )"), ("( o_o )", "(o_o  )"), ("( -.- )", "(-.-  )"), ("( ^.^ )", "(^.^  )"))
        elif nx > 0.25:
            pairs = (("( o.o )", "(  o.o)"), ("( O.O )", "(  O.O)"), ("( o_o )", "(  o_o)"), ("( -.- )", "(  -.-)"), ("( ^.^ )", "(  ^.^)"))
        else:
            return lines
        out = []
        for l in lines:
            nl = l
            for src, dst in pairs:
                if src in nl:
                    nl = nl.replace(src, dst[: len(src)])
            out.append(nl)
        return out

    def _on_tick(self) -> None:
        if self._suspended:
            return
        if self._hd is not None:
            self._on_tick_hd()
            return
        now = time.monotonic()
        dt = min(0.5, max(0.01, now - self._last_tick_time))
        self._last_tick_time = now

        old_look = self._cursor_look
        self._cursor_look = self._compute_cursor_look()
        look_changed = self.state.track_cursor and (
            abs(self._cursor_look[0] - old_look[0]) > 0.08 or abs(self._cursor_look[1] - old_look[1]) > 0.08
        )

        theme_info = self._current_theme_info()
        is_rainbow = bool(theme_info.get("is_rainbow")) and not self._is_multicolor_active()
        if is_rainbow:
            self._rainbow_hue = (self._rainbow_hue + dt * 0.14) % 1.0

        timer_changed = False
        if self._timer_active and not self._break_mode and not self._celebration_mode:
            self._remaining_seconds -= dt
            cur_sec = max(0, int(self._remaining_seconds))
            if cur_sec != self._last_timer_sec:
                self._last_timer_sec = cur_sec
                timer_changed = True
            if self._remaining_seconds <= 0:
                self._remaining_seconds = 0.0
                if not self._break_countdown_mode:
                    # Work session finished -> trigger 5-sec Fireworks Celebration shader!
                    self._celebration_mode = True
                    self._celebration_elapsed = 0.0
                    cur_w = max(40, max((len(l) for l in self._current_lines), default=48))
                    cur_h = max(16, len(self._current_lines) or 20)
                    self._celebration_renderer = Fireworks3DRenderer(width=cur_w, height=cur_h)
                    self._invalidate_art()
                else:
                    # 5-min Break finished -> graceful fade-out close
                    self._break_mode = True
                    self._break_elapsed = 0.0
                    self._invalidate_art()

        if self._celebration_mode:
            self._celebration_elapsed += dt
            if self._celebration_renderer is None:
                self._celebration_renderer = Fireworks3DRenderer(width=48, height=20)
            pf = self._celebration_renderer.step(dt, 1.15)
            lines = list(pf.lines)
            colors = [list(r) for r in pf.colors]
            msg = "  * MOLA ZAMANI! 5 dk dinlenme basliyor *  " if self.state.pomodoro_break_enabled else "  * TEBRIKLER! Oturum Tamamlandi! *  "
            cw = len(lines[0]) if lines else len(msg)
            banner = msg[:cw].center(cw)
            if len(lines) >= 2:
                lines[-1] = banner
                colors[-1] = [(255, 235, 110) if ch != " " else None for ch in banner]
            self._current_lines = lines
            self._current_colors = colors
            if self._celebration_elapsed >= 5.0:
                self._celebration_mode = False
                self._celebration_renderer = None
                if self.state.pomodoro_break_enabled:
                    self._break_countdown_mode = True
                    self._remaining_seconds = 300.0
                    self._last_timer_sec = -1
                    self._init_first_frame()
                else:
                    self._break_mode = True
                    self._break_elapsed = 0.0
            self._recalculate_size()
            self._invalidate_art()
            self.update()
            return

        if self._break_mode:
            self._break_elapsed += dt
            self._current_lines = [
                "   * Mola Tamamlandi! *   ",
                " Yeni odak icin hazirsin. ",
            ]
            self._current_colors = None
            if self._break_elapsed > 1.5:
                self._fade_factor = max(0.0, 1.0 - (self._break_elapsed - 1.5) / 2.0)
                if self._fade_factor <= 0.02:
                    self.close_widget()
                    return
            self._recalculate_size()
            self._invalidate_art()
            self.update()
            return

        blink_changed = False
        if self.state.eye_blink_enabled:
            self._blink_timer += dt
            if not self._is_blinking and self._blink_timer >= 3.8:
                self._is_blinking = True
                self._blink_timer = 0.0
                blink_changed = True
            elif self._is_blinking and self._blink_timer >= 0.22:
                self._is_blinking = False
                self._blink_timer = 0.0
                blink_changed = True
        elif self._is_blinking:
            self._is_blinking = False
            blink_changed = True

        particles_on = self.is_particles_active() or self.state.sleep_zzz_enabled

        frame_advanced = False
        if self._procedural is not None:
            self._sync_procedural_grid()
            if not self._paused or self._current_lines == [] or self._orbiting or look_changed:
                pf = self._procedural.step(
                    dt if not self._paused else 0.0,
                    self.state.speed_multiplier,
                    yaw_offset=self.state.orbit_yaw,
                    pitch_offset=self.state.orbit_pitch,
                    cursor_look=self._cursor_look,
                    progress=self._pomodoro_progress(),
                )
                base_lines = pf.lines
                base_colors: Optional[List[List[Optional[RGB]]]] = pf.colors
                if self.state.flip_horizontal:
                    max_w = max((len(l) for l in base_lines), default=0)
                    base_lines = [l.ljust(max_w)[::-1].translate(MIRROR_CHAR_MAP) for l in base_lines]
                    base_colors = [row[::-1] for row in base_colors]
                frame_advanced = (not self._paused) or self._orbiting or look_changed
            else:
                base_lines = self._current_lines
                base_colors = self._current_colors
        else:
            old_idx = self._frame_idx
            if not self._paused and self.asset.frame_count > 1:
                base_fps = self.state.custom_fps if self.state.custom_fps else self.asset.default_fps
                effective_fps = max(0.2, base_fps * self.state.speed_multiplier)
                self._frame_accum += dt * effective_fps
                if self._frame_accum >= 1.0:
                    steps = int(self._frame_accum)
                    self._frame_accum -= steps
                    self._frame_idx = (self._frame_idx + steps) % self.asset.frame_count
            frame_advanced = self._frame_idx != old_idx
            if not (frame_advanced or blink_changed or look_changed or particles_on or is_rainbow or timer_changed or self._art_dirty):
                return
            base_lines, base_colors = self._get_static_frame(self._frame_idx)
            base_lines = self._apply_cursor_track_static(base_lines)

        base_lines = self._apply_eye_blink(base_lines)

        if particles_on:
            ptype_override = self.state.particle_override_type
            if not self.is_particles_active() and self.state.sleep_zzz_enabled:
                ptype_override = "none"
            eff_ptype = ptype_override if ptype_override else self.asset.particles.type
            pad_top, _pad_b, pad_left, _pad_r = ParticleEngine.compute_padding(
                eff_ptype, sleep_zzz=self.state.sleep_zzz_enabled
            )
            lines, flash = self.particle_engine.step(
                base_lines=base_lines,
                config=self.asset.particles,
                override_type=ptype_override,
                density_override=self.state.particle_density,
                sleep_zzz=self.state.sleep_zzz_enabled,
                dt=dt,
            )
            self._lightning_flash = flash
            if base_colors is not None:
                total_h = len(lines)
                total_w = max((len(l) for l in lines), default=1)
                padded_colors: List[List[Optional[RGB]]] = [[None] * total_w for _ in range(total_h)]
                for r_i, crow in enumerate(base_colors):
                    ty = pad_top + r_i
                    if 0 <= ty < total_h:
                        dst_row = padded_colors[ty]
                        limit = min(len(crow), total_w - pad_left)
                        for c_i in range(limit):
                            dst_row[pad_left + c_i] = crow[c_i]
                final_colors: Optional[List[List[Optional[RGB]]]] = padded_colors
            else:
                final_colors = None
        else:
            if self.particle_engine.particles:
                self.particle_engine.clear()
            lines = base_lines
            final_colors = base_colors
            self._lightning_flash = False

        old_dims = (len(self._current_lines), max((len(l) for l in self._current_lines), default=0))
        new_dims = (len(lines), max((len(l) for l in lines), default=0))
        unchanged = lines == self._current_lines and final_colors == self._current_colors
        self._current_lines = lines
        self._current_colors = final_colors
        if old_dims != new_dims:
            self._recalculate_size()

        # Çıktı bir önceki kareyle aynıysa (ör. yavaş shader) yeniden çizme
        if unchanged and not (blink_changed or timer_changed or self._art_dirty or is_rainbow or self._lightning_flash):
            return
        if frame_advanced or blink_changed or look_changed or particles_on or is_rainbow or timer_changed or self._art_dirty:
            self._invalidate_art()
            self.update()

    def _current_theme_info(self) -> Dict[str, object]:
        theme_key = self.asset.recommended_color if self.state.color_theme == "auto" else self.state.color_theme
        return self.theme_lib.get(theme_key)

    def _resolve_colors(self) -> tuple[QColor, QColor, QColor]:
        info = self._current_theme_info()
        if info.get("is_rainbow"):
            primary = QColor.fromHsvF(self._rainbow_hue, 0.78, 1.0)
            secondary = QColor.fromHsvF((self._rainbow_hue + 0.15) % 1.0, 0.78, 1.0)
            glow = QColor.fromHsvF(self._rainbow_hue, 0.65, 1.0)
        else:
            primary = QColor(str(info.get("primary", "#FFFFFF")))
            secondary = QColor(str(info.get("secondary", "#E2E8F0")))
            glow = QColor(str(info.get("glow", "#94A3B8")))

        if self._lightning_flash:
            primary = QColor("#F0F9FF")
            glow = QColor("#38BDF8")

        return primary, secondary, glow

    def _rebuild_art_pixmap(self) -> None:
        dpr = max(1.0, self.devicePixelRatioF())
        pw = max(1, int(math.ceil(self.width() * dpr)))
        ph = max(1, int(math.ceil(self.height() * dpr)))

        pm = QPixmap(pw, ph)
        pm.setDevicePixelRatio(dpr)
        pm.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        font = self._build_font()
        painter.setFont(font)
        char_w, line_h, ascent = self._get_font_metrics()

        alpha = max(0.0, min(1.0, self.state.opacity * self._fade_factor))
        alpha_255 = int(255 * alpha)
        primary, secondary, glow = self._resolve_colors()

        start_x = 12.0
        start_y = 10.0 + ascent
        lines = self._current_lines

        levels = self._read_levels() if self.state.behind_text_enabled else None
        lights = self._readability.light if (levels is not None and self._readability is not None) else None

        def cell_level(i: int, col: int) -> int:
            if levels is None or i >= len(levels) or col >= len(levels[i]):
                return 0
            return levels[i][col]

        # 1. Glow (opsiyonel, varsayılan kapalı): tek geçiş
        if self.state.glow_enabled:
            painter.setPen(QColor(glow.red(), glow.green(), glow.blue(), int(55 * alpha)))
            for i, line in enumerate(lines):
                if line.strip():
                    painter.drawText(QPointF(start_x + 1.2, start_y + i * line_h + 1.2), line)

        # 2. Okunabilirlik gölgesi: tek geçiş (yazının arkasına geçilen hücrelerde gölge yok)
        if self.state.shadow_enabled:
            painter.setPen(QColor(8, 10, 16, int(190 * alpha)))
            for i, line in enumerate(lines):
                if not line.strip():
                    continue
                if levels is not None:
                    line = "".join(" " if (ch != " " and cell_level(i, k) >= 2) else ch for k, ch in enumerate(line))
                    if not line.strip():
                        continue
                painter.drawText(QPointF(start_x + 1.0, start_y + i * line_h + 1.0), line)

        # 3. Ön plan
        multicolor = self._is_multicolor_active() and self._current_colors is not None
        any_flagged = levels is not None and any(any(r) for r in levels)
        if any_flagged:
            fallback_rgb: RGB = (secondary.red(), secondary.green(), secondary.blue()) if multicolor else (primary.red(), primary.green(), primary.blue())
            c_rows = self._current_colors if multicolor else []
            pen_cache: Dict[Tuple[RGB, int, bool], QColor] = {}
            quant = self._procedural is not None and multicolor
            fade = max(0.08, min(0.6, self.state.behind_text_fade))

            def key_at(i: int, k: int, c_row: list, c_len: int) -> Tuple[RGB, int, bool]:
                rgb = _quantize((c_row[k] if k < c_len else None) or fallback_rgb, quant)
                lv = cell_level(i, k)
                lt = bool(lights[i][k]) if (lv and lights is not None and i < len(lights) and k < len(lights[i])) else False
                return (rgb, lv, lt)

            for i, line in enumerate(lines):
                if not line.strip():
                    continue
                y = start_y + i * line_h
                c_row = c_rows[i] if i < len(c_rows) else []
                n = len(line)
                c_len = len(c_row)
                col_idx = 0
                while col_idx < n:
                    if line[col_idx] == " ":
                        col_idx += 1
                        continue
                    key = key_at(i, col_idx, c_row, c_len)
                    run_start = col_idx
                    col_idx += 1
                    while col_idx < n and line[col_idx] != " " and key_at(i, col_idx, c_row, c_len) == key:
                        col_idx += 1
                    qcol = pen_cache.get(key)
                    if qcol is None:
                        rgb, lv, lt = key
                        a255 = alpha_255
                        if lv:
                            # arkaya geç: soluklaş + arka plan parlaklığının zıddına doğru renk kaydır
                            a255 = int(alpha_255 * (1.0 - (lv / 3.0) * (1.0 - fade)))
                            contrast = (22, 24, 34) if lt else (255, 255, 255)
                            m = 0.22 * lv
                            rgb = (
                                int(rgb[0] + (contrast[0] - rgb[0]) * m),
                                int(rgb[1] + (contrast[1] - rgb[1]) * m),
                                int(rgb[2] + (contrast[2] - rgb[2]) * m),
                            )
                        qcol = QColor(rgb[0], rgb[1], rgb[2], a255)
                        pen_cache[key] = qcol
                    painter.setPen(qcol)
                    # Monospace yazı tipi: x konumu = başlangıç + sütun * karakter genişliği (O(1))
                    painter.drawText(QPointF(start_x + run_start * char_w, y), line[run_start:col_idx])
        elif multicolor:
            fallback_rgb2: RGB = (secondary.red(), secondary.green(), secondary.blue())
            c_rows2 = self._current_colors or []
            pen_cache2: Dict[RGB, QColor] = {}
            quant2 = self._procedural is not None  # 3B kareler: renkleri kuantala → daha uzun koşular, daha az drawText
            for i, line in enumerate(lines):
                if not line.strip():
                    continue
                y = start_y + i * line_h
                c_row = c_rows2[i] if i < len(c_rows2) else []
                n = len(line)
                c_len = len(c_row)
                col_idx = 0
                while col_idx < n:
                    if line[col_idx] == " ":
                        col_idx += 1
                        continue
                    rgb = _quantize((c_row[col_idx] if col_idx < c_len else None) or fallback_rgb2, quant2)
                    run_start = col_idx
                    col_idx += 1
                    while col_idx < n:
                        if line[col_idx] == " ":
                            break
                        if _quantize((c_row[col_idx] if col_idx < c_len else None) or fallback_rgb2, quant2) != rgb:
                            break
                        col_idx += 1
                    qcol = pen_cache2.get(rgb)
                    if qcol is None:
                        qcol = QColor(rgb[0], rgb[1], rgb[2], alpha_255)
                        pen_cache2[rgb] = qcol
                    painter.setPen(qcol)
                    painter.drawText(QPointF(start_x + run_start * char_w, y), line[run_start:col_idx])
        else:
            painter.setPen(QColor(primary.red(), primary.green(), primary.blue(), alpha_255))
            for i, line in enumerate(lines):
                if line.strip():
                    painter.drawText(QPointF(start_x, start_y + i * line_h), line)

        # 4. Optional Remaining Timer Pill below character
        if self._timer_active and self.state.show_timer_below and not self._break_mode and not self._celebration_mode:
            mins = int(self._remaining_seconds // 60)
            secs = int(self._remaining_seconds % 60)
            timer_str = f"[ Mola {mins:02d}:{secs:02d} ]" if self._break_countdown_mode else f"[ {mins:02d}:{secs:02d} ]"
            small_font = QFont(font)
            small_font.setPointSize(max(8, self.state.font_size - 4))
            painter.setFont(small_font)
            ty = start_y + len(lines) * line_h
            if self.state.shadow_enabled:
                painter.setPen(QColor(0, 0, 0, int(190 * alpha)))
                painter.drawText(QPointF(start_x + 1.0, ty + 1.0), timer_str)
            painter.setPen(QColor(secondary.red(), secondary.green(), secondary.blue(), int(215 * alpha)))
            painter.drawText(QPointF(start_x, ty), timer_str)

        painter.end()
        self._art_pixmap = pm
        self._art_dirty = False

    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)

        # CRITICAL WINDOWS HIT-TEST FIX:
        # Fill bounding box with alpha=1/255 so Windows routes mouse clicks, drags,
        # hover events and scroll wheel to this frameless widget instead of passing through.
        if not self.state.click_through:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 1))

        # Subtle hover frame + corner handles when mouse hovers or resizes
        if (self._hovered or self._resize_mode is not None) and not self.state.click_through:
            primary, _, _ = self._resolve_colors()
            painter.fillRect(self.rect().adjusted(2, 2, -2, -2), QColor(15, 23, 42, 48))
            pen = QPen(QColor(primary.red(), primary.green(), primary.blue(), 145), 1.3, Qt.PenStyle.DotLine)
            painter.setPen(pen)
            r = self.rect().adjusted(2, 2, -3, -3)
            painter.drawRoundedRect(r, 8, 8)

            active_mode = self._resize_mode or self._resize_hover_mode
            base_handle_col = QColor(primary.red(), primary.green(), primary.blue(), 215)
            active_handle_col = QColor(255, 235, 130, 255)
            l = 9

            # Corner handles
            for corner_name, pts in (
                ("top-left", ((r.left(), r.top(), r.left() + l, r.top()), (r.left(), r.top(), r.left(), r.top() + l))),
                ("top-right", ((r.right(), r.top(), r.right() - l, r.top()), (r.right(), r.top(), r.right(), r.top() + l))),
                ("bottom-left", ((r.left(), r.bottom(), r.left() + l, r.bottom()), (r.left(), r.bottom(), r.left(), r.bottom() - l))),
                ("bottom-right", ((r.right(), r.bottom(), r.right() - l, r.bottom()), (r.right(), r.bottom(), r.right(), r.bottom() - l))),
            ):
                is_active = active_mode == corner_name
                painter.setPen(QPen(active_handle_col if is_active else base_handle_col, 2.8 if is_active else 2.0))
                for x1, y1, x2, y2 in pts:
                    painter.drawLine(x1, y1, x2, y2)

            # Highlight edge line when hovering/dragging an edge
            if active_mode in ("left", "right", "top", "bottom"):
                painter.setPen(QPen(active_handle_col, 2.5))
                if active_mode == "left":
                    painter.drawLine(r.left(), r.top() + l, r.left(), r.bottom() - l)
                elif active_mode == "right":
                    painter.drawLine(r.right(), r.top() + l, r.right(), r.bottom() - l)
                elif active_mode == "top":
                    painter.drawLine(r.left() + l, r.top(), r.right() - l, r.top())
                elif active_mode == "bottom":
                    painter.drawLine(r.left() + l, r.bottom(), r.right() - l, r.bottom())

        if self._hd is not None:
            img = self._hd.image
            if img is not None:
                painter.drawImage(12, 10, img)
            return

        if self._art_dirty or self._art_pixmap is None:
            self._rebuild_art_pixmap()

        if self._art_pixmap is not None:
            painter.drawPixmap(0, 0, self._art_pixmap)

    # --- Resize Hit-Testing & Cursor Helpers ---

    def _hit_test_resize(self, pos: QPoint) -> Optional[str]:
        if self.state.click_through:
            return None
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()
        cm = max(4, min(CORNER_GRAB_MARGIN, w // 3, h // 3))
        em = max(4, min(EDGE_GRAB_MARGIN, w // 4, h // 4))

        left_c = x <= cm
        right_c = x >= w - cm
        top_c = y <= cm
        bottom_c = y >= h - cm

        if top_c and left_c:
            return "top-left"
        if top_c and right_c:
            return "top-right"
        if bottom_c and left_c:
            return "bottom-left"
        if bottom_c and right_c:
            return "bottom-right"

        if x <= em:
            return "left"
        if x >= w - em:
            return "right"
        if y <= em:
            return "top"
        if y >= h - em:
            return "bottom"
        return None

    @staticmethod
    def _cursor_for_mode(mode: Optional[str], dragging: bool = False) -> Qt.CursorShape:
        if mode in ("top-left", "bottom-right"):
            return Qt.CursorShape.SizeFDiagCursor
        if mode in ("top-right", "bottom-left"):
            return Qt.CursorShape.SizeBDiagCursor
        if mode in ("left", "right"):
            return Qt.CursorShape.SizeHorCursor
        if mode in ("top", "bottom"):
            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ClosedHandCursor if dragging else Qt.CursorShape.OpenHandCursor

    # --- Mouse & Keyboard Events ---

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        pos = self.mapFromGlobal(event.globalPosition().toPoint()) if hasattr(event, "globalPosition") else QPoint(self.width() // 2, self.height() // 2)
        self._resize_hover_mode = self._hit_test_resize(pos)
        self.setCursor(self._cursor_for_mode(self._resize_hover_mode))
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        if self._resize_mode is None:
            self._resize_hover_mode = None
            self.unsetCursor()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            mode = self._hit_test_resize(event.position().toPoint())
            if mode is not None:
                self._resize_mode = mode
                self._dragging = False
                self._orbiting = False
                self._resize_start_global = event.globalPosition().toPoint()
                self._resize_start_geom = self.geometry()
                self._resize_start_font = self.state.font_size
                self.setCursor(self._cursor_for_mode(mode))
                self.update()
                event.accept()
                return

            if self._procedural is not None and (
                bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier) or self.state.free_orbit_3d
            ):
                self._orbiting = True
                self._dragging = False
                self._orbit_start_global = event.globalPosition().toPoint()
                self._orbit_start_yaw = self.state.orbit_yaw
                self._orbit_start_pitch = self.state.orbit_pitch
                self.setCursor(Qt.CursorShape.SizeAllCursor)
                event.accept()
                return

            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._resize_mode is not None and (event.buttons() & Qt.MouseButton.LeftButton):
            mode = self._resize_mode
            delta = event.globalPosition().toPoint() - self._resize_start_global
            dx, dy = delta.x(), delta.y()
            sg = self._resize_start_geom
            sw, sh = max(1, sg.width()), max(1, sg.height())

            target_w, target_h = sw, sh
            if "right" in mode:
                target_w = sw + dx
            elif "left" in mode:
                target_w = sw - dx
            if "bottom" in mode:
                target_h = sh + dy
            elif "top" in mode:
                target_h = sh - dy

            has_x = ("left" in mode) or ("right" in mode)
            has_y = ("top" in mode) or ("bottom" in mode)
            if has_x and has_y:
                rx = target_w / sw
                ry = target_h / sh
                scale = rx if abs(rx - 1.0) >= abs(ry - 1.0) else ry
            elif has_x:
                scale = target_w / sw
            else:
                scale = target_h / sh

            scale = max(0.1, scale)
            new_font = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, int(round(self._resize_start_font * scale))))
            if new_font != self.state.font_size:
                self.state.font_size = new_font
                self._cached_font = None
                self._cached_font_metrics = None
                self._refresh_procedural_immediately()
                self._recalculate_size()
                self._invalidate_art()
                nx = (sg.x() + sg.width() - self.width()) if ("left" in mode) else sg.x()
                ny = (sg.y() + sg.height() - self.height()) if ("top" in mode) else sg.y()
                self.move(nx, ny)
                self.update()
            event.accept()
            return

        if self._orbiting and (event.buttons() & Qt.MouseButton.LeftButton):
            delta = event.globalPosition().toPoint() - self._orbit_start_global
            self.state.orbit_yaw = self._orbit_start_yaw + delta.x() * 0.015
            self.state.orbit_pitch = max(-1.2, min(1.2, self._orbit_start_pitch + delta.y() * 0.012))
            self._refresh_procedural_immediately()
            self._invalidate_art()
            self.update()
            event.accept()
            return

        if self._dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)
            event.accept()
            return

        hover_mode = self._hit_test_resize(event.position().toPoint())
        if hover_mode != self._resize_hover_mode:
            self._resize_hover_mode = hover_mode
            self.setCursor(self._cursor_for_mode(hover_mode))
            self.update()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            if self._resize_mode is not None:
                self._resize_mode = None
                self.state.x = self.x()
                self.state.y = self.y()
                self._save_state()
                hover_mode = self._hit_test_resize(event.position().toPoint())
                self._resize_hover_mode = hover_mode
                self.setCursor(self._cursor_for_mode(hover_mode))
                self.update()
                event.accept()
                return

            if self._orbiting:
                self._orbiting = False
                self._save_state()
                hover_mode = self._hit_test_resize(event.position().toPoint())
                self._resize_hover_mode = hover_mode
                self.setCursor(self._cursor_for_mode(hover_mode))
                event.accept()
                return

            if self._dragging:
                self._dragging = False
                hover_mode = self._hit_test_resize(event.position().toPoint())
                self._resize_hover_mode = hover_mode
                self.setCursor(self._cursor_for_mode(hover_mode))
                self.state.x = self.x()
                self.state.y = self.y()
                self._save_state()
                event.accept()

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta > 0:
            self.set_font_size(min(MAX_FONT_SIZE, self.state.font_size + 1))
        elif delta < 0:
            self.set_font_size(max(MIN_FONT_SIZE, self.state.font_size - 1))
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.set_font_size(min(MAX_FONT_SIZE, self.state.font_size + 1))
        elif key == Qt.Key.Key_Minus:
            self.set_font_size(max(MIN_FONT_SIZE, self.state.font_size - 1))
        elif key == Qt.Key.Key_Space:
            self._paused = not self._paused
        elif key == Qt.Key.Key_Escape:
            self.close_widget()

    def moveEvent(self, event) -> None:  # noqa: N802
        # Tam ekran uygulama/kilit varken başka ekrana taşınınca durumu yeniden değerlendir
        mon = PowerMonitor.instance()
        if mon.fullscreen_rect is not None or self._suspended:
            self._evaluate_suspension()
        super().moveEvent(event)

    def contextMenuEvent(self, event) -> None:  # noqa: N802
        menu = build_context_menu(self)
        menu.exec(event.globalPos())

    # --- Drag & Drop Community File Import ---

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:  # noqa: N802
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                p = url.toLocalFile().lower()
                if p.endswith(".ascii.json") or p.endswith(".json") or p.endswith(".txt"):
                    event.acceptProposedAction()
                    return

    def dropEvent(self, event: QDropEvent) -> None:  # noqa: N802
        for url in event.mimeData().urls():
            local = url.toLocalFile()
            if local:
                asset, msg = import_file_to_community(local, self.library.community_dir)
                if asset:
                    self.library.reload()
                    if "spawn_asset" in self.manager_callbacks:
                        self.manager_callbacks["spawn_asset"](asset.id)
                    else:
                        self.asset = asset
                        self._procedural = (
                            create_procedural_renderer(asset.procedural, asset.procedural_params)
                            if asset.procedural
                            else None
                        )
                        self._frame_idx = 0
                        self._init_first_frame()
                        self._recalculate_size()
                        self._invalidate_art()
                        self._update_timer_interval()
                else:
                    QMessageBox.warning(self, "İçe Aktarma Hatası", msg)

    # --- State Mutators & Persistence ---

    def _save_state(self) -> None:
        self.config_mgr.save_widget_state(self.state, self.slot)

    def set_opacity(self, opacity: float) -> None:
        self.state.opacity = max(0.15, min(1.0, opacity))
        self._invalidate_art()
        self._save_state()
        self.update()

    def _refresh_procedural_immediately(self) -> None:
        if self._procedural is not None:
            self._sync_procedural_grid()
            pf = self._procedural.step(
                0.0,
                1.0,
                yaw_offset=self.state.orbit_yaw,
                pitch_offset=self.state.orbit_pitch,
                cursor_look=self._cursor_look,
                progress=self._pomodoro_progress(),
            )
            self._current_lines = pf.lines
            self._current_colors = pf.colors

    def set_font_size(self, size: int) -> None:
        self.state.font_size = max(MIN_FONT_SIZE, min(MAX_FONT_SIZE, size))
        self._cached_font = None
        self._cached_font_metrics = None
        self._refresh_procedural_immediately()
        self._recalculate_size()
        self._invalidate_art()
        self._save_state()
        self.update()

    def set_grid_resolution(self, resolution: str) -> None:
        if resolution not in ("auto", "compact", "standard", "hd", "ultra"):
            resolution = "auto"
        self.state.grid_resolution = resolution
        self._refresh_procedural_immediately()
        self._recalculate_size()
        self._invalidate_art()
        self._save_state()
        self.update()

    def set_free_orbit(self, enabled: bool) -> None:
        self.state.free_orbit_3d = bool(enabled)
        self._save_state()

    def reset_orbit(self) -> None:
        self.state.orbit_yaw = 0.0
        self.state.orbit_pitch = 0.0
        self._refresh_procedural_immediately()
        self._invalidate_art()
        self._save_state()
        self.update()

    def set_track_cursor(self, enabled: bool) -> None:
        self.state.track_cursor = bool(enabled)
        self._cursor_look = self._compute_cursor_look()
        self._refresh_procedural_immediately()
        self._invalidate_art()
        self._update_timer_interval()
        self._save_state()
        self.update()

    def set_pomodoro_break_enabled(self, enabled: bool) -> None:
        self.state.pomodoro_break_enabled = bool(enabled)
        self._save_state()

    def set_line_spacing(self, spacing: float) -> None:
        self.state.line_spacing = max(0.75, min(1.15, float(spacing)))
        self._cached_font_metrics = None
        self._recalculate_size()
        self._invalidate_art()
        self._save_state()
        self.update()

    def set_speed_multiplier(self, mult: float) -> None:
        self.state.speed_multiplier = max(0.1, min(5.0, mult))
        self._update_timer_interval()
        self._save_state()

    def set_custom_fps(self, fps: Optional[float]) -> None:
        self.state.custom_fps = fps
        self._update_timer_interval()
        self._save_state()

    def set_color_theme(self, theme_key: str) -> None:
        self.state.color_theme = theme_key
        self._invalidate_art()
        self._update_timer_interval()
        self._save_state()
        self.update()

    def set_glow(self, enabled: bool) -> None:
        self.state.glow_enabled = enabled
        self._invalidate_art()
        self._save_state()
        self.update()

    def set_shadow(self, enabled: bool) -> None:
        self.state.shadow_enabled = enabled
        self._invalidate_art()
        self._save_state()
        self.update()

    def set_flip(self, enabled: bool) -> None:
        self.state.flip_horizontal = enabled
        self._invalidate_art()
        self._save_state()
        self.update()

    def set_always_on_top(self, enabled: bool) -> None:
        self.state.always_on_top = enabled
        self._apply_window_flags()
        self._evaluate_suspension()
        self._save_state()

    def set_click_through(self, enabled: bool) -> None:
        self.state.click_through = enabled
        self._hovered = False
        self._apply_window_flags()
        self._save_state()
        if "refresh_tray" in self.manager_callbacks:
            self.manager_callbacks["refresh_tray"]()

    def set_particles_enabled(self, enabled: bool) -> None:
        self.state.particles_enabled = enabled
        if not enabled:
            self.particle_engine.clear()
        self._invalidate_art()
        self._update_timer_interval()
        self._save_state()
        self.update()

    def set_particle_override(self, ptype: Optional[str]) -> None:
        self.state.particle_override_type = ptype
        if ptype and ptype != "none":
            self.state.particles_enabled = True
        self.particle_engine.clear()
        self._invalidate_art()
        self._update_timer_interval()
        self._save_state()
        self.update()

    def set_particle_density(self, density: str) -> None:
        self.state.particle_density = density
        self._save_state()

    def set_sleep_zzz(self, enabled: bool) -> None:
        self.state.sleep_zzz_enabled = enabled
        self._invalidate_art()
        self._update_timer_interval()
        self._save_state()
        self.update()

    def set_eye_blink(self, enabled: bool) -> None:
        self.state.eye_blink_enabled = enabled
        self._invalidate_art()
        self._update_timer_interval()
        self._save_state()
        self.update()

    def set_timer_minutes(self, mins: int) -> None:
        self.state.duration_minutes = max(0, mins)
        self._break_mode = False
        self._celebration_mode = False
        self._celebration_renderer = None
        self._break_countdown_mode = False
        self._fade_factor = 1.0
        self._last_timer_sec = -1
        if mins > 0:
            self._timer_active = True
            self._remaining_seconds = float(mins * 60)
        else:
            self._timer_active = False
            self._remaining_seconds = 0.0
        self._refresh_procedural_immediately()
        self._recalculate_size()
        self._invalidate_art()
        self._update_timer_interval()
        self._save_state()
        self.update()

    def set_show_timer_below(self, show: bool) -> None:
        self.state.show_timer_below = show
        self._recalculate_size()
        self._invalidate_art()
        self._save_state()
        self.update()

    def closeEvent(self, event) -> None:  # noqa: N802
        """Her kapanış yolunda (Alt+F4, kod, oturum sonu) `closed` sinyali tam bir kez gider."""
        if not self._close_notified:
            self._close_notified = True
            try:
                self._tick_timer.stop()
                if self._readability is not None:
                    self._readability.stop()
                    self._readability = None
                self.state.x = self.x()
                self.state.y = self.y()
                self._save_state()
            except Exception:
                log.exception("kapanışta durum kaydedilemedi")
            self.closed.emit(self.instance_id)
        super().closeEvent(event)

    def close_widget(self) -> None:
        self.close()
