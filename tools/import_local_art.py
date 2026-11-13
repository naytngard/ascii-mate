"""Kişisel/yerel resim → ASCII Mate HD varlığı (GİT DIŞINDA: %APPDATA%\\ASCII_Mate\\community).

Telif notu: başkalarının eserlerinden (tablolar, illüstrasyonlar, film kareleri) üretilen çıktılar yalnızca kişisel
kullanım içindir. Bu araç varsayılan olarak repoya YAZMAZ; çıktı klasörü depo içindeyse durur (--allow-repo yoksa).

Örnekler:
    python tools/import_local_art.py "C:\\Resimler\\sovalye.jpg" --preset high --bg auto --anim wind
    python tools/import_local_art.py foto.jpg --cols 180 --crop 0.1,0,0.8,1 --bg solid --anim pulse --gamma 0.8
    python tools/import_local_art.py klasor/*.jpg --preset medium       # birden çok resim

Arka plan (--bg):
    auto      : kenarlardan başlayan renk/parlaklık benzerliğiyle arka planı ayırır (gökyüzü, sepya kağıt) → saydam
    threshold : yalnızca koyu pikseller saydam (--bg-threshold)
    solid     : hiçbir şey silinmez; widget koyu bir panel üstünde çizer (bg_mode=solid)
Hareket (--anim): none | wind (alt bölgede rüzgâr: yalnızca alt satırlar kayar) | embers (yükselen kıvılcımlar)
                  | pulse (gün batımı gibi yavaş renk nabzı) — virgülle birleştirilebilir: wind,embers
"""

from __future__ import annotations

import argparse
import math
import os
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "tools"))

import numpy as np  # noqa: E402

import hd_convert as hc  # noqa: E402

PRESETS = {"low": (110, 8.0), "medium": (160, 10.0), "high": (210, 10.0)}


def default_out_dir() -> Path:
    from src.core.app_logging import app_data_dir

    return app_data_dir() / "community"


def is_inside_repo(p: Path) -> bool:
    try:
        p.resolve().relative_to(BASE.resolve())
        return True
    except ValueError:
        return False


def parse_crop(spec: Optional[str], w: int, h: int) -> Tuple[int, int, int, int]:
    """'x,y,w,h' — 0..1 arası kesirler ya da piksel."""
    if not spec:
        return 0, 0, w, h
    v = [float(x) for x in spec.split(",")]
    if len(v) != 4:
        raise SystemExit("--crop x,y,w,h biçiminde olmalı")
    if all(0.0 <= x <= 1.0 for x in v):
        v = [v[0] * w, v[1] * h, v[2] * w, v[3] * h]
    x, y, cw, ch = (int(round(a)) for a in v)
    x, y = max(0, x), max(0, y)
    return x, y, max(1, min(cw, w - x)), max(1, min(ch, h - y))


