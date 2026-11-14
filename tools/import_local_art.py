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
ap_defaults: dict = {}


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


def clahe(lum: np.ndarray, tiles: int = 8, clip: float = 2.5) -> np.ndarray:
    """Sınırlı uyarlamalı histogram eşitleme (CLAHE benzeri, NumPy). lum 0..1 → 0..1.
    Karolar arası geçiş bilineer enterpolasyonla yumuşatılır (karo sınırı görünmez)."""
    h, w = lum.shape
    v = np.clip((lum * 255).astype(np.int32), 0, 255)
    ty = np.linspace(0, h, tiles + 1).astype(int)
    tx = np.linspace(0, w, tiles + 1).astype(int)
    maps = np.zeros((tiles, tiles, 256), np.float32)
    for i in range(tiles):
        for j in range(tiles):
            blk = v[ty[i] : ty[i + 1], tx[j] : tx[j + 1]].ravel()
            hist = np.bincount(blk, minlength=256).astype(np.float32)
            limit = clip * max(1.0, blk.size / 256.0)
            excess = np.maximum(hist - limit, 0).sum()
            hist = np.minimum(hist, limit) + excess / 256.0
            cdf = hist.cumsum()
            maps[i, j] = (cdf - cdf[0]) / max(cdf[-1] - cdf[0], 1e-6)
    cy = (np.arange(h) + 0.5) / h * tiles - 0.5
    cx = (np.arange(w) + 0.5) / w * tiles - 0.5
    y0 = np.clip(np.floor(cy).astype(int), 0, tiles - 1)
    x0 = np.clip(np.floor(cx).astype(int), 0, tiles - 1)
    y1 = np.clip(y0 + 1, 0, tiles - 1)
    x1 = np.clip(x0 + 1, 0, tiles - 1)
    fy = np.clip(cy - np.floor(cy), 0, 1)[:, None]
    fx = np.clip(cx - np.floor(cx), 0, 1)[None, :]
    Y0, X0, Y1, X1 = y0[:, None], x0[None, :], y1[:, None], x1[None, :]
    a = maps[Y0, X0, v]
    b = maps[Y0, X1, v]
    c = maps[Y1, X0, v]
    d = maps[Y1, X1, v]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def subject_weight(rgb: np.ndarray, mode: str, bg_mask: Optional[np.ndarray] = None) -> np.ndarray:
    """Özne ağırlığı 0..1 (1 = özne). center: merkez öncelikli elips; edge: kenar renklerinden farklılık;
    auto: ikisinin çarpımı (merkezde ve zeminden farklı olan = özne)."""
    h, w = rgb.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    dy = (yy / max(h - 1, 1) - 0.52) / 0.62
    dx = (xx / max(w - 1, 1) - 0.5) / 0.55
    center = np.clip(1.25 - np.sqrt(dx * dx + dy * dy), 0, 1)
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    seeds = border[np.linspace(0, len(border) - 1, 48).astype(int)]
    dist = np.min(np.linalg.norm(rgb[:, :, None, :] - seeds[None, None, :, :], axis=-1), axis=-1)
    diff = np.clip(dist / max(np.percentile(dist, 90), 1e-3), 0, 1)
    if bg_mask is not None:
        diff = np.where(bg_mask, 0.0, np.maximum(diff, 0.5))
    if mode == "center":
        wgt = center
    elif mode == "edge":
        wgt = diff
    else:
        wgt = np.clip(diff * (0.35 + 0.65 * center) * 1.6, 0, 1)
    # yumuşat (kutu bulanıklığı ×2): maske sınırı titremesin/delik delik olmasın
    for _ in range(2):
        p = np.pad(wgt, 3, mode="edge")
        wgt = sum(p[i : i + h, j : j + w] for i in range(7) for j in range(7)) / 49.0
    return wgt


