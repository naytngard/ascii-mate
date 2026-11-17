"""Hazır (CC0) 3B modellerden HD sahneler: robot, astronot, şövalye. Kaynak/lisans: THIRD_PARTY.md.

Modeller repoya GİRMEZ (tools/models_cache/, .gitignore). Hazırlık: tools/blender_prep.py (Blender, arka plan) →
köşe renkli OBJ (tools/models_cache/*.obj). Bu modül OBJ'yi okur, yavaş ±25° salınımla (kare 0 = kare N, kesintisiz döngü)
döndürür ve common.render_cells_smooth ile aynı görünüme çevirir: ".:;+*%#$@" rampası, kontur karakteri yok, yalnızca
ışık/gölge → mürekkep yoğunluğu + hücre rengi.
"""

from __future__ import annotations

import math
from functools import lru_cache
from typing import Dict, Optional, Tuple

import numpy as np

import common
import hd_convert as hc

CACHE = common.BASE / "tools" / "models_cache"
SWAY_DEG = 25.0

# id → model dosyası, ışık, kamera çerçevesi, ön döndürme (derece, x/y/z), eğim
BUILDERS: Dict[str, dict] = {
    "knight_grass": dict(
        obj="knight.obj", aspect=0.80, tilt=12.0, pre=(0, 0, 0), fill=0.80, color_gain=1.6, gamma=1.15,
        spec_k=0.65, spec_pow=14.0, rim_k=0.6, diff_k=1.05,
        light=dict(dir=(-0.5, 0.65, 0.6), color=(0.85, 0.80, 0.70), sky=(0.30, 0.36, 0.46), ambient=0.20, rim=(0.9, 0.95, 1.0)),
        overlay="grass", sway_phase=0.0, bottom_pad=0.10),
    "knight_sunset": dict(
        obj="knight.obj", aspect=0.80, tilt=12.0, pre=(0, 0, 0), fill=0.80, color_gain=1.6, gamma=1.15,
        spec_k=0.65, spec_pow=14.0, rim_k=0.6, diff_k=1.1,
        light=dict(dir=(0.95, 0.22, 0.28), color=(1.5, 0.85, 0.45), sky=(0.45, 0.30, 0.32), ambient=0.20, rim=(1.0, 0.6, 0.3)),
        rock=True, bottom_pad=0.10),
    "robot": dict(
        obj="robot.obj", aspect=1.05, tilt=10.0, pre=(0, 0, 0), fill=0.82,
        light=dict(dir=(-0.45, 0.6, 0.65), color=(1.0, 0.97, 0.92), sky=(0.25, 0.30, 0.42), ambient=0.38, rim=(0.8, 0.9, 1.0))),
    "dragon": dict(
        obj="dragon.obj", aspect=1.0, tilt=10.0, pre=(0, 0, 0), fill=1.18, yaw=40.0, color_gain=1.8, gamma=0.9,
        spec_k=0.35, spec_pow=18.0, rim_k=0.5, diff_k=1.0,
        light=dict(dir=(-0.5, 0.65, 0.6), color=(0.95, 0.90, 0.80), sky=(0.30, 0.36, 0.46), ambient=0.24, rim=(0.9, 0.95, 1.0))),
    "astronaut": dict(
        obj="astro.obj", aspect=1.0, tilt=8.0, pre=(90, 0, 0), fill=0.82, yaw=25.0,
        light=dict(dir=(0.6, 0.5, 0.6), color=(1.0, 0.98, 0.92), sky=(0.12, 0.16, 0.30), ambient=0.30, rim=(0.5, 0.7, 1.0)),
        overlay="stars"),
}


