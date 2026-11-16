"""Sahne betikleri için ortak yardımcılar: RGBA kareler → HD varlık (+ düşük çözünürlüklü klasik yedek) ve PNG önizleme."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

if os.name != "nt":  # Windows'ta gerçek platform: offscreen eklentisinde sistem yazı tipleri yok (glifler kutu çıkar → rampa bozulur)
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "tools"))

import numpy as np  # noqa: E402

import hd_convert as hc  # noqa: E402
from src.core.hd_format import write_hd  # noqa: E402

ANIM = BASE / "assets" / "animations"
PREVIEW_DIR = BASE / "build" / "previews"  # .gitignore: build/
SCENE_RAMP = ".:-=+*#%@"  # sahne dolgusu: klasik, okunaklı 9 kademe (gerçek mürekkebe göre yeniden sıralanır)
PALETTE_KEYS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz@#"  # 64 anahtar = 4×4×4 renk


def to_cells(frames_rgba: Sequence[np.ndarray], cols: int, *, gamma: float = 0.85, edge_boost: float = 0.25,
             bg_threshold: float = 0.035, color_lift: float = 0.35, ramp: Optional[list] = None) -> Tuple[List[np.ndarray], List[np.ndarray]]:
    ramp = ramp or hc.build_ramp("auto")
    h, w = frames_rgba[0].shape[:2]
    rows = hc.grid_rows(w, h, cols)
    chars, colors = [], []
    for arr in frames_rgba:
        c, k = hc.convert_rgba(arr, cols, rows, ramp, gamma=gamma, edge_boost=edge_boost,
                               bg_threshold=bg_threshold, color_lift=color_lift)
        chars.append(c)
        colors.append(k)
    return chars, colors


def render_cells(scene, light, cam: dict, cols: int, *, ramp: Optional[list] = None, levels: Optional[Tuple[float, float]] = None,
                 gamma: float = 0.9, fill_max: float = 0.62, depth_jump: float = 0.18, keep_rgba: bool = False,
                 target_mean: float = 0.62):
    """SDF sahnesini doğrudan hücre ızgarasına çevirir (kontur + öznitelik katmanı):
      * zemin (ıskalanan) → boşluk (saydam)
      * öznitelik malzemesi (glyph tanımlı: göz, burun, bıyık...) hücrede varsa → o karakter, saf renk
      * siluet ve malzeme/derinlik sınırları → yönlü kontur karakteri  | - _ / \\
      * iç bölge → ölçülmüş mürekkep rampası (yoğunluk tavanı fill_max: konturlar okunur kalsın)
    Görüntü (rows*4, cols*2) piksel çözülür: her hücre 2×4 alt piksel.
    Dönüş: chars, colors, levels(lo, hi) [, rgba]"""
    import sdf

    ramp = ramp or hc.build_ramp(SCENE_RAMP)
    aspect = float(cam.get("aspect", 1.0))
    rows = max(1, int(round(cols * aspect / 2.0)))
    W, H = cols * 2, rows * 4
    buf: dict = {}
    rgba = sdf.render(scene, W, H, cam_pos=cam["cam"], target=cam["target"], fov_deg=cam["fov"], light=light, buffers=buf)
    mat = buf["mat"]
    depth = buf["depth"]
    hit = mat >= 0

    def blk(x):
        return x.reshape(rows, 4, cols, 2, *x.shape[2:])

    cnt = blk(hit.astype(np.float32)).sum(axis=(1, 3))
    cov = cnt / 8.0
    rgb_sum = blk(rgba[..., :3] * hit[..., None]).sum(axis=(1, 3))
    rgb = rgb_sum / np.maximum(cnt, 1.0)[..., None]
    lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    if levels is None:
        vals = lum[cov > 0.5]
        lo, hi = (float(np.percentile(vals, 2)), float(np.percentile(vals, 99))) if vals.size else (0.0, 1.0)
        # Otomatik pozlama: dolu hücrelerin ortalama renk parlaklığı hedefin altındaysa renk kazancı uygula
        # (koyu sahneler masaüstünde kaybolmasın). Tüm döngüde aynı kazanç → titreme yok.
        mean_l = float(lum[cov > 0.5].mean()) if vals.size else target_mean
        gain = float(np.clip(target_mean / max(mean_l, 1e-3), 1.0, 3.0))
        levels = (lo, max(hi, lo + 1e-3), gain)
    lo, hi = levels[0], levels[1]
    gain = levels[2] if len(levels) > 2 else 1.0
    if gain != 1.0:
        # yumuşak tavanlı kazanç: parlak bölgeler patlamasın (x / (1 + x*k) biçimli omuz)
        g = rgb * gain
        rgb = g / (1.0 + np.maximum(g - 1.0, 0.0))
        rgb = np.clip(rgb, 0.0, 1.0)
    tone = np.clip((lum - lo) / (hi - lo), 0.0, 1.0) ** gamma
    n = len(ramp)
    ramp_chars = np.array([ord(c) for c, _ in ramp], np.uint8)
    idx = np.clip(np.round(1 + tone * (fill_max * (n - 1) - 1)).astype(int), 1, n - 1)
    chars = ramp_chars[idx]
    colors = rgb.copy()

    # --- sınırlar (alt piksel ızgarasında)
    outline_ok = np.array([m.outline for m in scene.materials] + [True], bool)  # -1 → son eleman
    mo = outline_ok[mat]
    bnd = np.zeros_like(hit)
    for dy, dx in ((0, 1), (1, 0)):
        a_m, b_m = mat[: H - dy, : W - dx], mat[dy:, dx:]
        a_h, b_h = hit[: H - dy, : W - dx], hit[dy:, dx:]
        a_o, b_o = mo[: H - dy, : W - dx], mo[dy:, dx:]
        with np.errstate(invalid="ignore"):
            dj = np.abs(np.where(a_h & b_h, depth[: H - dy, : W - dx] - depth[dy:, dx:], 0.0)) > depth_jump
        e = (a_h != b_h) | ((a_m != b_m) & a_h & b_h & a_o & b_o) | dj
        bnd[: H - dy, : W - dx] |= e
        bnd[dy:, dx:] |= e
    edge_cell = blk(bnd).any(axis=(1, 3)) & (cov > 0.12)
    sil = edge_cell & (cov < 0.999)
    # yön: siluette kapsama gradyanı, iç sınırda parlaklık gradyanı
    def grad(f):
        pz = np.pad(f, 1, mode="edge")
        gx = (pz[:-2, 2:] + 2 * pz[1:-1, 2:] + pz[2:, 2:]) - (pz[:-2, :-2] + 2 * pz[1:-1, :-2] + pz[2:, :-2])
        gy = (pz[2:, :-2] + 2 * pz[2:, 1:-1] + pz[2:, 2:]) - (pz[:-2, :-2] + 2 * pz[:-2, 1:-1] + pz[:-2, 2:])
        return gx, gy * 2.0  # hücre 1:2 → dikey adım fiziksel olarak iki kat

    gxc, gyc = grad(cov)
    gxl, gyl = grad(np.where(cov > 0, lum, 0.0) + 0.0)
    gx = np.where(sil, gxc, gxl)
    gy = np.where(sil, gyc, gyl)
    theta = np.degrees(np.arctan2(gy, gx)) % 180.0
    ech = np.full((rows, cols), ord("|"), np.uint8)
    ech[(theta >= 22.5) & (theta < 67.5)] = ord("/")
    horiz = (theta >= 67.5) & (theta < 112.5)
    ech[horiz] = ord("-")
    ech[horiz & sil & (gy > 0) & (cov < 0.55)] = ord("_")  # nesnenin üst kenarı (altı dolu, üstü boş)
    ech[(theta >= 112.5) & (theta < 157.5)] = ord("\\")
    chars = np.where(edge_cell, ech, chars)
    colors = np.where(edge_cell[..., None], np.where(sil[..., None], np.clip(rgb * 1.18 + 0.04, 0, 1), rgb * 0.72), colors)

    # --- öznitelikler (en yüksek öncelik kazanır)
    best_pri = np.full((rows, cols), -1, np.int32)
    for mi, m in enumerate(scene.materials):
        if not m.glyph:
            continue
        c_m = blk((mat == mi).astype(np.float32)).sum(axis=(1, 3))
        sel = (c_m >= float(m.glyph_min)) & (m.priority > best_pri)
        if not sel.any():
            continue
        best_pri[sel] = m.priority
        chars[sel] = ord(m.glyph)
        mrgb = (blk(rgba[..., :3] * (mat == mi)[..., None]).sum(axis=(1, 3)) / np.maximum(c_m, 1.0)[..., None])
        colors[sel] = np.clip(mrgb[sel] * 1.1 + 0.05, 0, 1)

    bg = cov < 0.30
    chars = np.where(bg & (best_pri < 0), 32, chars).astype(np.uint8)
    out_col = (np.clip(colors, 0, 1) * 255 + 0.5).astype(np.uint8)
    out_col[chars == 32] = 0
    if keep_rgba:
        return chars, out_col, levels, rgba
    return chars, out_col, levels


# gerçekçi mod: kalp/satürn gibi yumuşak gölge rampası (mürekkebe göre sıralanır). Yatay karakterler (- ~ = ,) yok:
# küçük hücrelerde satır satır "tarama çizgisi" gibi görünüp yüzeyi çizgili gösteriyorlardı.
SMOOTH_RAMP = ".:;+*%#$@"


def render_cells_smooth(scene, light, cam: dict, cols: int, *, ramp: Optional[list] = None,
                        levels: Optional[Tuple[float, ...]] = None, gamma: float = 0.95, ss: int = 2,
                        target_mean: float = 0.62, keep_rgba: bool = False):
    """SDF sahnesini 'gerçekçi' biçimde hücrelere çevirir: kontur ve öznitelik (göz/burun) karakteri YOK.
    Matematiksel shader'lardaki (kalp, satürn) gibi yalnızca ışık/gölge → mürekkep yoğunluğu + hücre rengi.
      * her hücre (2*ss)×(4*ss) alt pikselle örneklenir (kenar yumuşatma)
      * kısmi kaplanan kenar hücreleri daha seyrek karakter alır → siluet yumuşak, çizgi film konturu yok
      * kontrast düzeyleri ilk kareden alınır ve tüm döngüde sabit kalır (titreme yok)
    Dönüş: chars, colors, levels [, rgba]"""
    import sdf

    ramp = ramp or hc.build_ramp(SMOOTH_RAMP)
    for m in scene.materials:  # eski öznitelik malzemeleri (göz, bıyık...) parlamasın: doğal renkleriyle gölgelensin
        if m.glyph:
            m.emissive = min(m.emissive, 0.12)
            m.rim = min(m.rim, 0.15)
    aspect = float(cam.get("aspect", 1.0))
    rows = max(1, int(round(cols * aspect / 2.0)))
    sx, sy = 2 * ss, 4 * ss
    W, H = cols * sx, rows * sy
    rgba = sdf.render(scene, W, H, cam_pos=cam["cam"], target=cam["target"], fov_deg=cam["fov"], light=light)
    a = rgba[..., 3]

    def blk(x):
        return x.reshape(rows, sy, cols, sx, *x.shape[2:])

    cov = blk(a).mean(axis=(1, 3))
    rgb = blk(rgba[..., :3] * a[..., None]).sum(axis=(1, 3)) / np.maximum(blk(a).sum(axis=(1, 3)), 1e-6)[..., None]
    lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    if levels is None:
        vals = lum[cov > 0.5]
        lo, hi = (float(np.percentile(vals, 1)), float(np.percentile(vals, 99.5))) if vals.size else (0.0, 1.0)
        mean_l = float(vals.mean()) if vals.size else target_mean
        gain = float(np.clip(target_mean / max(mean_l, 1e-3), 1.0, 3.0))
        levels = (lo, max(hi, lo + 1e-3), gain)
    lo, hi = levels[0], levels[1]
    gain = levels[2] if len(levels) > 2 else 1.0
    if gain != 1.0:
        g = rgb * gain
        rgb = np.clip(g / (1.0 + np.maximum(g - 1.0, 0.0)), 0.0, 1.0)
    tone = np.clip((lum - lo) / (hi - lo), 0.0, 1.0) ** gamma
    tone = tone * np.clip(cov, 0.0, 1.0) ** 0.6  # kenar yumuşatma: yarı dolu hücre → daha hafif karakter
    n = len(ramp)
    ramp_chars = np.array([ord(c) for c, _ in ramp], np.uint8)
    idx = np.clip(np.round(1 + tone * (n - 2)).astype(int), 1, n - 1)
    chars = ramp_chars[idx]
    chars = np.where(cov < 0.22, 32, chars).astype(np.uint8)
    # renk: ton bilgisi asıl olarak karakter yoğunluğunda; renk ise malzemenin tonunu korur ama gölgede tamamen
    # kararmaz (koyu masaüstünde kaybolmasın). Parlaklık tabanı ~0.38, ışıkta gerçek renk.
    peak = rgb.max(axis=2, keepdims=True)
    hue = rgb / np.maximum(peak, 1e-4)
    bright = np.maximum(peak, 0.38 + 0.25 * tone[..., None])
    colors = np.clip(hue * bright, 0.0, 1.0)
    out_col = (colors * 255 + 0.5).astype(np.uint8)
    out_col[chars == 32] = 0
    if keep_rgba:
        return chars, out_col, levels, rgba
    return chars, out_col, levels


def palette_frames(chars: Sequence[np.ndarray], colors: Sequence[np.ndarray]) -> Tuple[List[str], Dict[str, str], List[str]]:
    """Hücre dizilerini klasik 1.0 biçimine çevirir: satırlar + 64 renkli palet (palette_map) + renk haritası (color_frames)."""
    frames, cframes = [], []
    pal: Dict[str, str] = {}
    for i, (r_, g_, b_) in enumerate((r, g, b) for r in range(4) for g in range(4) for b in range(4)):
        pal[PALETTE_KEYS[i]] = "#%02X%02X%02X" % (r_ * 85, g_ * 85, b_ * 85)
    for ch, co in zip(chars, colors):
        q = np.clip((co.astype(np.int32) + 42) // 85, 0, 3)
        key = q[..., 0] * 16 + q[..., 1] * 4 + q[..., 2]
        rows, crow = [], []
        for r in range(ch.shape[0]):
            rows.append("".join(map(chr, ch[r].tolist())))
            crow.append("".join(" " if ch[r, c] == 32 else PALETTE_KEYS[key[r, c]] for c in range(ch.shape[1])))
        frames.append("\n".join(rows))
        cframes.append("\n".join(crow))
    return frames, pal, cframes


def classic_fallback(frames_rgba: Sequence[np.ndarray], cols: int = 60, **kw) -> Tuple[List[str], Dict[str, str], List[str]]:
    """HD kapalıyken kullanılacak klasik (1.0 uyumlu) kareler: satırlar + 64 renkli palet + renk haritası."""
    chars, colors = to_cells(frames_rgba, cols, **kw)
    frames, cframes = [], []
    pal: Dict[str, str] = {}
    for i, (r_, g_, b_) in enumerate((r, g, b) for r in range(4) for g in range(4) for b in range(4)):
        pal[PALETTE_KEYS[i]] = "#%02X%02X%02X" % (r_ * 85, g_ * 85, b_ * 85)
    for ch, co in zip(chars, colors):
        q = np.clip((co.astype(np.int32) + 42) // 85, 0, 3)
        key = q[..., 0] * 16 + q[..., 1] * 4 + q[..., 2]
        rows = []
        crow = []
        for r in range(ch.shape[0]):
            rows.append("".join(map(chr, ch[r].tolist())))
            crow.append("".join(" " if ch[r, c] == 32 else PALETTE_KEYS[key[r, c]] for c in range(ch.shape[1])))
        frames.append("\n".join(rows))
        cframes.append("\n".join(crow))
    return frames, pal, cframes


def write_scene_asset(
    folder: str, asset_id: str, name: str, category: str, chars: List[np.ndarray], colors: List[np.ndarray],
    fps: float, tags: List[str], fallback: Optional[Tuple[List[str], Dict[str, str], List[str]]] = None,
    extra: Optional[dict] = None, source: str = "",
) -> Path:
    out = ANIM / folder
    out.mkdir(parents=True, exist_ok=True)
    hd_path = out / f"{asset_id}.ascii.hd"
    write_hd(hd_path, chars, colors)
    rows, cols = chars[0].shape
    meta = {
        "schema_version": "3.0", "hd": True, "id": asset_id, "name": name, "category": category, "author": "ASCII Mate",
        "tags": tags + ["hd"], "default_fps": float(fps), "recommended_color": "auto_hd",
        "hd_file": hd_path.name, "cols": int(cols), "rows": int(rows), "frame_count": len(chars), "bg_mode": "transparent",
        "source": source or "tools/scenes (kendi ürettiğimiz SDF sahnesi; harici görsel yok)",
        "particles": {"enabled_by_default": False, "type": "none", "toggle_label": "Parçacık Efekti", "spawn_area": "around",
                      "density": "low", "chars": ["*", "+", "."]},
        "frames": [],
    }
    if fallback is not None:
        meta["frames"], meta["palette_map"], meta["color_frames"] = fallback
    if extra:
        meta.update(extra)
    jp = out / f"{asset_id}.ascii.json"
    jp.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return jp


def preview_png(chars: np.ndarray, colors: np.ndarray, path: Path, cw: int = 6, ch: int = 12, bg=(12, 14, 20),
                tint: float = 0.0) -> Path:
    """Hücreleri gerçek glif atlasıyla PNG'ye çizer (değerlendirme için; repoya girmez)."""
    from PyQt6.QtGui import QImage

    from src.gui.hd_renderer import build_atlas

    hc.ensure_qt()
    atlas = build_atlas(cw, ch)
    rows, cols = chars.shape
    a = atlas[chars.astype(np.intp) - 32].astype(np.float32) / 255.0  # (r, c, ch, cw)
    img = np.empty((rows, ch, cols, cw, 3), np.float32)
    bgv = np.asarray(bg, np.float32)
    for k in range(3):
        cell_bg = bgv[k] + tint * colors[..., k].astype(np.float32)[:, :, None, None]
        img[..., k] = (a * colors[..., k][:, :, None, None] + (1 - a) * cell_bg).transpose(0, 2, 1, 3)
    out = np.ascontiguousarray(img.reshape(rows * ch, cols * cw, 3).clip(0, 255).astype(np.uint8))
    path.parent.mkdir(parents=True, exist_ok=True)
    q = QImage(out.data, out.shape[1], out.shape[0], out.shape[1] * 3, QImage.Format.Format_RGB888)
    q.save(str(path))
    return path


def save_rgba_png(arr: np.ndarray, path: Path, bg=(12, 14, 20)) -> Path:
    from PyQt6.QtGui import QImage

    hc.ensure_qt()
    a = arr[..., 3:4]
    rgb = (arr[..., :3] * a + np.asarray(bg, np.float32) / 255.0 * (1 - a)) * 255
    out = np.ascontiguousarray(rgb.clip(0, 255).astype(np.uint8))
    path.parent.mkdir(parents=True, exist_ok=True)
    QImage(out.data, out.shape[1], out.shape[0], out.shape[1] * 3, QImage.Format.Format_RGB888).save(str(path))
    return path