def edge_background_mask(rgb: np.ndarray, tol: float = 0.12, max_iter: int = 2000, side: str = "top") -> np.ndarray:
    """Kenarlardan taşan arka plan maskesi (True = arka plan). Kenar piksellerinin rengine yakın ve kenara
    bağlantılı bölgeler arka plan sayılır (gökyüzü, düz kağıt). Aşağı örneklenmiş ızgarada çalışır."""
    h, w = rgb.shape[:2]
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
    # tohumlar: "top" → üst kenar + yan kenarların üst yarısı (gökyüzü); "all" → tüm kenarlar (düz kağıt/stüdyo)
    if side == "top":
        border = np.concatenate([rgb[0], rgb[: h // 2, 0], rgb[: h // 2, -1]])
    else:
        border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    # kenar renkleri birkaç kümeye ayrılır (ör. gökyüzü üst, toprak alt) → her piksel en yakın kümeye uzaklık
    seeds = border[np.linspace(0, len(border) - 1, 64).astype(int)]
    d = np.min(np.linalg.norm(rgb[:, :, None, :] - seeds[None, None, :, :], axis=-1), axis=-1)
    similar = d < tol
    # düz bölge koşulu: yerel kenar enerjisi düşük olmalı (nesne dokusu taşmasın)
    gy, gx = np.gradient(lum)
    flat = np.hypot(gx, gy) < 0.08
    allowed = similar & flat
    mask = np.zeros((h, w), bool)
    mask[0, :] = allowed[0, :]
    lim = h // 2 if side == "top" else h
    if side != "top":
        mask[-1, :] = allowed[-1, :]
    mask[:lim, 0] |= allowed[:lim, 0]
    mask[:lim, -1] |= allowed[:lim, -1]
    for _ in range(max_iter):
        grown = mask.copy()
        grown[1:, :] |= mask[:-1, :]
        grown[:-1, :] |= mask[1:, :]
        grown[:, 1:] |= mask[:, :-1]
        grown[:, :-1] |= mask[:, 1:]
        grown &= allowed
        if (grown == mask).all():
            break
        mask = grown
    return mask


def stretch(arr: np.ndarray, black: float, white: float, saturation: float) -> np.ndarray:
    """Siyah/beyaz noktası (yüzdelik) ile kontrast germe + doygunluk."""
    a = arr[..., 3] > 0.5
    rgb = arr[..., :3]
    lum = rgb @ np.array([0.2126, 0.7152, 0.0722])
    vals = lum[a] if a.any() else lum.ravel()
    lo, hi = np.percentile(vals, black), np.percentile(vals, white)
    rgb = np.clip((rgb - lo) / max(hi - lo, 1e-3), 0, 1)
    g = (rgb @ np.array([0.2126, 0.7152, 0.0722]))[..., None]
    rgb = np.clip(g + (rgb - g) * saturation, 0, 1)
    out = arr.copy()
    out[..., :3] = rgb
    return out


# --------------------------------------------------------------------------- ucuz canlılık (hücre uzayında)

def animate(chars: np.ndarray, colors: np.ndarray, kinds: Sequence[str], n: int, region: float = 0.30,
            seed: int = 3) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    """Durağan kareden n karelik döngü üretir; yalnızca etkilenen hücreler değişir (çizici değişen hücreyi yazar)."""
    rows, cols = chars.shape
    rng = np.random.default_rng(seed)
    embers = [(rng.uniform(0, cols), rng.uniform(0, rows), rng.uniform(0.5, 1.5)) for _ in range(max(6, cols // 12))]
    out_c, out_k = [], []
    r0 = int(rows * (1.0 - region))
    for i in range(n):
        ph = i / n
        ch = chars.copy()
        co = colors.copy()
        if "wind" in kinds:
            for r in range(r0, rows):
                depth = (r - r0 + 1) / max(1, rows - r0)
                shift = int(round(1.2 * depth * math.sin(ph * 2 * math.pi + r * 0.45)))
                if shift:
                    ch[r] = np.roll(chars[r], shift)
                    co[r] = np.roll(colors[r], shift, axis=0)
        if "pulse" in kinds:
            k = 0.88 + 0.12 * math.sin(ph * 2 * math.pi)
            warm = np.array([1.0, 0.92 + 0.08 * k, 0.85 + 0.15 * k])
            co = np.clip(co.astype(np.float32) * warm * k, 0, 255).astype(np.uint8)
        if "embers" in kinds:
            for (x, y, sp) in embers:
                yy = int((y - ph * rows * 0.6 * sp) % rows)
                xx = int(x + 1.5 * math.sin(ph * 6.28 * 2 + y)) % cols
                ch[yy, xx] = ord("*" if (i + int(x)) % 3 == 0 else ".")
                co[yy, xx] = (255, 170 + int(60 * math.sin(ph * 6.28 + x)), 60)
        out_c.append(ch)
        out_k.append(co)
    return out_c, out_k


# --------------------------------------------------------------------------- ana akış

def convert_one(path: Path, args, ramp) -> Path:
    from PyQt6.QtGui import QImage

    from src.core.converter import slugify

    hc.ensure_qt()
    img = QImage(str(path))
    if img.isNull():
        raise SystemExit(f"Görüntü okunamadı: {path}")
    arr = hc.qimage_to_rgba(img)
    x, y, w, h = parse_crop(args.crop, arr.shape[1], arr.shape[0])
    arr = arr[y : y + h, x : x + w].copy()
    cols = args.cols or PRESETS[args.preset][0]
    fps = args.fps or PRESETS[args.preset][1]
    if args.bg == "auto":
        small_w = min(arr.shape[1], 360)
        small_h = max(1, int(arr.shape[0] * small_w / arr.shape[1]))
        small = hc.resize_rgba(arr, small_w, small_h)
        m = edge_background_mask(small[..., :3], tol=args.bg_tol, side=args.bg_side)
        # maskeyi tam boyuta (en yakın komşu) taşı
        yi = (np.arange(arr.shape[0]) * small_h // arr.shape[0]).clip(0, small_h - 1)
        xi = (np.arange(arr.shape[1]) * small_w // arr.shape[1]).clip(0, small_w - 1)
        arr[..., 3] = np.where(m[np.ix_(yi, xi)], 0.0, arr[..., 3])
    arr = stretch(arr, args.black_point, args.white_point, args.saturation)
    rows = hc.grid_rows(arr.shape[1], arr.shape[0], cols)
    bg_thr = args.bg_threshold if args.bg == "threshold" else 0.0  # auto: arka planı maske belirler, koyu özne silinmez
    ch, co = hc.convert_rgba(arr, cols, rows, ramp, gamma=args.gamma, edge_boost=args.edges, bg_threshold=bg_thr,
                             color_lift=args.color_lift, invert=args.invert)
    kinds = [k for k in args.anim.split(",") if k and k != "none"]
    if kinds:
        chars, colors = animate(ch, co, kinds, args.frames, region=args.wind_region)
    else:
        chars, colors = [ch], [co]
    out = Path(args.out) if args.out else default_out_dir()
    if is_inside_repo(out) and not args.allow_repo:
        raise SystemExit(f"Çıktı klasörü depo içinde ({out}). Başkalarının eserlerinden türetilen dosyalar repoya "
                         "girmemeli; --out ile depo dışını seçin (ya da kendi eserinizse --allow-repo).")
    asset_id = args.id or ("local_" + slugify(path.stem))
    jp, hp = hc.write_asset(out, asset_id, args.name or path.stem, "Topluluk / Özel Eklenenler", chars, colors, fps,
                            bg_mode="solid" if args.bg == "solid" else "transparent", tags=["yerel", "kişisel"],
                            author="Yerel (kişisel kullanım)", description=f"Kaynak: {path.name} (yerel, repoya girmez)")
    if not args.no_preview:
        sys.path.insert(0, str(BASE / "tools" / "scenes"))
        import common

        common.preview_png(chars[0], colors[0], out / f"{asset_id}_preview.png", cw=6, ch=12)
    print(f"[OK] {jp}  ({cols}x{rows}, {len(chars)} kare, {hp.stat().st_size / 1024:.0f} KB)")
    return jp


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("inputs", nargs="+")
    ap.add_argument("--out", default=None, help="varsayılan: %%APPDATA%%\\ASCII_Mate\\community (git dışı)")
    ap.add_argument("--allow-repo", action="store_true", help="depo içine yazmaya izin ver (yalnızca kendi eserleriniz için)")
    ap.add_argument("--id", default=None)
    ap.add_argument("--name", default=None)
    ap.add_argument("--preset", choices=sorted(PRESETS), default="medium", help="low=110, medium=160, high=210 sütun")
    ap.add_argument("--cols", type=int, default=None)
    ap.add_argument("--gamma", type=float, default=0.9)
    ap.add_argument("--edges", type=float, default=0.35, help="Sobel kenar karakteri gücü (0 = kapalı)")
    ap.add_argument("--bg", choices=("auto", "threshold", "solid"), default="auto")
    ap.add_argument("--bg-tol", type=float, default=0.12, help="auto: kenar rengine benzerlik toleransı")
    ap.add_argument("--bg-side", choices=("top", "all"), default="top", help="auto: tohum kenarları (top = gökyüzü)")
    ap.add_argument("--bg-threshold", type=float, default=0.05)
    ap.add_argument("--black-point", type=float, default=2.0)
    ap.add_argument("--white-point", type=float, default=99.0)
    ap.add_argument("--saturation", type=float, default=1.15)
    ap.add_argument("--color-lift", type=float, default=0.35)
    ap.add_argument("--crop", default=None, help="x,y,w,h (0..1 kesir ya da piksel)")
    ap.add_argument("--invert", action="store_true", help="açık zemin önünde koyu özne: yoğunluğu ters çevir")
    ap.add_argument("--anim", default="none", help="none | wind | embers | pulse (virgülle birleştirilebilir)")
    ap.add_argument("--wind-region", type=float, default=0.30, help="rüzgârın etkilediği alt bölge oranı")
    ap.add_argument("--frames", type=int, default=24)
    ap.add_argument("--fps", type=float, default=None)
    ap.add_argument("--no-preview", action="store_true")
    args = ap.parse_args(argv)
    ramp = hc.build_ramp("auto")
    for inp in args.inputs:
        convert_one(Path(inp), args, ramp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