# Telif künyesi (JSON "source" + "model_credit" alanları; THIRD_PARTY.md ile aynı)
CREDITS: Dict[str, dict] = {
    "knight_grass": dict(name="Knight statue (knight_statue.blend)", author="yd",
                         url="https://opengameart.org/content/knight-statue", license="CC0"),
    "knight_sunset": dict(name="Knight statue (knight_statue.blend)", author="yd",
                          url="https://opengameart.org/content/knight-statue", license="CC0"),
    "robot": dict(name="LowPoly Robot (Robot.obj)", author="Quaternius",
                  url="https://quaternius.itch.io/lowpoly-robot", license="CC0 1.0"),
    "dragon": dict(
        obj="dragon.obj", aspect=1.0, tilt=10.0, pre=(0, 0, 0), fill=1.18, yaw=40.0, color_gain=1.8, gamma=0.9,
        spec_k=0.35, spec_pow=18.0, rim_k=0.5, diff_k=1.0,
        light=dict(dir=(-0.5, 0.65, 0.6), color=(0.95, 0.90, 0.80), sky=(0.30, 0.36, 0.46), ambient=0.24, rim=(0.9, 0.95, 1.0))),
    "dragon": dict(name="Cethiel's Dragon 3D (dragon.obj, dokudan köşe rengi)", author="Drummyfish (Cethiel ile)",
                   url="https://opengameart.org/content/cethiels-dragon-3d", license="CC0"),
    "astronaut": dict(name="Astronaut low poly (Astronaut01.fbx)", author="ThunderWare games",
                      url="https://mariusmopar.itch.io/astronaut-low-poly", license="CC0"),
}


def source_text(builder: str) -> str:
    c = CREDITS[builder]
    return (f"tools/scenes/mesh_scenes.py; model: {c['name']}, yazar {c['author']}, {c['url']}, lisans {c['license']} "
            f"(model repoda yok; yalnız üretilen HD kareler)")


@lru_cache(maxsize=None)
def load(name: str):
    v, f, c = hc.parse_obj(CACHE / name)
    n = hc.vertex_normals(v, f)
    if c is None:
        c = np.full_like(v, 0.7)
    return v, f, c.astype(np.float32), n


def _rot(rx: float, ry: float, rz: float) -> np.ndarray:
    a, b, c = (math.radians(x) for x in (rx, ry, rz))
    Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]], np.float32)
    Ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]], np.float32)
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]], np.float32)
    return Rz @ Ry @ Rx


def ellipsoid_mesh(center, radii, color, nu: int = 28, nv: int = 16):
    """Kaya için UV elipsoit ağı (köşe renkli)."""
    us = np.linspace(0, 2 * math.pi, nu, endpoint=False)
    vs = np.linspace(0.0, math.pi, nv)
    P, F = [], []
    for j, t in enumerate(vs):
        for u in us:
            P.append((math.sin(t) * math.cos(u), math.cos(t), math.sin(t) * math.sin(u)))
    P = np.array(P, np.float32)
    for j in range(nv - 1):
        for i in range(nu):
            a, b = j * nu + i, j * nu + (i + 1) % nu
            c, d = (j + 1) * nu + i, (j + 1) * nu + (i + 1) % nu
            F += [[a, c, b], [b, c, d]]
    n = P.copy()
    v = P * np.asarray(radii, np.float32) + np.asarray(center, np.float32)
    nn = n / np.asarray(radii, np.float32)
    nn /= np.maximum(np.linalg.norm(nn, axis=1, keepdims=True), 1e-9)
    return v, np.array(F, np.int32), np.tile(np.asarray(color, np.float32), (len(v), 1)), nn.astype(np.float32)


def _merge(parts):
    vs, fs, cs, ns, off = [], [], [], [], 0
    for v, f, c, n in parts:
        vs.append(v); fs.append(f + off); cs.append(c); ns.append(n); off += len(v)
    return np.concatenate(vs), np.concatenate(fs), np.concatenate(cs), np.concatenate(ns)


