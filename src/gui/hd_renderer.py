"""HD çizici: NumPy glyph atlası + değişen hücrelerin tek bir QImage tamponuna yazılması.

Her kare `drawText` ile çizilmez: 95 ASCII glifi bir kez maske (alfa) olarak çizilir; kare, glif maskeleri × hücre rengi
çarpımıyla premultiplied BGRA tampona birleştirilir. Yalnızca önceki kareye göre değişen hücreler güncellenir
(durağan kare: sıfır iş), paintEvent tek `drawImage` yapar.
"""

from __future__ import annotations

from typing import Dict, Optional, Tuple

import numpy as np
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QPainter

from src.core.app_logging import get_logger
from src.core.hd_format import HDReader
from src.core.models import AnimationAsset

log = get_logger("hd")

GLYPH_GAIN = 1.6  # küçük hücrelerde glif kapsama alanı düşük kalır; hafif kazanç parlaklığı korur
_ATLAS_CACHE: Dict[Tuple[int, int], np.ndarray] = {}

# Kaliteye göre (ondalık küçültme, FPS üst sınırı)
HD_QUALITY: Dict[str, Tuple[int, float]] = {
    "low": (2, 8.0),  # sütun/satır sayısı yarıya iner, hücre pikseli ikiye katlanır (aynı fiziksel boyut)
    "medium": (1, 12.0),
    "high": (1, 15.0),
}
HD_ABS_FPS_CAP = 15.0
BLOCK_CACHE = 2048  # önceden birleştirilmiş (karakter, renk) hücre blokları


