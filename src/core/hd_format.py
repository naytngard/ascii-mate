"""HD (schema 3.0) varlık deposu: `.ascii.hd` ikili dosyası (kare başına zlib) + küçük JSON üst verisi.

Dosya düzeni (little-endian):
    b"AHD1" | u32 cols | u32 rows | u32 nframes | u32 size[nframes] | blob[nframes]
Her blob zlib ile sıkıştırılmış: chars (rows*cols bayt, ASCII 32..126) + colors (rows*cols*3 bayt, RGB, düzlemsel).
Okuyucu tembeldir: açılışta yalnızca başlık+dizin okunur; kareler istendikçe çözülür ve en fazla `CACHE_FRAMES` kare bellekte tutulur.
"""

from __future__ import annotations

import struct
import zlib
from collections import OrderedDict
from pathlib import Path
from typing import List, Sequence, Tuple

import numpy as np

MAGIC = b"AHD1"
CACHE_FRAMES = 3
MAX_CELLS = 600 * 300  # sağlamlık: bozuk dosyada dev bellek ayrılmasın


class HDFormatError(ValueError):
    pass


def write_hd(path: Path | str, chars: Sequence[np.ndarray], colors: Sequence[np.ndarray], level: int = 9) -> None:
    """chars[i]: (rows, cols) uint8 ASCII kodu; colors[i]: (rows, cols, 3) uint8 RGB."""
    if not chars or len(chars) != len(colors):
        raise HDFormatError("kare sayısı tutarsız/boş")
    rows, cols = chars[0].shape
    blobs: List[bytes] = []
    for ch, co in zip(chars, colors):
        if ch.shape != (rows, cols) or co.shape != (rows, cols, 3):
            raise HDFormatError("kare boyutları tutarsız")
        if ch.size and (ch.min() < 32 or ch.max() > 126):
            raise HDFormatError("yalnızca ASCII 32..126 karakter yazılabilir")
        planar = np.ascontiguousarray(co.transpose(2, 0, 1))  # R düzlemi, G düzlemi, B düzlemi: daha iyi sıkışır
        blobs.append(zlib.compress(ch.astype(np.uint8).tobytes() + planar.astype(np.uint8).tobytes(), level))
    head = MAGIC + struct.pack("<III", cols, rows, len(blobs)) + struct.pack(f"<{len(blobs)}I", *(len(b) for b in blobs))
    Path(path).write_bytes(head + b"".join(blobs))


class HDReader:
    """Tembel okuyucu. `frame(i)` → (chars (rows,cols) uint8, colors (rows,cols,3) uint8)."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        with self.path.open("rb") as f:
            head = f.read(16)
            if len(head) < 16 or head[:4] != MAGIC:
                raise HDFormatError(f"{self.path.name}: geçersiz HD dosyası")
            self.cols, self.rows, self.frame_count = struct.unpack("<III", head[4:16])
            if not (0 < self.cols * self.rows <= MAX_CELLS) or not (0 < self.frame_count <= 5000):
                raise HDFormatError(f"{self.path.name}: geçersiz boyut/kare sayısı")
            raw = f.read(4 * self.frame_count)
            if len(raw) != 4 * self.frame_count:
                raise HDFormatError(f"{self.path.name}: kesik dizin")
            self.sizes = struct.unpack(f"<{self.frame_count}I", raw)
        self._base = 16 + 4 * self.frame_count
        self.offsets = np.concatenate(([0], np.cumsum(self.sizes))).tolist()
        self._cache: "OrderedDict[int, Tuple[np.ndarray, np.ndarray]]" = OrderedDict()

    def frame(self, idx: int) -> Tuple[np.ndarray, np.ndarray]:
        idx %= self.frame_count
        hit = self._cache.get(idx)
        if hit is not None:
            self._cache.move_to_end(idx)
            return hit
        with self.path.open("rb") as f:
            f.seek(self._base + self.offsets[idx])
            blob = f.read(self.sizes[idx])
        n = self.rows * self.cols
        try:
            data = zlib.decompress(blob)
        except zlib.error as exc:
            raise HDFormatError(f"{self.path.name}: kare {idx} bozuk ({exc})") from exc
        if len(data) != n * 4:
            raise HDFormatError(f"{self.path.name}: kare {idx} boyutu beklenenden farklı")
        ch = np.frombuffer(data, np.uint8, n).reshape(self.rows, self.cols)
        co = np.frombuffer(data, np.uint8, n * 3, n).reshape(3, self.rows, self.cols).transpose(1, 2, 0)
        out = (ch, co)
        self._cache[idx] = out
        while len(self._cache) > CACHE_FRAMES:
            self._cache.popitem(last=False)
        return out

    def compressed_bytes(self) -> int:
        return int(sum(self.sizes))

    def cached_frames(self) -> int:
        return len(self._cache)

    def preview(self, idx: int, out_cols: int, out_rows: int) -> Tuple[List[str], List[List[Tuple[int, int, int]]]]:
        """Terminal önizlemesi için en yakın komşu ile küçültülmüş satırlar ve renkler."""
        ch, co = self.frame(idx)
        ri = np.linspace(0, self.rows - 1, max(1, min(out_rows, self.rows))).astype(int)
        ci = np.linspace(0, self.cols - 1, max(1, min(out_cols, self.cols))).astype(int)
        sub_c = ch[np.ix_(ri, ci)]
        sub_k = co[np.ix_(ri, ci)]
        lines = ["".join(map(chr, row)) for row in sub_c.tolist()]
        colors = [[tuple(px) for px in row] for row in sub_k.tolist()]
        return lines, colors  # type: ignore[return-value]