def _raster(v, f, vcol, n, W: int, H: int, scale: float, cy: float, light: dict, fill: float, spec_k: float = 0.22,
            spec_pow: float = 28.0, rim_k: float = 0.32, diff_k: float = 0.9) -> np.ndarray:
    """Ortografik z-buffer; yönlü ışık + zayıf dolgu ışığı + gökyüzü/zemin ortamı + kenar ışığı. RGBA float."""
    sx = v[:, 0] * scale + W / 2.0
    sy = -(v[:, 1] - cy) * scale + H / 2.0
    sz = v[:, 2]
    L = np.asarray(light["dir"], np.float32)
    L = L / np.linalg.norm(L)
    Lf = np.array([-L[0], 0.2, 0.7], np.float32)
    Lf /= np.linalg.norm(Lf)
    lcol = np.asarray(light["color"], np.float32)
    sky = np.asarray(light["sky"], np.float32)
    rimc = np.asarray(light["rim"], np.float32)
    amb = float(light["ambient"])
    zbuf = np.full((H, W), -1e9, np.float32)
    img = np.zeros((H, W, 4), np.float32)
    for a, b, c in f:
        ax, ay, bx, by, cx, cy_ = sx[a], sy[a], sx[b], sy[b], sx[c], sy[c]
        area = (bx - ax) * (cy_ - ay) - (cx - ax) * (by - ay)
        if area >= 0:
            continue
        x0, x1 = int(max(0, math.floor(min(ax, bx, cx)))), int(min(W - 1, math.ceil(max(ax, bx, cx))))
        y0, y1 = int(max(0, math.floor(min(ay, by, cy_)))), int(min(H - 1, math.ceil(max(ay, by, cy_))))
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((bx - xs) * (cy_ - ys) - (cx - xs) * (by - ys)) / area
        w1 = ((cx - xs) * (ay - ys) - (ax - xs) * (cy_ - ys)) / area
        w2 = 1.0 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        z = w0 * sz[a] + w1 * sz[b] + w2 * sz[c]
        sub = zbuf[y0 : y1 + 1, x0 : x1 + 1]
        upd = inside & (z > sub)
        if not upd.any():
            continue
        nn = w0[..., None] * n[a] + w1[..., None] * n[b] + w2[..., None] * n[c]
        nn /= np.maximum(np.linalg.norm(nn, axis=-1, keepdims=True), 1e-9)
        base = w0[..., None] * vcol[a] + w1[..., None] * vcol[b] + w2[..., None] * vcol[c]
        diff = np.clip(nn @ L, 0, 1)[..., None]
        dfil = np.clip(nn @ Lf, 0, 1)[..., None]
        hemi = (0.5 + 0.5 * nn[..., 1:2])  # üst → gökyüzü, alt → zemin
        ambient = amb * (sky * hemi + 0.35 * (1.0 - hemi)) + amb * 0.35
        nz = np.clip(nn[..., 2:3], 0, 1)
        rim = ((1.0 - nz) ** 3) * rim_k * rimc
        spec = (np.clip(nn @ (L + np.array([0, 0, 1], np.float32)) / np.linalg.norm(L + np.array([0, 0, 1], np.float32)), 0, 1) ** spec_pow)[..., None] * spec_k
        rgb = base * (ambient + diff * lcol * diff_k + dfil * fill * 0.25) + rim * (0.4 + 0.6 * diff) + spec
        patch = img[y0 : y1 + 1, x0 : x1 + 1]
        patch[upd, :3] = np.clip(rgb, 0, 1.4)[upd]
        patch[upd, 3] = 1.0
        sub[upd] = z[upd]
    return img


def _cells(rgba: np.ndarray, cols: int, rows: int, ss: int, levels: Optional[Tuple[float, ...]], ramp, gamma=0.95, target_mean=0.62):
    """common.render_cells_smooth'un hücreleme aşaması (aynı kurallar)."""
    sx, sy = 2 * ss, 4 * ss
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
    gain = levels[2]
    if gain != 1.0:
        g = rgb * gain
        rgb = np.clip(g / (1.0 + np.maximum(g - 1.0, 0.0)), 0.0, 1.0)
    tone = np.clip((lum - lo) / (hi - lo), 0.0, 1.0) ** gamma
    tone = tone * np.clip(cov, 0.0, 1.0) ** 0.6
    n = len(ramp)
    ramp_chars = np.array([ord(c) for c, _ in ramp], np.uint8)
    idx = np.clip(np.round(1 + tone * (n - 2)).astype(int), 1, n - 1)
    chars = ramp_chars[idx]
    chars = np.where(cov < 0.22, 32, chars).astype(np.uint8)
    peak = rgb.max(axis=2, keepdims=True)
    hue = rgb / np.maximum(peak, 1e-4)
    bright = np.maximum(peak, 0.38 + 0.25 * tone[..., None])
    colors = np.clip(hue * bright, 0.0, 1.0)
    out_col = (colors * 255 + 0.5).astype(np.uint8)
    out_col[chars == 32] = 0
    return chars, out_col, levels


