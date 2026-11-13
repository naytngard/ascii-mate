"""Klasik (1.0/2.0) widget'lar için hücre birleştirici: glif atlası + yalnızca değişen hücreler.

Eski yol her karede tüm satırları `QPainter.drawText` ile (gölge için iki kez) yeniden çiziyordu; 1.5 DPI'da bu tek başına
~6 ms/kare tutuyordu. Bu yol:
  * widget'ın yazı tipiyle, gerçek ölçekte (DPR dahil) 95 ASCII glifini bir kez alfa maskesine çizer,
  * okunabilirlik gölgesini maskeye "pişirir" (1 px kaydırılmış koyu kopya → ek çizim geçişi yok),
  * kareyi (karakter kodu, renk) dizisi olarak alır, önceki kareyle karşılaştırır ve yalnızca değişen hücreleri
    premultiplied BGRA tampona yazar; paintEvent tek `drawImage` yapar.
Glow veya ASCII dışı karakter gerektiğinde widget eski `drawText` yoluna döner.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
from PyQt6.QtCore import QPointF
from PyQt6.QtGui import QColor, QFont, QImage, QPainter

_ATLAS: Dict[tuple, Tuple[np.ndarray, np.ndarray]] = {}
SHADOW_ALPHA = 0.75  # eski gölge kalemi: QColor(8, 10, 16, 190)
BLOCK_CACHE = 1024  # önceden birleştirilmiş (karakter, renk) hücre blokları; renk kanal başına 5 bit (32 kademe)


def build_text_atlas(font: QFont, cwp: int, chp: int, baseline: float, dpr: float, shadow_px: int) -> Tuple[np.ndarray, np.ndarray]:
    """(fg_alpha, toplam_alpha) — ikisi de (95, chp, cwp) uint8. toplam = ön plan + altına pişirilmiş gölge."""
    key = (font.key(), cwp, chp, round(baseline, 3), round(dpr, 3), shadow_px)
    hit = _ATLAS.get(key)
    if hit is not None:
        return hit
    fg = np.zeros((95, chp, cwp), np.uint8)
    for code in range(33, 127):
        img = QImage(cwp, chp, QImage.Format.Format_ARGB32_Premultiplied)
        img.fill(0)
        img.setDevicePixelRatio(dpr)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QPointF(0.0, baseline), chr(code))
        p.end()
        ptr = img.constBits()
        ptr.setsize(img.sizeInBytes())
        fg[code - 32] = np.frombuffer(ptr, np.uint8).reshape(chp, img.bytesPerLine() // 4, 4)[:, :cwp, 3]
    total = fg.copy()
    if shadow_px > 0:
        sh = np.zeros_like(fg)
        sh[:, shadow_px:, shadow_px:] = fg[:, :-shadow_px, :-shadow_px]
        a = fg.astype(np.uint32)
        total = (a + (sh.astype(np.uint32) * int(SHADOW_ALPHA * 256) >> 8) * (255 - a) // 255).astype(np.uint8)
    _ATLAS[key] = (fg, total)
    return fg, total


class ClassicCellRenderer:
    """Tek widget'ın hücre tamponu. `render()` hiçbir hücre değişmediyse False döner (çizim gerekmez)."""

    def __init__(self) -> None:
        self.cwp = self.chp = 0
        self.dpr = 1.0
        self.rows = self.cols = 0
        self.opacity = 1.0
        self._cfg_key: Optional[tuple] = None
        self._fg: Optional[np.ndarray] = None
        self._tot: Optional[np.ndarray] = None
        self._fg_op: Optional[np.ndarray] = None
        self._tot_op: Optional[np.ndarray] = None
        self._buf: Optional[np.ndarray] = None
        self._img: Optional[QImage] = None
        self._prev_chars: Optional[np.ndarray] = None
        self._prev_colors: Optional[np.ndarray] = None
        self._prev_levels: Optional[np.ndarray] = None
        self._full = True
        self.last_dirty: Optional[Tuple[int, int, int, int]] = None  # (r0, c0, r1, c1) son render'da değişen hücre kutusu
        self._table: Optional[np.ndarray] = None  # (BLOCK_CACHE, chp*cwp, 4) hazır BGRA hücre blokları
        self._slot: Dict[int, int] = {}
        self._n_blocks = 0

    @property
    def image(self) -> Optional[QImage]:
        return self._img

    def invalidate(self) -> None:
        self._full = True

    def dirty_rect_logical(self, ox: float, oy: float) -> Optional[Tuple[int, int, int, int]]:
        """Son değişen hücre kutusunun widget koordinatlarındaki dikdörtgeni (x, y, w, h); gölge için 2 px pay."""
        if self.last_dirty is None:
            return None
        r0, c0, r1, c1 = self.last_dirty
        x = ox + c0 * self.cwp / self.dpr - 2
        y = oy + r0 * self.chp / self.dpr - 2
        w = (c1 - c0 + 1) * self.cwp / self.dpr + 5
        h = (r1 - r0 + 1) * self.chp / self.dpr + 5
        return int(x), int(y), int(w) + 1, int(h) + 1

    def configure(self, font: QFont, char_w: float, line_h: float, ascent: float, font_h: float, dpr: float,
                  opacity: float, shadow: bool) -> None:
        cwp = max(1, int(round(char_w * dpr)))
        chp = max(1, int(round(line_h * dpr)))
        # Satır yüksekliği (0.88×) yazı yüksekliğinden kısa: glifleri taşan kadar yukarı al (üstteki boş iç boşluk kırpılır,
        # alt çizgi '_' ve alt uzantılar korunur).
        baseline = ascent - max(0.0, font_h - line_h)
        shadow_px = max(1, int(round(dpr))) if shadow else 0
        key = (font.key(), cwp, chp, round(baseline, 3), round(dpr, 3), shadow_px)
        if key != self._cfg_key:
            self._cfg_key = key
            self.cwp, self.chp, self.dpr = cwp, chp, dpr
            self._fg, self._tot = build_text_atlas(font, cwp, chp, baseline, dpr, shadow_px)
            self._fg_op = None
            self._full = True
        op = max(0.0, min(1.0, opacity))
        if self._fg_op is None or abs(op - self.opacity) > 1e-4:
            self.opacity = op
            m = int(op * 256)
            self._fg_op = ((self._fg.astype(np.uint16) * m) >> 8).astype(np.uint8)
            self._tot_op = ((self._tot.astype(np.uint16) * m) >> 8).astype(np.uint8)
            self._full = True
            self._table = None  # opaklık/atlas değişti: blok önbelleği geçersiz
            self._slot.clear()
            self._n_blocks = 0

    def _ensure_buffer(self, rows: int, cols: int) -> None:
        if self._buf is not None and (rows, cols) == (self.rows, self.cols) and self._buf.shape[:2] == (rows * self.chp, cols * self.cwp):
            return
        self.rows, self.cols = rows, cols
        self._buf = np.zeros((rows * self.chp, cols * self.cwp, 4), np.uint8)
        self._img = QImage(self._buf.data, cols * self.cwp, rows * self.chp, cols * self.cwp * 4,
                           QImage.Format.Format_ARGB32_Premultiplied)
        self._img.setDevicePixelRatio(self.dpr)
        self._full = True

    def render(self, chars: np.ndarray, colors: np.ndarray, levels: Optional[np.ndarray] = None,
               light: Optional[np.ndarray] = None, fade: float = 0.2) -> bool:
        assert self._fg_op is not None and self._tot_op is not None
        rows, cols = chars.shape
        self._ensure_buffer(rows, cols)
        if levels is not None and levels.shape != chars.shape:
            levels = None
        if self._full or self._prev_chars is None or self._prev_chars.shape != chars.shape:
            self._buf[...] = 0
            changed = chars != 32
        else:
            changed = chars != self._prev_chars
            changed |= (colors != self._prev_colors).any(axis=-1)
            if levels is not None or self._prev_levels is not None:
                a = levels if levels is not None else np.zeros(chars.shape, np.int8)
                b = self._prev_levels if self._prev_levels is not None else np.zeros(chars.shape, np.int8)
                changed |= a != b
        self._prev_chars, self._prev_colors = chars.copy(), colors.copy()
        self._prev_levels = None if levels is None else levels.copy()
        self._full = False
        rr, cc = np.nonzero(changed)
        if rr.size == 0:
            self.last_dirty = None
            return False
        self.last_dirty = (int(rr.min()), int(cc.min()), int(rr.max()), int(cc.max()))
        idx = chars[rr, cc].astype(np.intp) - 32
        col = colors[rr, cc]
        npx = self.chp * self.cwp
        view = self._buf.reshape(rows, self.chp, cols, self.cwp, 4).transpose(0, 2, 1, 3, 4)
        if levels is None:
            # Hızlı yol: (karakter, 5-bit renk) → önceden birleştirilmiş blok; yalnızca yeni anahtarlar hesaplanır
            q = (col >> 3).astype(np.uint32)
            key = (idx.astype(np.uint32) << 15) | (q[:, 0] << 10) | (q[:, 1] << 5) | q[:, 2]
            uk, inv = np.unique(key, return_inverse=True)
            if self._table is None or self._table.shape[1] != npx:
                self._table = np.zeros((BLOCK_CACHE, npx, 4), np.uint8)
                self._slot.clear()
                self._n_blocks = 0
            uk_list = uk.tolist()
            slots = [self._slot.get(k, -1) for k in uk_list]
            missing = [i for i, s in enumerate(slots) if s < 0]
            if missing:
                if self._n_blocks + len(missing) > BLOCK_CACHE:
                    self._slot.clear()
                    self._n_blocks = 0
                    missing = list(range(len(uk_list)))
                mk = uk[missing]
                m_idx = (mk >> 15).astype(np.intp)
                m_col = np.stack([((mk >> s) & 31) << 3 | 4 for s in (10, 5, 0)], axis=1).astype(np.uint16)
                a16 = self._fg_op[m_idx].reshape(len(missing), npx).astype(np.uint16)
                blk = np.empty((len(missing), npx, 4), np.uint8)
                tmp = np.empty(a16.shape, np.uint16)
                for dst, src in ((0, 2), (1, 1), (2, 0)):
                    np.multiply(a16, m_col[:, src : src + 1], out=tmp)
                    tmp >>= 8
                    blk[:, :, dst] = tmp
                blk[:, :, 3] = self._tot_op[m_idx].reshape(len(missing), npx)
                start = self._n_blocks
                self._table[start : start + len(missing)] = blk
                for j, i in enumerate(missing):
                    self._slot[uk_list[i]] = start + j
                    slots[i] = start + j
                self._n_blocks += len(missing)
            sl = np.asarray(slots, np.intp)[inv.reshape(-1)]
            view[rr, cc] = self._table[sl].reshape(rr.size, self.chp, self.cwp, 4)
            return True
        if levels is None:
            fga = self._fg_op[idx].reshape(rr.size, npx)
            tota = self._tot_op[idx].reshape(rr.size, npx)
            cols16 = col.astype(np.uint16)
        else:
            lv = levels[rr, cc].astype(np.float32)
            fac = 1.0 - (lv / 3.0) * (1.0 - fade)
            fga = (self._fg_op[idx].reshape(rr.size, npx) * fac[:, None]).astype(np.uint8)
            tota = (self._tot_op[idx].reshape(rr.size, npx) * fac[:, None]).astype(np.uint8)
            lt = light[rr, cc] if light is not None else np.zeros(rr.size, bool)
            contrast = np.where(lt[:, None], 22, 255).astype(np.float32)
            m = (0.22 * lv)[:, None]
            cols16 = (col + (contrast - col) * m).astype(np.uint16)
        a16 = fga.astype(np.uint16)
        out = np.empty((rr.size, npx, 4), np.uint8)
        tmp = np.empty(a16.shape, np.uint16)
        for dst, src in ((0, 2), (1, 1), (2, 0)):  # premultiplied BGRA; gölge siyah olduğundan renge katkısı yok
            np.multiply(a16, cols16[:, src : src + 1], out=tmp)
            tmp >>= 8
            out[:, :, dst] = tmp
        out[:, :, 3] = tota
        view[rr, cc] = out.reshape(rr.size, self.chp, self.cwp, 4)
        return True


def lines_to_arrays(lines, colors, fallback: Tuple[int, int, int]) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """Satır listesi + (isteğe bağlı) hücre renkleri → (chars uint8 (r,c), colors uint8 (r,c,3)). ASCII dışıysa None."""
    rows = len(lines)
    cols = max((len(l) for l in lines), default=0)
    if rows == 0 or cols == 0:
        return None
    try:
        raw = "".join(l.ljust(cols) for l in lines).encode("ascii")
    except UnicodeEncodeError:
        return None
    chars = np.frombuffer(raw, np.uint8).reshape(rows, cols).copy()
    chars[(chars < 32) | (chars > 126)] = 32
    col = np.empty((rows, cols, 3), np.uint8)
    col[...] = fallback
    if colors:
        for r, crow in enumerate(colors[:rows]):
            n = min(len(crow), cols)
            if n:
                vals = [c if c is not None else fallback for c in crow[:n]]
                col[r, :n] = vals
    return chars, col