def build_atlas(cw: int, ch: int) -> np.ndarray:
    """(95, ch, cw) uint8 alfa maskeleri (ASCII 32..126)."""
    key = (cw, ch)
    atlas = _ATLAS_CACHE.get(key)
    if atlas is not None:
        return atlas
    font = QFont()
    font.setFamilies(["Cascadia Mono", "Consolas", "Courier New", "Monospace"])
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPixelSize(max(3, int(ch * 0.82)))
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    font.setWeight(QFont.Weight.Bold)  # küçük hücrelerde kalın glif: daha çok mürekkep → koyu zeminde daha parlak resim
    atlas = np.zeros((95, ch, cw), np.uint8)
    for code in range(33, 127):
        img = QImage(cw, ch, QImage.Format.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        p.setFont(font)
        p.setPen(QColor(255, 255, 255))
        p.drawText(QRectF(0, 0, cw, ch), int(Qt.AlignmentFlag.AlignCenter), chr(code))
        p.end()
        ptr = img.constBits()
        ptr.setsize(img.sizeInBytes())
        arr = np.frombuffer(ptr, np.uint8).reshape(ch, img.bytesPerLine() // 4, 4)[:, :cw, 3]
        atlas[code - 32] = arr
    atlas = np.minimum(255, atlas.astype(np.uint16) * int(GLYPH_GAIN * 256) // 256).astype(np.uint8)
    _ATLAS_CACHE[key] = atlas
    return atlas


class HDPlayer:
    """Bir HD varlığın kare çözme + çizim durumu."""

    def __init__(self, asset: AnimationAsset) -> None:
        path = asset.hd_path()
        if path is None:
            raise ValueError("HD varlığın hd_file yolu yok")
        self.asset = asset
        self.reader = HDReader(path)
        self.decim = 1
        self.cw = 5
        self.ch = 10
        self.opacity = 0.94
        self.solid_bg = asset.bg_mode in ("solid", "tinted")
        self.tinted_bg = asset.bg_mode == "tinted"  # hücre zemini, hücre renginin koyu tonu (resim gibi okunur)
        self.dcols = self.reader.cols
        self.drows = self.reader.rows
        self._buf: Optional[np.ndarray] = None
        self._img: Optional[QImage] = None
        self._prev_chars: Optional[np.ndarray] = None
        self._prev_colors: Optional[np.ndarray] = None
        self._prev_levels: Optional[np.ndarray] = None
        self._levels: Optional[np.ndarray] = None
        self._light: Optional[np.ndarray] = None
        self._fade = 0.2
        self._atlas: Optional[np.ndarray] = None
        self._atlas_op: Optional[np.ndarray] = None  # opaklık uygulanmış atlas (maskesiz hızlı yol)
        self._full_dirty = True
        self._last_idx = -1
        self.last_dirty: Optional[Tuple[int, int, int, int]] = None
        self._blocks: Optional[np.ndarray] = None
        self._slot: Dict[int, int] = {}
        self._n_blocks = 0
        self._cache_bits = 5

    # --- yapılandırma
    def configure(self, cell_w: int, cell_h: int, decim: int, opacity: float) -> None:
        decim = max(1, int(decim))
        cw, ch = max(1, int(cell_w)) * decim, max(1, int(cell_h)) * decim
        dcols, drows = max(1, self.reader.cols // decim), max(1, self.reader.rows // decim)
        op = max(0.0, min(1.0, opacity))
        if (cw, ch, decim, dcols, drows) != (self.cw, self.ch, self.decim, self.dcols, self.drows) or self._buf is None:
            self.cw, self.ch, self.decim, self.dcols, self.drows = cw, ch, decim, dcols, drows
            self._atlas = build_atlas(cw, ch)
            self._buf = np.zeros((drows * ch, dcols * cw, 4), np.uint8)
            self._img = QImage(self._buf.data, dcols * cw, drows * ch, dcols * cw * 4, QImage.Format.Format_ARGB32_Premultiplied)
            self._full_dirty = True
            self._levels = self._light = self._prev_levels = None
        if abs(op - self.opacity) > 1e-4:
            self.opacity = op
            self._full_dirty = True
        if self._atlas_op is None or self._full_dirty:
            assert self._atlas is not None
            self._atlas_op = ((self._atlas.astype(np.uint16) * int(self.opacity * 256)) >> 8).astype(np.uint8)
            self._blocks = None  # (karakter, renk) blok önbelleği geçersiz
            self._slot = {}
            self._n_blocks = 0

    @property
    def pixel_size(self) -> Tuple[int, int]:
        return self.dcols * self.cw, self.drows * self.ch

    @property
    def image(self) -> Optional[QImage]:
        return self._img

    def set_mask(self, levels: Optional[np.ndarray], light: Optional[np.ndarray], fade: float) -> None:
        """Akıllı okunabilirlik maskesi (drows × dcols). None → maske yok."""
        if levels is not None and levels.shape != (self.drows, self.dcols):
            levels = None
        if levels is None and self._levels is None:
            return
        self._levels, self._light = levels, light
        if abs(fade - self._fade) > 1e-6:
            self._fade = fade
            self._full_dirty = True

    def invalidate(self) -> None:
        self._full_dirty = True

    # --- kare çözme / birleştirme
    def _decimated(self, idx: int) -> Tuple[np.ndarray, np.ndarray]:
        ch, co = self.reader.frame(idx)
        d = self.decim
        if d == 1:
            return ch, co
        rows, cols = self.drows * d, self.dcols * d
        ch = ch[:rows, :cols][d // 2 :: d, d // 2 :: d][: self.drows, : self.dcols]
        c = co[:rows, :cols].astype(np.uint16)
        acc = np.zeros((self.drows, self.dcols, 3), np.uint16)
        for dy in range(d):
            for dx in range(d):
                acc += c[dy::d, dx::d][: self.drows, : self.dcols]
        return ch, (acc // (d * d)).astype(np.uint8)

    def render(self, idx: int) -> bool:
        """Kareyi tampona yazar. Hiçbir hücre değişmediyse False döner (çizim gerekmez)."""
        if self._buf is None or self._atlas is None:
            return False
        chars, colors = self._decimated(idx)
        levels = self._levels
        if self._full_dirty or self._prev_chars is None:
            if self.solid_bg:
                self._buf[...] = (int(14 * self.opacity), int(12 * self.opacity), int(10 * self.opacity), int(255 * self.opacity))
                changed = np.ones(chars.shape, bool)
            else:
                self._buf[...] = 0
                changed = chars != 32  # tampon sıfırlandı: yalnızca dolu hücreleri yazmak yeter
        else:
            changed = chars != self._prev_chars
            changed |= (colors != self._prev_colors).any(axis=-1)
            if levels is not None or self._prev_levels is not None:
                a = levels if levels is not None else np.zeros_like(self._prev_levels)
                b = self._prev_levels if self._prev_levels is not None else np.zeros_like(a)
                changed |= a != b
        rr, cc = np.nonzero(changed)
        self._prev_chars, self._prev_colors = chars.copy(), colors.copy()
        self._prev_levels = None if levels is None else levels.copy()
        self._full_dirty = False
        self._last_idx = idx
        if rr.size == 0:
            self.last_dirty = None
            return False
        self.last_dirty = (int(rr.min()), int(cc.min()), int(rr.max()), int(cc.max()))

        idxs = chars[rr, cc].astype(np.intp) - 32
        col = colors[rr, cc]  # (k, 3) uint8 RGB
        view = self._buf.reshape(self.drows, self.ch, self.dcols, self.cw, 4).transpose(0, 2, 1, 3, 4)
        use_cache = levels is None and not self.solid_bg and rr.size > 0
        cbits = 5
        if use_cache:
            # Uyarlamalı renk kuantalama: 5 bit/kanal fazla çeşit üretiyorsa (dönen gökkuşağı) 4 bit dene;
            # o da sığmazsa doğrudan birleştir. Kararlılık için bir kez 4 bite düşen oyuncu 4 bitte kalır.
            for bits in ((4,) if self._cache_bits == 4 else (5, 4)):
                sh = 8 - bits
                q0 = (col >> sh).astype(np.uint32)
                k0 = (idxs.astype(np.uint32) << 15) | (q0[:, 0] << 10) | (q0[:, 1] << 5) | q0[:, 2]
                if np.unique(k0).size <= BLOCK_CACHE // 2:
                    cbits = bits
                    break
            else:
                use_cache = False
            if use_cache and cbits != self._cache_bits:
                self._cache_bits = cbits
                self._blocks = None  # anahtar anlamı değişti
        sh = 8 - cbits
        if use_cache:
            # En hızlı yol: (karakter, 5-bit renk) → önceden birleştirilmiş BGRA blok; yalnızca yeni anahtarlar hesaplanır.
            # Dönen sahnelerde hemen her hücre değişir ama (karakter, renk) çiftleri çok tekrar eder.
            npx = self.ch * self.cw
            q = (col >> sh).astype(np.uint32)
            key = (idxs.astype(np.uint32) << 15) | (q[:, 0] << 10) | (q[:, 1] << 5) | q[:, 2]
            uk, inv = np.unique(key, return_inverse=True)
            if getattr(self, "_blocks", None) is None or self._blocks.shape[1] != npx:
                self._blocks = np.zeros((BLOCK_CACHE, npx, 4), np.uint8)
                self._slot = {}
                self._n_blocks = 0
            ukl = uk.tolist()
            slots = [self._slot.get(k_, -1) for k_ in ukl]
            miss = [i for i, s_ in enumerate(slots) if s_ < 0]
            if miss:
                if self._n_blocks + len(miss) > BLOCK_CACHE:
                    self._slot = {}
                    self._n_blocks = 0
                    miss = list(range(len(ukl)))
                mk = uk[miss]
                m_idx = (mk >> 15).astype(np.intp)
                m_col = np.stack([((mk >> s_) & 31) << sh | (1 << (sh - 1)) for s_ in (10, 5, 0)], axis=1).astype(np.uint16)
                a8m = self._atlas_op[m_idx].reshape(len(miss), npx)
                a16m = a8m.astype(np.uint16)
                blk = np.empty((len(miss), npx, 4), np.uint8)
                tmpm = np.empty(a16m.shape, np.uint16)
                for dst, src in ((0, 2), (1, 1), (2, 0)):
                    np.multiply(a16m, m_col[:, src : src + 1], out=tmpm)
                    tmpm >>= 8
                    blk[:, :, dst] = tmpm
                blk[:, :, 3] = a8m
                start = self._n_blocks
                self._blocks[start : start + len(miss)] = blk
                for j, i in enumerate(miss):
                    self._slot[ukl[i]] = start + j
                    slots[i] = start + j
                self._n_blocks += len(miss)
            sl = np.asarray(slots, np.intp)[inv.reshape(-1)]
            view[rr, cc] = self._blocks[sl].reshape(rr.size, self.ch, self.cw, 4)
            return True
        if levels is None and not self.solid_bg:
            # Doğrudan yol: alfa = opaklık uygulanmış atlas; kanal başına bitişik çarpma
            a8 = self._atlas_op[idxs].reshape(rr.size, self.ch * self.cw)  # (k, piksel)
            a16 = a8.astype(np.uint16)
            out = np.empty((rr.size, self.ch * self.cw, 4), np.uint8)
            tmp = np.empty(a16.shape, np.uint16)
            for dst, src in ((0, 2), (1, 1), (2, 0)):  # premultiplied BGRA: kanal başına bitişik çarpma + kaydırma
                np.multiply(a16, col[:, src : src + 1].astype(np.uint16), out=tmp)
                tmp >>= 8
                out[:, :, dst] = tmp
            out[:, :, 3] = a8
            out = out.reshape(rr.size, self.ch, self.cw, 4)
        else:
            glyph = self._atlas[idxs].astype(np.uint16)  # (k, ch, cw)
            colw = col.astype(np.int32)
            fac = np.full(rr.size, int(self.opacity * 256), np.int32)
            if levels is not None:
                lv = levels[rr, cc].astype(np.int32)
                lt = self._light[rr, cc] if self._light is not None else np.zeros(rr.size, bool)
                fade = self._fade
                fac = (fac * (1.0 - (lv / 3.0) * (1.0 - fade))).astype(np.int32)
                contrast = np.where(lt[:, None], 22, 255).astype(np.int32)  # açık arka plan → koyu yazı rengi
                m = (0.22 * lv)[:, None]
                colw = (colw + (contrast - colw) * m).astype(np.int32)
            a = (glyph * fac[:, None, None].astype(np.uint16)) >> 8  # (k, ch, cw) 0..255
            rgb = (colw[:, None, None, :].astype(np.uint16) * a[..., None]) >> 8  # premultiplied (R,G,B)
            if self.solid_bg:  # "solid" zemin: hücrenin altına opak koyu zemin birleştir
                a_bg = int(255 * self.opacity)
                inv = (255 - a.astype(np.int32))[..., None]
                if self.tinted_bg:
                    bg = (14 + colw[:, None, None, :] * 0.24).astype(np.int32) * a_bg // 255
                else:
                    bg = np.array([14, 12, 10], np.int32) * a_bg // 255
                rgb = (rgb.astype(np.int32) + bg * inv // 255).astype(np.uint16)
                a = (a.astype(np.int32) + a_bg * inv[..., 0] // 255).astype(np.uint16)
            out = np.empty((rr.size, self.ch, self.cw, 4), np.uint8)
            out[..., 0] = rgb[..., 2]
            out[..., 1] = rgb[..., 1]
            out[..., 2] = rgb[..., 0]
            out[..., 3] = a
        view[rr, cc] = out
        return True