_RAMP = None


def frame(builder: str, ph: float, cols: int, levels: Optional[Tuple[float, ...]] = None, ss: int = 2, keep_rgba: bool = False):
    """ph ∈ [0,1): kare 0 ve 1.0 aynı (kesintisiz döngü). Dönüş: chars, colors, levels."""
    global _RAMP
    import animals

    if _RAMP is None:
        _RAMP = hc.build_ramp(common.SMOOTH_RAMP)
    spec = BUILDERS[builder]
    v, f, c, n = load(spec["obj"])
    c = np.clip(c * spec.get("color_gain", 1.0), 0.0, 1.0)
    parts = [(v, f, c, n)]
    ext = float(np.abs(v).max(axis=0)[1])  # yarı yükseklik
    if spec.get("rock"):
        # kaya: şövalyenin altında (model birimi: yükseklik ≈ 1.15 → kaya boyutu buna göre)
        h = float(v[:, 1].max() - v[:, 1].min())
        base_y = float(v[:, 1].min())
        rc = (2.2, 1.7, 1.4)  # kaya kare içinde seçilir kalsın: >1 değer yalnızca gölgeleme çarpanı (son renk 1.4'e kırpılır)
        parts.append(ellipsoid_mesh((0.0, base_y + 0.03 * h, -0.02 * h), (0.50 * h, 0.13 * h, 0.38 * h), rc))
        parts.append(ellipsoid_mesh((0.34 * h, base_y + 0.0 * h, 0.12 * h), (0.32 * h, 0.10 * h, 0.28 * h), rc))
    pre = _rot(*spec["pre"])
    ang = math.radians(SWAY_DEG) * math.sin(2 * math.pi * ph)
    R = _rot(spec["tilt"], 0, 0) @ _rot(0, spec.get("yaw", 0.0) + math.degrees(ang), 0) @ pre
    mv, mf, mc, mn = _merge(parts)
    pv = mv @ R.T
    pn = mn @ R.T
    aspect = spec["aspect"]
    rows = max(1, int(round(cols * aspect / 2.0)))
    sx_, sy_ = 2 * ss, 4 * ss
    W, H = cols * sx_, rows * sy_
    # sabit ölçek: dönüşten bağımsız sınır (yatay yarıçap), dikey yarı yükseklik
    r_h = float(np.sqrt(v[:, 0] ** 2 + v[:, 2] ** 2).max())
    kv = v @ R.T  # ölçek yalnızca ana modelden (kaya taşsa da şövalye küçülmesin)
    lo_y, hi_y = float(kv[:, 1].min()), float(kv[:, 1].max())
    ext_y = max(hi_y - lo_y, 1e-6) / 2.0
    # ekran: hücre 1:2 → piksel kare. Sığdır
    scale = spec["fill"] * min(W / (2.0 * r_h), H / (2.0 * ext_y))
    cy = (lo_y + hi_y) / 2.0 - spec.get("bottom_pad", 0.0) * 0.0
    # şövalye/kaya için kısa-bölgede çim payı: görüntüyü hafif yukarı kaydır
    cy -= spec.get("bottom_pad", 0.0) * ext_y
    pv = pv.astype(np.float32)
    rgba = _raster(pv, mf, mc, pn.astype(np.float32), W, H, scale, cy, spec["light"], spec["fill"], spec.get("spec_k", 0.22),
                   spec.get("spec_pow", 28.0), spec.get("rim_k", 0.32), spec.get("diff_k", 0.9))
    ch, co, lv = _cells(rgba, cols, rows, ss, levels, _RAMP, gamma=spec.get("gamma", 0.95))
    ov = None
    if spec.get("overlay") == "grass":
        ov = animals._grass_overlay(ph, 0.86, 0.75, 0.0, seed=3)
    elif spec.get("overlay") == "stars":
        ov = animals._stars_overlay()
    if ov is not None:
        ch, co = ch.copy(), co.copy()
        ov(ch, co, ph)
    if keep_rgba:
        return ch, co, lv, rgba
    return ch, co, lv



