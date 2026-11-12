"""Floating transparent, frameless, draggable, scalable PyQt6 ASCII widget with offscreen QPixmap cache and HD multi-color 3D support."""

from __future__ import annotations

import math
import time
from typing import Callable, Dict, List, Optional, Tuple

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import (
    QColor,
    QDragEnterEvent,
    QDropEvent,
    QFont,
    QFontMetricsF,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget

from src.core.config_manager import ConfigManager
from src.core.converter import import_file_to_community
from src.core.library import AnimationLibrary, ThemeLibrary
from src.core.models import AnimationAsset, WidgetState
from src.core.particle_engine import ParticleEngine
from src.core.procedural_engine import BaseProceduralRenderer, create_procedural_renderer
from src.gui.context_menu import build_context_menu

RGB = Tuple[int, int, int]

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
    ) -> None:
        super().__init__()
        self.instance_id = instance_id
        self.asset = asset
        self.library = library
        self.theme_lib = theme_lib
        self.config_mgr = config_mgr
        self.manager_callbacks = manager_callbacks or {}

        self.state: WidgetState = self.config_mgr.get_widget_state(asset.id)
        self.particle_engine = ParticleEngine()

        # Optional live 3D / shader procedural engine
        self._procedural: Optional[BaseProceduralRenderer] = (
            create_procedural_renderer(asset.procedural, asset.procedural_params)
            if asset.procedural
            else None
        )

        # Runtime animation state
        self._frame_idx: int = 0
        self._frame_accum: float = 0.0
        self._paused: bool = False
        self._hovered: bool = False
        self._dragging: bool = False
        self._drag_offset: QPoint = QPoint()
        self._rainbow_hue: float = 0.0
        self._lightning_flash: bool = False
        self._last_tick_time: float = time.monotonic()
        self._last_timer_sec: int = -1

        # Eye blink state
        self._blink_timer: float = 0.0
        self._is_blinking: bool = False

        # Study timer / fade-out state
        self._remaining_seconds: float = float(self.state.duration_minutes * 60) if self.state.duration_minutes > 0 else 0.0
        self._timer_active: bool = self.state.duration_minutes > 0
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

    def _init_first_frame(self) -> None:
        if self._procedural is not None:
            pf = self._procedural.render_at(0.0)
            self._current_lines = pf.lines
            self._current_colors = pf.colors
        else:
            self._current_lines, self._current_colors = self._get_static_frame(0)

    def _target_tick_ms(self) -> int:
        if self._procedural is not None:
            fps = self.state.custom_fps if self.state.custom_fps else self.asset.default_fps
            eff = max(12.0, min(30.0, fps * self.state.speed_multiplier))
            return max(33, int(round(1000.0 / eff)))
        fps = self.state.custom_fps if self.state.custom_fps else self.asset.default_fps
        if fps * self.state.speed_multiplier > 16.0:
            return 33
        return 62

    def _update_timer_interval(self) -> None:
        interval = self._target_tick_ms()
        if not self._tick_timer.isActive() or self._tick_timer.interval() != interval:
            self._tick_timer.start(interval)

    def _invalidate_art(self) -> None:
        self._art_dirty = True

    def _apply_window_flags(self, initial: bool = False) -> None:
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
        if self.state.always_on_top:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        if self.state.click_through:
            flags |= Qt.WindowType.WindowTransparentForInput
        self.setWindowFlags(flags)
        if not initial:
            self.show()

    def _restore_or_place_position(self) -> None:
        screen = QApplication.primaryScreen()
        avail = screen.availableGeometry() if screen else QRectF(0, 0, 1280, 720).toRect()
        if self.state.x is not None and self.state.y is not None:
            nx = max(avail.left(), min(avail.right() - self.width(), self.state.x))
            ny = max(avail.top(), min(avail.bottom() - self.height(), self.state.y))
            self.move(nx, ny)
        else:
            offset = (hash(self.instance_id) % 5) * 36
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
        out = []
        for l in lines:
            nl = (
                l.replace("o.o", "-.-")
                .replace("O.O", "-.-")
                .replace("^.^", "-.-")
                .replace("•.•", "-.-")
                .replace("◉.◉", "-.-")
                .replace("o_o", "-_-")
                .replace("O_O", "-_-")
                .replace("•_•", "-_-")
                .replace("o o", "- -")
                .replace("0 0", "- -")
                .replace("^ ^", "- -")
                .replace("O,O", "-,-")
                .replace("(o )", "(- )")
                .replace("( o)", "( -)")
                .replace("oωo", "-ω-")
                .replace("^ω^", "-ω-")
            )
            out.append(nl)
        return out

    def is_particles_active(self) -> bool:
        if self.state.particle_override_type is not None:
            return self.state.particle_override_type != "none"
        if self.state.particles_enabled is not None:
            return self.state.particles_enabled
        return self.asset.particles.enabled_by_default

    def _is_multicolor_active(self) -> bool:
        if self._current_colors is None or self._lightning_flash or self._break_mode:
            return False
        return self.state.color_theme in ("auto", "auto_hd")

    def _recalculate_size(self) -> None:
        char_w, line_h, _ = self._get_font_metrics()
        lines = self._current_lines or ["(Boş)"]
        cols = max((len(l) for l in lines), default=10)
        rows = len(lines)

        pad_x = 24
        pad_y = 22
        extra_timer_h = int(math.ceil(line_h * 1.1)) if (self._timer_active and self.state.show_timer_below) else 0

        w = int(math.ceil(cols * char_w)) + pad_x
        h = int(math.ceil(rows * line_h)) + pad_y + extra_timer_h
        new_w, new_h = max(90, w), max(60, h)
        if new_w != self.width() or new_h != self.height():
            self.resize(new_w, new_h)
            self._invalidate_art()

    def _on_tick(self) -> None:
        now = time.monotonic()
        dt = min(0.25, max(0.01, now - self._last_tick_time))
        self._last_tick_time = now

        theme_info = self._current_theme_info()
        is_rainbow = bool(theme_info.get("is_rainbow")) and not self._is_multicolor_active()
        if is_rainbow:
            self._rainbow_hue = (self._rainbow_hue + dt * 0.14) % 1.0

        timer_changed = False
        if self._timer_active and not self._break_mode:
            self._remaining_seconds -= dt
            cur_sec = max(0, int(self._remaining_seconds))
            if cur_sec != self._last_timer_sec:
                self._last_timer_sec = cur_sec
                timer_changed = True
            if self._remaining_seconds <= 0:
                self._remaining_seconds = 0.0
                self._break_mode = True
                self._break_elapsed = 0.0
                self._invalidate_art()

        if self._break_mode:
            self._break_elapsed += dt
            self._current_lines = [
                "   * Mola Zamani! *    ",
                " Dinlenmeyi hak ettin. ",
            ]
            self._current_colors = None
            if self._break_elapsed > 3.5:
                self._fade_factor = max(0.0, 1.0 - (self._break_elapsed - 3.5) / 2.0)
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
            if not self._paused or self._current_lines == []:
                pf = self._procedural.step(dt if not self._paused else 0.0, self.state.speed_multiplier)
                base_lines = pf.lines
                base_colors: Optional[List[List[Optional[RGB]]]] = pf.colors
                if self.state.flip_horizontal:
                    max_w = max((len(l) for l in base_lines), default=0)
                    base_lines = [l.ljust(max_w)[::-1].translate(MIRROR_CHAR_MAP) for l in base_lines]
                    base_colors = [row[::-1] for row in base_colors]
                frame_advanced = not self._paused
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
            if not (frame_advanced or blink_changed or particles_on or is_rainbow or timer_changed or self._art_dirty):
                return
            base_lines, base_colors = self._get_static_frame(self._frame_idx)

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
        self._current_lines = lines
        self._current_colors = final_colors
        if old_dims != new_dims:
            self._recalculate_size()

        if frame_advanced or blink_changed or particles_on or is_rainbow or timer_changed or self._art_dirty:
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

        # 1. Soft Neon Glow Pass (rendered once into cached offscreen QPixmap)
        if self.state.glow_enabled:
            glow_col = QColor(glow.red(), glow.green(), glow.blue(), int(42 * alpha))
            painter.setPen(glow_col)
            for dx, dy in ((-1.3, 0.0), (1.3, 0.0), (0.0, -1.3), (0.0, 1.3)):
                for i, line in enumerate(lines):
                    if line.strip():
                        painter.drawText(QPointF(start_x + dx, start_y + i * line_h + dy), line)

        # 2. Readability Drop Shadow / Outline Pass
        if self.state.shadow_enabled:
            shadow_col = QColor(8, 10, 16, int(195 * alpha))
            painter.setPen(shadow_col)
            for dx, dy in ((1.0, 1.0), (-1.0, 0.0), (0.0, 1.0)):
                for i, line in enumerate(lines):
                    if line.strip():
                        painter.drawText(QPointF(start_x + dx, start_y + i * line_h + dy), line)

        # 3. Foreground Pass (Multi-color HD run-batched OR crisp monochrome)
        if self._is_multicolor_active() and self._current_colors is not None:
            fallback_rgb: RGB = (secondary.red(), secondary.green(), secondary.blue())
            c_rows = self._current_colors
            pen_cache: Dict[RGB, QColor] = {}

            for i, line in enumerate(lines):
                if not line.strip():
                    continue
                y = start_y + i * line_h
                c_row = c_rows[i] if i < len(c_rows) else []
                n = len(line)
                c_len = len(c_row)
                col_idx = 0
                while col_idx < n:
                    ch = line[col_idx]
                    if ch == " ":
                        col_idx += 1
                        continue
                    rgb = (c_row[col_idx] if col_idx < c_len else None) or fallback_rgb
                    run_start = col_idx
                    col_idx += 1
                    while col_idx < n:
                        nch = line[col_idx]
                        if nch == " ":
                            break
                        nrgb = (c_row[col_idx] if col_idx < c_len else None) or fallback_rgb
                        if nrgb != rgb:
                            break
                        col_idx += 1
                    qcol = pen_cache.get(rgb)
                    if qcol is None:
                        qcol = QColor(rgb[0], rgb[1], rgb[2], alpha_255)
                        pen_cache[rgb] = qcol
                    painter.setPen(qcol)
                    painter.drawText(QPointF(start_x + run_start * char_w, y), line[run_start:col_idx])
        else:
            fg_col = QColor(primary.red(), primary.green(), primary.blue(), alpha_255)
            painter.setPen(fg_col)
            for i, line in enumerate(lines):
                if line.strip():
                    painter.drawText(QPointF(start_x, start_y + i * line_h), line)

        # 4. Optional Remaining Timer Pill below character
        if self._timer_active and self.state.show_timer_below and not self._break_mode:
            mins = int(self._remaining_seconds // 60)
            secs = int(self._remaining_seconds % 60)
            timer_str = f"⏱ {mins:02d}:{secs:02d}"
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

        # Subtle hover frame + corner handles when mouse hovers
        if self._hovered and not self.state.click_through:
            primary, _, _ = self._resolve_colors()
            painter.fillRect(self.rect().adjusted(2, 2, -2, -2), QColor(15, 23, 42, 48))
            pen = QPen(QColor(primary.red(), primary.green(), primary.blue(), 145), 1.3, Qt.PenStyle.DotLine)
            painter.setPen(pen)
            painter.drawRoundedRect(self.rect().adjusted(2, 2, -3, -3), 8, 8)

            handle_pen = QPen(QColor(primary.red(), primary.green(), primary.blue(), 210), 2.0)
            painter.setPen(handle_pen)
            r = self.rect().adjusted(2, 2, -3, -3)
            l = 7
            painter.drawLine(r.left(), r.top(), r.left() + l, r.top())
            painter.drawLine(r.left(), r.top(), r.left(), r.top() + l)
            painter.drawLine(r.right(), r.top(), r.right() - l, r.top())
            painter.drawLine(r.right(), r.top(), r.right(), r.top() + l)
            painter.drawLine(r.left(), r.bottom(), r.left() + l, r.bottom())
            painter.drawLine(r.left(), r.bottom(), r.left(), r.bottom() - l)
            painter.drawLine(r.right(), r.bottom(), r.right() - l, r.bottom())
            painter.drawLine(r.right(), r.bottom(), r.right(), r.bottom() - l)

        if self._art_dirty or self._art_pixmap is None:
            self._rebuild_art_pixmap()

        if self._art_pixmap is not None:
            painter.drawPixmap(0, 0, self._art_pixmap)

    # --- Mouse & Keyboard Events ---

    def enterEvent(self, event) -> None:  # noqa: N802
        self._hovered = True
        self.setCursor(Qt.CursorShape.OpenHandCursor)
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event) -> None:  # noqa: N802
        self._hovered = False
        self.unsetCursor()
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()

    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if self._dragging and (event.buttons() & Qt.MouseButton.LeftButton):
            new_pos = event.globalPosition().toPoint() - self._drag_offset
            self.move(new_pos)
            event.accept()

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            self.state.x = self.x()
            self.state.y = self.y()
            self._save_state()
            event.accept()

    def wheelEvent(self, event) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta > 0:
            self.set_font_size(min(42, self.state.font_size + 1))
        elif delta < 0:
            self.set_font_size(max(8, self.state.font_size - 1))
        event.accept()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.key()
        if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.set_font_size(min(42, self.state.font_size + 1))
        elif key == Qt.Key.Key_Minus:
            self.set_font_size(max(8, self.state.font_size - 1))
        elif key == Qt.Key.Key_Space:
            self._paused = not self._paused
        elif key == Qt.Key.Key_Escape:
            self.close_widget()

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
        self.config_mgr.save_widget_state(self.state)

    def set_opacity(self, opacity: float) -> None:
        self.state.opacity = max(0.15, min(1.0, opacity))
        self._invalidate_art()
        self._save_state()
        self.update()

    def set_font_size(self, size: int) -> None:
        self.state.font_size = max(8, min(42, size))
        self._cached_font = None
        self._cached_font_metrics = None
        self._recalculate_size()
        self._invalidate_art()
        self._save_state()
        self.update()

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
        self._save_state()
        self.update()

    def set_particle_override(self, ptype: Optional[str]) -> None:
        self.state.particle_override_type = ptype
        if ptype and ptype != "none":
            self.state.particles_enabled = True
        self.particle_engine.clear()
        self._invalidate_art()
        self._save_state()
        self.update()

    def set_particle_density(self, density: str) -> None:
        self.state.particle_density = density
        self._save_state()

    def set_sleep_zzz(self, enabled: bool) -> None:
        self.state.sleep_zzz_enabled = enabled
        self._invalidate_art()
        self._save_state()
        self.update()

    def set_eye_blink(self, enabled: bool) -> None:
        self.state.eye_blink_enabled = enabled
        self._invalidate_art()
        self._save_state()
        self.update()

    def set_timer_minutes(self, mins: int) -> None:
        self.state.duration_minutes = max(0, mins)
        self._break_mode = False
        self._fade_factor = 1.0
        self._last_timer_sec = -1
        if mins > 0:
            self._timer_active = True
            self._remaining_seconds = float(mins * 60)
        else:
            self._timer_active = False
            self._remaining_seconds = 0.0
        self._recalculate_size()
        self._invalidate_art()
        self._save_state()
        self.update()

    def set_show_timer_below(self, show: bool) -> None:
        self.state.show_timer_below = show
        self._recalculate_size()
        self._invalidate_art()
        self._save_state()
        self.update()

    def close_widget(self) -> None:
        self.state.x = self.x()
        self.state.y = self.y()
        self._save_state()
        self._tick_timer.stop()
        self.closed.emit(self.instance_id)
        self.close()