LOOKS = {
    # gamma (>1 parlatır), clahe kırpma, doygunluk, orta ton kaldırma, arka plan karartma
    "vivid": dict(gamma=1.45, clahe=2.8, saturation=1.25, mid=0.80, bg_dim=0.30),
    "soft": dict(gamma=1.20, clahe=1.8, saturation=1.10, mid=0.90, bg_dim=0.45),
    "photo": dict(gamma=1.30, clahe=2.2, saturation=1.05, mid=0.85, bg_dim=0.35),
}


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
    look = LOOKS.get(args.look) if args.look else None
    if look:
        for k_, v_ in look.items():
            if getattr(args, k_.replace("-", "_"), None) in (None, ap_defaults.get(k_)):
                setattr(args, k_, v_)
    arr = stretch(arr, args.black_point, args.white_point, args.saturation)
    if args.clahe and args.clahe > 0:
        lum0 = arr[..., :3] @ np.array([0.2126, 0.7152, 0.0722])
        lum1 = clahe(lum0, tiles=8, clip=args.clahe)
        lum1 = 0.65 * lum1 + 0.35 * lum0  # yerel kontrast + genel ton dengesi
        if args.mid and args.mid != 1.0:
            lum1 = np.clip(lum1, 0, 1) ** args.mid  # orta tonları parlat
        ratio = (lum1 + 0.02) / (lum0 + 0.02)
        arr[..., :3] = np.clip(arr[..., :3] * ratio[..., None], 0, 1)
    if args.subject_mask != "none":
        # özne net ve parlak kalsın, zemin koyu panelde soluk dursun (silinmez: sahne bütünlüğü korunur)
        wgt = subject_weight(arr[..., :3], args.subject_mask)
        dim = args.bg_dim + (1.0 - args.bg_dim) * wgt
        arr[..., :3] = arr[..., :3] * dim[..., None]
    rows = hc.grid_rows(arr.shape[1], arr.shape[0], cols)
    bg_thr = args.bg_threshold if args.bg == "threshold" else 0.0
    if args.bg == "tinted":
        ch_space = None  # tinted: boş hücre bırakma, her hücre en az nokta  # auto: arka planı maske belirler, koyu özne silinmez
    ch, co = hc.convert_rgba(arr, cols, rows, ramp, gamma=args.gamma, edge_boost=args.edges, bg_threshold=bg_thr,
                             color_lift=args.color_lift, invert=args.invert, edge_pct=args.edge_pct,
                             min_brightness=args.min_brightness)
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
                            bg_mode=args.bg if args.bg in ("solid", "tinted") else "transparent", tags=["yerel", "kişisel"],
                            author="Yerel (kişisel kullanım)", description=f"Kaynak: {path.name} (yerel, repoya girmez)")
    if not args.no_preview:
        sys.path.insert(0, str(BASE / "tools" / "scenes"))
        import common

        common.preview_png(chars[0], colors[0], out / f"{asset_id}_preview.png", cw=6, ch=12,
                           tint=0.24 if args.bg == "tinted" else 0.0)
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
    ap.add_argument("--gamma", type=float, default=1.25, help=">1 orta tonları ve gölgeleri parlatır (yoğun karakter)")
    ap.add_argument("--edges", type=float, default=0.35, help="Sobel kenar karakteri gücü (0 = kapalı)")
    ap.add_argument("--bg", choices=("auto", "threshold", "solid", "tinted"), default="auto",
                    help="tinted: hücre zemini rengin koyu tonu (resim gibi okunur, en parlak sonuç)")
    ap.add_argument("--bg-tol", type=float, default=0.12, help="auto: kenar rengine benzerlik toleransı")
    ap.add_argument("--bg-side", choices=("top", "all"), default="top", help="auto: tohum kenarları (top = gökyüzü)")
    ap.add_argument("--bg-threshold", type=float, default=0.05)
    ap.add_argument("--black-point", type=float, default=2.0)
    ap.add_argument("--white-point", type=float, default=99.0)
    ap.add_argument("--saturation", type=float, default=1.15)
    ap.add_argument("--color-lift", type=float, default=0.35)
    ap.add_argument("--crop", default=None, help="x,y,w,h (0..1 kesir ya da piksel)")
    ap.add_argument("--invert", action="store_true", help="açık zemin önünde koyu özne: yoğunluğu ters çevir")
    ap.add_argument("--min-brightness", type=float, default=0.62,
                    help="karakter renklerinin en düşük parlaklığı (koyu zeminde görünürlük)")
    ap.add_argument("--look", choices=sorted(LOOKS), default=None, help="görünüm önayarı: vivid | soft | photo")
    ap.add_argument("--clahe", type=float, default=0.0, help="yerel kontrast eşitleme gücü (0 = kapalı, ~2-3 önerilir)")
    ap.add_argument("--mid", type=float, default=1.0, help="orta ton eğrisi (<1 parlatır)")
    ap.add_argument("--subject-mask", choices=("none", "auto", "center", "edge"), default="none",
                    help="özneyi öne çıkar: zemini --bg-dim oranında karart (silmez)")
    ap.add_argument("--bg-dim", type=float, default=0.35, help="özne maskesinde zemin parlaklık çarpanı")
    ap.add_argument("--edge-pct", type=float, default=None, help="kenar karakteri yalnızca bu yüzdelik üstündeki kenarlarda (ör. 92)")
    ap.add_argument("--anim", default="none", help="none | wind | embers | pulse (virgülle birleştirilebilir)")
    ap.add_argument("--wind-region", type=float, default=0.30, help="rüzgârın etkilediği alt bölge oranı")
    ap.add_argument("--frames", type=int, default=24)
    ap.add_argument("--fps", type=float, default=None)
    ap.add_argument("--no-preview", action="store_true")
    args = ap.parse_args(argv)
    global ap_defaults
    ap_defaults = {a.dest: a.default for a in ap._actions}
    ramp = hc.build_ramp("auto")
    for inp in args.inputs:
        convert_one(Path(inp), args, ramp)
    return 0


if __name__ == "__main__":
    sys.exit(main())
