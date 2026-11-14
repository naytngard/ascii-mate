"""Hayvan/karakter SDF sahneleri (eski elipsoit modellerinin HD karşılıkları). Her `build_*` (faz) → Scene döner.

faz ∈ [0, 1): döngü içindeki konum (nefes, kuyruk, kulak, göz kırpma buradan türetilir).
"""

from __future__ import annotations

import math

import numpy as np

from sdf import Light, Scene, capsule, ellipsoid, rot, round_box, round_cone, sphere, torus, value_noise


# ASCII için düz/yumuşak ışık: ton büyük ölçüde malzeme renginden gelsin, gölgeler hücreleri karartıp şekli yutmasın
ASCII_LIGHT = Light(dir=(-0.45, 0.6, 0.75), color=(0.75, 0.70, 0.62), sky=(0.32, 0.34, 0.40), rim_color=(1.0, 0.85, 0.6),
                    ambient=0.42, shadow_k=4.0)


def _blink(ph: float, at: float = 0.78, width: float = 0.05) -> float:
    """0 = açık, 1 = kapalı (kısa göz kırpma)."""
    d = abs(((ph - at + 0.5) % 1.0) - 0.5)
    return max(0.0, 1.0 - d / width)


def _tabby(base, stripe_scale=11.0, depth=0.18, seed=1):
    def pat(p, n):
        s = 0.5 + 0.5 * np.sin(p[:, 1] * stripe_scale + 2.2 * value_noise(p, 2.5, seed) * 3.0 + p[:, 0] * 1.5)
        fur = 0.93 + 0.14 * value_noise(p, 28.0, seed + 7)
        return (1.0 - depth * (s > 0.62)) * fur

    return pat


def _fur(scale=26.0, amp=0.28, seed=3):
    def pat(p, n):
        return (1.0 - amp / 2) + amp * value_noise(p, scale, seed)

    return pat


# =========================================================================== KEDİ (oturan, 3/4)

def build_cat(ph: float) -> tuple[Scene, Light, dict]:
    s = Scene()
    fur = s.mat((235, 150, 70), rim=0.45, pattern=_tabby(None))
    cream = s.mat((250, 232, 205), rim=0.3, pattern=_fur(30, 0.2), outline=False)
    pink = s.mat((240, 140, 160), rim=0.2)
    nose = s.mat((255, 150, 175), rim=0.2, glyph="v", priority=5, glyph_min=3)
    eye = s.mat((150, 245, 120), spec=0.9, shine=60, rim=0.1, emissive=0.7, glyph="o", priority=1, glyph_min=6)
    pupil = s.mat((30, 60, 34), spec=0.6, shine=80, rim=0.0, glyph="|", priority=6, glyph_min=2)
    dark = s.mat((120, 70, 60), rim=0.1, glyph="-", priority=4)
    whisk_h = s.mat((250, 248, 240), rim=0.0, emissive=0.8, glyph="-", priority=2, outline=False)
    whisk_l = s.mat((250, 248, 240), rim=0.0, emissive=0.8, glyph="/", priority=2, outline=False)
    whisk_r = s.mat((250, 248, 240), rim=0.0, emissive=0.8, glyph="\\", priority=2, outline=False)

    breath = 1.0 + 0.018 * math.sin(ph * 2 * math.pi)
    turn = rot(0, -22, 0)  # 3/4 duruş: tüm kedi hafif sola döner
    yaw_head = -10 + 6 * math.sin(ph * 2 * math.pi)

    def T(p):  # gövde koordinatı → dünya
        return tuple((np.asarray(p) @ turn.T).tolist())

    body = s.group(k=0.16)
    body.items += [
        (ellipsoid(T((0.0, -0.38, -0.05)), (0.55 * breath, 0.66, 0.50 * breath), turn), fur),  # göğüs/gövde
        (ellipsoid(T((0.0, -0.95, -0.25)), (0.78, 0.38, 0.62), turn), fur),  # kalça (oturan)
        (capsule(T((-0.22, -0.55, 0.32)), T((-0.24, -1.12, 0.42)), 0.11), fur),  # ön bacaklar
        (capsule(T((0.22, -0.55, 0.32)), T((0.24, -1.12, 0.42)), 0.11), fur),
        (ellipsoid(T((-0.24, -1.17, 0.50)), (0.14, 0.07, 0.17), turn), cream),  # patiler
        (ellipsoid(T((0.24, -1.17, 0.50)), (0.14, 0.07, 0.17), turn), cream),
        (ellipsoid(T((0.0, -0.25, 0.38)), (0.30, 0.42, 0.18), turn), cream),  # göğüs beyazı
    ]
    # kuyruk: arkadan dolanıp öne kıvrılan, ucu salınan
    tail = s.group(k=0.06)
    sway = 0.18 * math.sin(ph * 2 * math.pi + 0.7)
    pts = [(0.55, -1.15, -0.55), (0.95, -1.12, -0.05), (0.85, -1.10, 0.45), (0.45 + sway * 0.4, -1.05, 0.70),
           (0.05 + sway, -0.98, 0.78)]
    for a, b in zip(pts, pts[1:]):
        tail.items.append((capsule(T(a), T(b), 0.10), fur))

    # baş (ayrı dönüşle hafif sağa-sola bakar)
    hr = turn @ rot(-6, yaw_head, 0)
    hc = np.array((0.0, 0.66, 0.15))

    def H(p):
        return tuple((hc @ turn.T + (np.asarray(p) @ hr.T)).tolist())

    head = s.group(k=0.10)
    head.items += [
        (ellipsoid(H((0, 0, 0)), (0.64, 0.53, 0.56), hr), fur),
        (ellipsoid(H((-0.19, -0.16, 0.40)), (0.21, 0.16, 0.18), hr), cream),  # yanak/ağız çevresi
        (ellipsoid(H((0.19, -0.16, 0.40)), (0.21, 0.16, 0.18), hr), cream),
        (ellipsoid(H((0.0, -0.22, 0.30)), (0.12, 0.08, 0.10), hr), cream),  # çene
    ]
    ears = s.group(k=0.03)
    twitch = 18.0 * max(0.0, math.sin((ph - 0.30) * 2 * math.pi * 3)) if 0.30 < ph < 0.47 else 0.0
    for sx, tw in ((-1, twitch), (1, 0.0)):
        base = H((0.30 * sx, 0.30, -0.02))
        tip = H((0.42 * sx, 0.78, -0.08 + 0.05 * (tw / 18.0)))
        ears.items.append((round_cone(base, tip, 0.20, 0.025), fur))
        ears.items.append((round_cone(H((0.29 * sx, 0.34, 0.07)), H((0.39 * sx, 0.70, 0.02)), 0.11, 0.015), pink))
    face = s.group(k=0.0)
    bl = _blink(ph)
    for sx in (-1, 1):
        ec = H((0.21 * sx, 0.07, 0.47))
        face.items.append((ellipsoid(ec, (0.13, 0.135 * (1 - 0.88 * bl) + 0.008, 0.075), hr), eye if bl < 0.5 else dark))
        if bl < 0.5:
            face.items.append((ellipsoid(H((0.21 * sx, 0.07, 0.535)), (0.014, 0.095, 0.03), hr), pupil))  # dikey göz bebeği
    face.items.append((round_cone(H((0, -0.07, 0.585)), H((0, -0.11, 0.60)), 0.045, 0.025), nose))  # burun
    face.items.append((capsule(H((0, -0.15, 0.59)), H((0, -0.22, 0.575)), 0.016), dark))  # ağız çizgisi
    face.items.append((capsule(H((0, -0.22, 0.575)), H((-0.08, -0.26, 0.55)), 0.015), dark))
    face.items.append((capsule(H((0, -0.22, 0.575)), H((0.08, -0.26, 0.55)), 0.015), dark))
    for sx in (-1, 1):  # bıyıklar
        for dy, m in ((0.02, whisk_h), (-0.07, whisk_h)):
            a = H((0.20 * sx, -0.15, 0.55))
            b = H((0.84 * sx, -0.12 + dy, 0.46))
            face.items.append((capsule(a, b, 0.006), m))
    light = ASCII_LIGHT
    return s, light, {"cam": (0.0, 0.72, 4.3), "target": (0.0, 0.62, 0.0), "fov": 27.0, "aspect": 0.92}


# =========================================================================== ortak yardımcılar

def _feather(scale=26.0, amp=0.25):
    def pat(p, n):
        s = np.sin(p[:, 1] * scale + np.abs(p[:, 0]) * scale * 0.7)
        return (1.0 - amp / 2) + amp * (s > 0.3)

    return pat


def _H(center, R):
    c = np.asarray(center, np.float64)

    def f(p):
        return tuple((c + np.asarray(p, np.float64) @ R.T).tolist())

    return f


def _eyes(s, H, R, xs, y, z, r, iris, pupil_glyph="o", pupil_r=0.5, blink=0.0, slit=False, group=None):
    """Göz: renkli iris + koyu bebek + parlama; kırpınca göz kapağı (koyu çizgi)."""
    g = group or s.group(k=0.0)
    m_iris = s.mat(iris, spec=0.9, shine=60, rim=0.05, emissive=0.55, glyph="o", priority=1, glyph_min=6)
    m_pup = s.mat((25, 25, 30), spec=0.8, shine=80, rim=0.0, glyph="|" if slit else "@", priority=6, glyph_min=2)
    m_lid = s.mat((70, 50, 40), rim=0.0, glyph="-", priority=7, glyph_min=2)
    m_hi = s.mat((255, 255, 255), emissive=1.0, glyph="'", priority=8, glyph_min=2, outline=False)
    for sx in xs:
        c = H((sx, y, z))
        if blink > 0.5:
            g.items.append((ellipsoid(c, (r * 1.05, r * 0.18, r * 0.6), R), m_lid))
            continue
        g.items.append((ellipsoid(c, (r, r, r * 0.6), R), m_iris))
        pr = (r * 0.22, r * 0.8, r * 0.3) if slit else (r * pupil_r, r * pupil_r, r * 0.3)
        g.items.append((ellipsoid(H((sx, y, z + r * 0.45)), pr, R), m_pup))
        g.items.append((sphere(H((sx - r * 0.3, y + r * 0.35, z + r * 0.62)), r * 0.16), m_hi))
    return g


# =========================================================================== BAYKUŞ

def build_owl(ph: float):
    s = Scene()
    brown = s.mat((150, 100, 60), rim=0.4, pattern=_feather(30, 0.25))
    dark = s.mat((95, 62, 38), rim=0.3, pattern=_feather(24, 0.3))
    disc = s.mat((236, 214, 178), rim=0.25, outline=True, pattern=_fur(40, 0.15))
    belly = s.mat((228, 205, 165), rim=0.3, pattern=_feather(36, 0.35), outline=False)
    beak = s.mat((245, 175, 60), spec=0.5, rim=0.1, glyph="v", priority=5, glyph_min=2)
    branch = s.mat((110, 75, 45), rim=0.2, pattern=_fur(12, 0.4))
    claw = s.mat((70, 60, 55), glyph="m", priority=3, glyph_min=3)
    breath = 1.0 + 0.015 * math.sin(ph * 2 * math.pi)
    tilt = 8 * math.sin(ph * 2 * math.pi)
    body = s.group(k=0.12)
    body.items += [
        (ellipsoid((0, -0.45, 0), (0.78 * breath, 0.95, 0.62), None), brown),
        (ellipsoid((0, -0.55, 0.30), (0.52, 0.70, 0.36), None), belly),
        (ellipsoid((-0.70, -0.45, -0.05), (0.22, 0.72, 0.40), rot(0, 0, -8)), dark),
        (ellipsoid((0.70, -0.45, -0.05), (0.22, 0.72, 0.40), rot(0, 0, 8)), dark),
    ]
    R = rot(0, tilt, 0)
    H = _H((0, 0.55, 0.05), R)
    head = s.group(k=0.10)
    head.items += [
        (ellipsoid(H((0, 0, 0)), (0.72, 0.58, 0.58), R), brown),
        (round_cone(H((-0.42, 0.40, -0.05)), H((-0.62, 0.86, -0.12)), 0.16, 0.03), dark),
        (round_cone(H((0.42, 0.40, -0.05)), H((0.62, 0.86, -0.12)), 0.16, 0.03), dark),
    ]
    face = s.group(k=0.06)
    for sx in (-0.27, 0.27):
        face.items.append((ellipsoid(H((sx, 0.02, 0.38)), (0.30, 0.30, 0.16), R), disc))
    bl = _blink(ph, 0.62, 0.05)
    _eyes(s, H, R, (-0.27, 0.27), 0.04, 0.50, 0.16, (255, 190, 40), pupil_r=0.55, blink=bl)
    face2 = s.group()
    face2.items.append((round_cone(H((0, -0.12, 0.50)), H((0, -0.30, 0.56)), 0.07, 0.015), beak))
    perch = s.group(k=0.02)
    perch.items.append((capsule((-1.3, -1.42, 0.15), (1.3, -1.38, 0.10), 0.09), branch))
    for sx in (-0.25, 0.25):
        for k in (-0.07, 0.0, 0.07):
            perch.items.append((capsule((sx + k, -1.36, 0.28), (sx + k * 1.4, -1.40, 0.40), 0.028), claw))
    return s, ASCII_LIGHT, {"cam": (0.0, -0.10, 6.0), "target": (0.0, -0.20, 0.0), "fov": 30.0, "aspect": 0.95}


# =========================================================================== KÖPEK (golden retriever)

def build_dog(ph: float):
    s = Scene()
    gold = s.mat((228, 168, 90), rim=0.45, pattern=_fur(30, 0.22))
    ear_m = s.mat((196, 128, 62), rim=0.35, pattern=_fur(36, 0.3))
    light_m = s.mat((245, 214, 160), rim=0.3, pattern=_fur(34, 0.18), outline=False)
    nose = s.mat((70, 62, 70), spec=0.8, shine=50, rim=0.1, glyph="@", priority=5, glyph_min=3)
    tongue = s.mat((245, 110, 130), spec=0.5, rim=0.1, glyph="u", priority=4, glyph_min=3)
    collar = s.mat((210, 50, 60), spec=0.4, rim=0.2)
    tag = s.mat((250, 210, 80), spec=1.0, shine=40, emissive=0.3, glyph="o", priority=4, glyph_min=2)
    pant = 0.5 + 0.5 * math.sin(ph * 2 * math.pi * 4)
    flop = 6 * math.sin(ph * 2 * math.pi * 2)
    body = s.group(k=0.14)
    body.items += [(ellipsoid((0, -0.95, -0.1), (0.75, 0.70, 0.55), None), gold),
                   (capsule((0, -0.55, -0.05), (0, 0.05, 0.0), 0.36), gold),  # boyun
                   (ellipsoid((0, -0.80, 0.28), (0.42, 0.50, 0.30), None), light_m)]
    s.group().items.append((torus((0, -0.36, 0.0), 0.43, 0.06, rot(78, 0, 0)), collar))
    s.group().items.append((sphere((0, -0.55, 0.47), 0.07), tag))
    R = rot(-6, -14 + 6 * math.sin(ph * 2 * math.pi), 4)
    H = _H((0, 0.22, 0.05), R)
    head = s.group(k=0.14)
    head.items += [
        (ellipsoid(H((0, 0.08, -0.05)), (0.58, 0.52, 0.52), R), gold),
        (ellipsoid(H((0, -0.18, 0.42)), (0.32, 0.26, 0.40), R), light_m),  # burun kemiği/ağız
        (ellipsoid(H((0, 0.30, 0.25)), (0.36, 0.16, 0.30), R), gold),  # alın
    ]
    ears = s.group(k=0.05)
    for sx in (-1, 1):
        ears.items.append((ellipsoid(H((0.52 * sx, -0.10, -0.05)), (0.17, 0.42, 0.26), R @ rot(0, 0, (14 + flop) * sx)), ear_m))
    _eyes(s, H, R, (-0.22, 0.22), 0.12, 0.40, 0.085, (90, 55, 35), pupil_r=0.7, blink=_blink(ph, 0.55, 0.04))
    f = s.group()
    f.items.append((ellipsoid(H((0, -0.04, 0.82)), (0.12, 0.08, 0.08), R), nose))
    f.items.append((ellipsoid(H((0, -0.42 - 0.05 * pant, 0.64)), (0.10, 0.08 + 0.05 * pant, 0.05), R @ rot(-25, 0, 0)), tongue))
    return s, ASCII_LIGHT, {"cam": (0.0, -0.05, 5.4), "target": (0.0, -0.12, 0.0), "fov": 30.0, "aspect": 0.95}


# =========================================================================== TİLKİ

def build_fox(ph: float):
    s = Scene()
    orange = s.mat((240, 125, 45), rim=0.5, pattern=_fur(32, 0.22))
    white = s.mat((250, 244, 232), rim=0.3, pattern=_fur(38, 0.15), outline=False)
    black = s.mat((45, 32, 30), rim=0.25)
    nose = s.mat((40, 30, 30), spec=0.8, shine=50, glyph="@", priority=5, glyph_min=2)
    body = s.group(k=0.14)
    body.items += [(ellipsoid((0, -0.95, -0.15), (0.62, 0.68, 0.50), None), orange),
                   (capsule((0, -0.55, -0.05), (0, 0.05, 0.0), 0.30), orange),  # boyun
                   (ellipsoid((0, -0.80, 0.22), (0.36, 0.52, 0.28), None), white)]
    tail = s.group(k=0.10)
    sw = 0.25 * math.sin(ph * 2 * math.pi)
    for i in range(5):
        f = i / 4
        c = (0.55 + 0.45 * math.sin(f * 2.2) + sw * f, -1.45 + 0.65 * f, 0.20 + 0.25 * f)
        r = 0.20 + 0.10 * math.sin(f * math.pi)
        tail.items.append((sphere(c, r), white if i == 4 else orange))
    R = rot(-4, -18 + 7 * math.sin(ph * 2 * math.pi), 3)
    H = _H((0, 0.22, 0.05), R)
    head = s.group(k=0.12)
    head.items += [
        (ellipsoid(H((0, 0.05, 0)), (0.56, 0.44, 0.46), R), orange),
        (round_cone(H((0, -0.08, 0.20)), H((0, -0.16, 0.86)), 0.22, 0.06), white),  # sivri burun
        (ellipsoid(H((-0.36, -0.14, 0.18)), (0.24, 0.22, 0.26), R), white),
        (ellipsoid(H((0.36, -0.14, 0.18)), (0.24, 0.22, 0.26), R), white),
    ]
    ears = s.group(k=0.02)
    tw = 10 * max(0.0, math.sin((ph - 0.2) * 2 * math.pi * 3)) if 0.2 < ph < 0.37 else 0.0
    for sx in (-1, 1):
        b, tip = H((0.30 * sx, 0.32, -0.02)), H((0.48 * sx, 0.95, -0.10 + 0.002 * tw * sx))
        ears.items.append((round_cone(b, tip, 0.22, 0.03), orange))
        ears.items.append((round_cone(H((0.44 * sx, 0.78, -0.08)), tip, 0.08, 0.035), black))
    _eyes(s, H, R, (-0.22, 0.22), 0.14, 0.38, 0.085, (255, 190, 60), slit=True, blink=_blink(ph, 0.7, 0.04))
    s.group().items.append((sphere(H((0, -0.14, 0.92)), 0.065), nose))
    return s, ASCII_LIGHT, {"cam": (0.0, -0.20, 5.6), "target": (0.0, -0.28, 0.0), "fov": 30.0, "aspect": 0.95}


# =========================================================================== KAMP ATEŞİ BAŞINDA KURT

def build_wolf(ph: float):
    s = Scene()
    grey = s.mat((150, 152, 160), rim=0.5, pattern=_fur(30, 0.25))
    pale = s.mat((215, 215, 220), rim=0.4, pattern=_fur(34, 0.2), outline=False)
    darkg = s.mat((80, 82, 92), rim=0.3, pattern=_fur(30, 0.2))
    nose = s.mat((35, 35, 40), spec=0.8, glyph="@", priority=5, glyph_min=2)
    log = s.mat((110, 70, 40), rim=0.2, pattern=_fur(14, 0.5))
    ember = s.mat((255, 120, 30), emissive=1.0, rim=0.0, glyph="*", priority=2, glyph_min=2, outline=False)
    flame = s.mat((255, 190, 60), emissive=1.2, rim=0.0, outline=False)
    ground = s.mat((60, 70, 55), rim=0.0, pattern=_fur(6, 0.4), outline=False)
    # kurt (oturan, 3/4, sağa bakıyor)
    b = s.group(k=0.16)
    b.items += [
        (ellipsoid((-0.75, -0.55, 0.0), (0.62, 0.55, 0.48), rot(0, 0, -25)), grey),
        (ellipsoid((-1.05, -0.95, 0.0), (0.55, 0.32, 0.45), None), grey),
        (capsule((-0.45, -0.55, 0.25), (-0.40, -1.15, 0.35), 0.10), grey),
        (capsule((-0.55, -0.55, -0.20), (-0.52, -1.15, -0.25), 0.10), darkg),
        (ellipsoid((-0.48, -0.35, 0.18), (0.30, 0.42, 0.25), rot(0, 0, -15)), pale),
        (capsule((-0.55, 0.0, 0.0), (-0.35, 0.35, 0.0), 0.28), grey),  # boyun
    ]
    tail = s.group(k=0.08)
    sw = 0.12 * math.sin(ph * 2 * math.pi)
    for a_, b_ in (((-1.55, -1.0, -0.1), (-1.95, -1.05, 0.1)), ((-1.95, -1.05, 0.1), (-2.15 - sw, -1.05, 0.45))):
        tail.items.append((capsule(a_, b_, 0.16), grey))
    R = rot(0, 35, -8 + 3 * math.sin(ph * 2 * math.pi))
    H = _H((-0.30, 0.42, 0.05), R)
    head = s.group(k=0.10)
    head.items += [
        (ellipsoid(H((0, 0, 0)), (0.36, 0.32, 0.34), R), grey),
        (round_cone(H((0.0, -0.06, 0.10)), H((0.0, -0.14, 0.62)), 0.20, 0.08), pale),
    ]
    for sx in (-1, 1):
        head.items.append((round_cone(H((0.18 * sx, 0.20, -0.05)), H((0.24 * sx, 0.58, -0.10)), 0.13, 0.02), darkg))
    _eyes(s, H, R, (-0.15, 0.15), 0.08, 0.27, 0.06, (255, 205, 80), slit=False, pupil_r=0.5, blink=_blink(ph, 0.8, 0.04))
    s.group().items.append((sphere(H((0, -0.13, 0.68)), 0.06), nose))
    # ateş
    fire = s.group(k=0.0)
    fire.items += [(capsule((0.75, -1.25, 0.35), (1.65, -1.18, 0.05), 0.08), log),
                   (capsule((0.85, -1.18, -0.05), (1.6, -1.25, 0.40), 0.08), log)]
    fl = s.group(k=0.12)
    for i, (dx, hgt) in enumerate(((0.0, 0.85), (-0.18, 0.55), (0.17, 0.62), (0.05, 0.40))):
        fh = hgt * (0.85 + 0.25 * math.sin(ph * 2 * math.pi * 3 + i * 1.7))
        wob = 0.06 * math.sin(ph * 2 * math.pi * 2 + i)
        fl.items.append((round_cone((1.2 + dx, -1.15, 0.18), (1.2 + dx + wob, -1.15 + fh, 0.18), 0.17, 0.01), flame))
    s.group().items.append((sphere((1.2, -1.18, 0.18), 0.14), ember))
    s.group().items.append((ellipsoid((0.0, -1.42, 0.0), (2.6, 0.08, 1.4), None), ground))
    li = Light(dir=(0.7, 0.4, 0.55), color=(1.05, 0.62, 0.32), sky=(0.16, 0.20, 0.32), rim_color=(1.0, 0.55, 0.25),
               ambient=0.35, shadow_k=4.0)
    return s, li, {"cam": (0.0, -0.35, 7.6), "target": (-0.25, -0.45, 0.0), "fov": 30.0, "aspect": 0.62}


# =========================================================================== ŞÖVALYE (ortak; iki sahne)

def _knight(s: Scene, ph: float, *, helmet_on: bool, steel, cloth, seat: str):
    steel_m = s.mat(steel, spec=0.9, shine=40, rim=0.6, pattern=_fur(60, 0.12))
    dark_m = s.mat(tuple(int(c * 0.55) for c in steel), spec=0.6, shine=30, rim=0.4)
    cloth_m = s.mat(cloth, rim=0.35, pattern=_fur(30, 0.2))
    skin = s.mat((225, 175, 140), rim=0.3)
    hair = s.mat((70, 50, 35), rim=0.2, pattern=_fur(40, 0.3))
    blade = s.mat((235, 240, 250), spec=1.0, shine=80, rim=0.6, emissive=0.15)
    gold = s.mat((240, 195, 80), spec=0.8, shine=40, rim=0.3)
    slit = s.mat((20, 20, 25), glyph="=", priority=5, glyph_min=2)
    br = 1.0 + 0.012 * math.sin(ph * 2 * math.pi)
    seat_y = -0.62 if seat == "rock" else -0.95
    g = s.group(k=0.06)
    g.items += [
        (ellipsoid((0, -0.05, 0), (0.48 * br, 0.62, 0.36 * br), None), steel_m),  # göğüs zırhı
        (ellipsoid((0, -0.62, 0.02), (0.44, 0.22, 0.34), None), dark_m),  # bel
        (round_box((0, -0.28, 0.30), (0.22, 0.42, 0.05), 0.03, rot(-8, 0, 0)), cloth_m),  # tabard
    ]
    for sx in (-1, 1):
        g.items += [
            (sphere((0.52 * sx, 0.40, 0.0), 0.24), steel_m),  # omuzluk
            (capsule((0.56 * sx, 0.30, 0.05), (0.64 * sx, -0.25, 0.22), 0.13), steel_m),  # üst kol
            (capsule((0.64 * sx, -0.25, 0.22), (0.38 * sx, -0.55, 0.62), 0.12), dark_m),  # ön kol (dizlere)
            (capsule((0.24 * sx, -0.75, 0.05), (0.30 * sx, seat_y + 0.05, 0.80), 0.17), steel_m),  # uyluk
            (capsule((0.30 * sx, seat_y + 0.05, 0.80), (0.30 * sx, seat_y - 0.70, 0.95), 0.14), dark_m),  # baldır
            (ellipsoid((0.30 * sx, seat_y - 0.78, 1.10), (0.13, 0.09, 0.22), None), dark_m),  # çizme
        ]
    R = rot(-8, 12 * math.sin(ph * 2 * math.pi) if helmet_on else -10, 0)
    H = _H((0, 0.92, 0.0), R)
    hg = s.group(k=0.04)
    if helmet_on:
        hg.items += [(ellipsoid(H((0, 0, 0)), (0.30, 0.36, 0.32), R), steel_m),
                     (ellipsoid(H((0, 0.36, -0.05)), (0.05, 0.16, 0.28), R), cloth_m)]  # sorguç
        s.group().items.append((round_box(H((0, 0.02, 0.29)), (0.20, 0.025, 0.04), 0.01, R), slit))
    else:
        hg.items += [(ellipsoid(H((0, 0, 0.02)), (0.24, 0.30, 0.26), R), skin),
                     (ellipsoid(H((0, 0.10, -0.06)), (0.27, 0.27, 0.26), R), hair)]
        _eyes(s, H, R, (-0.09, 0.09), 0.02, 0.23, 0.035, (90, 70, 50), pupil_r=0.7, blink=_blink(ph, 0.4, 0.04))
        # miğfer dizde
        s.group().items.append((ellipsoid((-0.42, -0.42, 0.85), (0.24, 0.27, 0.24), None), steel_m))
    # kılıç: yere saplı, sağda
    sg = s.group()
    sg.items += [(round_box((0.95, -0.55, 0.45), (0.035, 0.85, 0.012), 0.008, rot(0, 0, 4)), blade),
                 (round_box((0.89, 0.34, 0.45), (0.20, 0.03, 0.04), 0.01, rot(0, 0, 4)), gold),
                 (capsule((0.88, 0.37, 0.45), (0.86, 0.60, 0.45), 0.035), cloth_m),
                 (sphere((0.86, 0.64, 0.45), 0.055), gold)]
    return seat_y


def _grass_overlay(ph: float, row_from: float = 0.72, density: float = 0.55, flowers: float = 0.06, seed: int = 7,
                   palette=((70, 150, 60), (110, 175, 70), (160, 190, 80)), flower_col=(220, 40, 50)):
    """Hücre uzayında rüzgârlı çimen + kır çiçekleri (yalnızca alt bölge değişir → ucuz)."""
    rng = np.random.default_rng(seed)

    def ov(chars: np.ndarray, colors: np.ndarray, phase: float) -> None:
        rows, cols = chars.shape
        r0 = int(rows * row_from)
        rs = np.random.default_rng(seed)
        for c in range(cols):
            if rs.random() > density:
                continue
            h = int(rs.integers(2, max(3, rows - r0)))
            bend = math.sin(phase * 2 * math.pi + c * 0.21)
            col = palette[int(rs.integers(0, len(palette)))]
            for k in range(h):
                r = rows - 1 - k
                if r < r0:
                    break
                lean = bend * (k / max(h, 1)) ** 1.5
                cc = c + int(round(lean * 1.4))
                if 0 <= cc < cols and (chars[r, cc] == 32 or k < 2):
                    chars[r, cc] = ord("|" if abs(lean) < 0.33 else ("/" if lean > 0 else "\\"))
                    colors[r, cc] = col
            if rs.random() < flowers and h > 2:
                cc = c + int(round(bend * 1.3))
                r = rows - h
                if 0 <= cc < cols:
                    chars[r, cc] = ord("@" if rs.random() < 0.5 else "*")
                    colors[r, cc] = flower_col

    return ov


def build_knight_grass(ph: float):
    s = Scene()
    _knight(s, ph, helmet_on=True, steel=(175, 185, 205), cloth=(170, 40, 45), seat="grass")
    li = Light(dir=(-0.5, 0.65, 0.6), color=(0.85, 0.80, 0.70), sky=(0.30, 0.36, 0.46), rim_color=(0.9, 0.9, 1.0),
               ambient=0.40, shadow_k=4.0)
    return s, li, {"cam": (2.2, 0.6, 7.4), "target": (0.10, -0.35, 0.0), "fov": 30.0, "aspect": 0.80,
                   "overlay": _grass_overlay(ph, 0.80, 0.75, 0.0, seed=3)}


def build_knight_sunset(ph: float):
    s = Scene()
    seat_y = _knight(s, ph, helmet_on=True, steel=(150, 140, 135), cloth=(120, 25, 30), seat="rock")
    rock = s.mat((95, 80, 75), rim=0.4, pattern=_fur(8, 0.45))
    s.group(k=0.2).items += [(ellipsoid((0.0, -1.05, -0.10), (0.95, 0.42, 0.70), None), rock),
                             (ellipsoid((0.65, -1.35, 0.25), (0.75, 0.30, 0.65), None), rock)]
    pulse = 0.9 + 0.1 * math.sin(ph * 2 * math.pi)
    li = Light(dir=(0.75, 0.35, 0.55), color=(1.35 * pulse, 0.80 * pulse, 0.45), sky=(0.45, 0.30, 0.32),
               rim_color=(1.0, 0.55, 0.3), ambient=0.48, shadow_k=4.0)
    return s, li, {"cam": (-2.4, 0.3, 7.3), "target": (0.05, -0.30, 0.0), "fov": 31.0, "aspect": 0.80}


def build_meadow_warrior(ph: float):
    s = Scene()
    _knight(s, ph, helmet_on=False, steel=(160, 165, 170), cloth=(90, 110, 70), seat="grass")
    li = Light(dir=(-0.4, 0.7, 0.55), color=(0.95, 0.90, 0.70), sky=(0.32, 0.40, 0.30), rim_color=(1.0, 0.95, 0.75),
               ambient=0.40, shadow_k=4.0)
    return s, li, {"cam": (-1.9, 0.5, 7.5), "target": (0.05, -0.35, 0.0), "fov": 30.0, "aspect": 0.80,
                   "overlay": _grass_overlay(ph, 0.74, 0.85, 0.12, seed=11, flower_col=(240, 220, 90))}


# =========================================================================== EJDERHA YAVRUSU

def build_dragon(ph: float):
    s = Scene()
    green = s.mat((90, 190, 100), spec=0.4, shine=30, rim=0.5, pattern=_feather(40, 0.2))
    belly = s.mat((240, 220, 140), rim=0.3, pattern=lambda p, n: 0.85 + 0.15 * (np.sin(p[:, 1] * 30) > 0), outline=False)
    wing = s.mat((70, 140, 200), rim=0.6, pattern=_fur(18, 0.2))
    horn = s.mat((245, 235, 205), spec=0.6, rim=0.3)
    nost = s.mat((40, 70, 50), glyph=":", priority=5, glyph_min=2)
    flap = 22 * math.sin(ph * 2 * math.pi * 2)
    b = s.group(k=0.16)
    b.items += [(ellipsoid((0, -0.75, 0), (0.62, 0.68, 0.55), None), green),
                (ellipsoid((0, -0.80, 0.30), (0.40, 0.52, 0.30), None), belly),
                (ellipsoid((-0.32, -1.38, 0.30), (0.20, 0.12, 0.28), None), green),
                (ellipsoid((0.32, -1.38, 0.30), (0.20, 0.12, 0.28), None), green),
                (capsule((0, -0.30, 0), (0, 0.10, 0.05), 0.30), green)]
    tail = s.group(k=0.08)
    pts = [(0.4, -1.25, -0.4), (0.95, -1.35, -0.2), (1.25, -1.25, 0.25), (1.15 + 0.1 * math.sin(ph * 6.28), -1.05, 0.55)]
    for i, (a_, b_) in enumerate(zip(pts, pts[1:])):
        tail.items.append((round_cone(a_, b_, 0.20 - i * 0.05, 0.15 - i * 0.05), green))
    for sx in (-1, 1):
        wg = s.group(k=0.02)
        R = rot(0, 25 * sx, (35 + flap) * sx)
        wg.items.append((ellipsoid((0.75 * sx, -0.25, -0.35), (0.60, 0.05, 0.38), R), wing))
        wg.items.append((capsule((0.35 * sx, -0.30, -0.30), (1.15 * sx, -0.30 + 0.35 * math.sin(math.radians(35 + flap)), -0.40), 0.05), green))
    R = rot(-5, -12 + 8 * math.sin(ph * 6.28), 0)
    H = _H((0, 0.45, 0.10), R)
    h = s.group(k=0.12)
    h.items += [(ellipsoid(H((0, 0, 0)), (0.50, 0.44, 0.46), R), green),
                (ellipsoid(H((0, -0.14, 0.40)), (0.30, 0.22, 0.30), R), green)]
    for sx in (-1, 1):
        s.group().items.append((round_cone(H((0.22 * sx, 0.32, -0.08)), H((0.32 * sx, 0.68, -0.30)), 0.08, 0.015), horn))
        s.group().items.append((sphere(H((0.08 * sx, -0.08, 0.70)), 0.03), nost))
    _eyes(s, H, R, (-0.22, 0.22), 0.10, 0.36, 0.11, (255, 210, 60), slit=True, blink=_blink(ph, 0.66, 0.04))
    return s, ASCII_LIGHT, {"cam": (0.8, 0.2, 6.2), "target": (0.15, -0.40, 0.0), "fov": 32.0, "aspect": 0.95}


# =========================================================================== NÖBETÇİ ROBOT

def build_robot(ph: float):
    s = Scene()
    metal = s.mat((165, 178, 198), spec=0.9, shine=50, rim=0.5)
    dark = s.mat((80, 90, 108), spec=0.6, shine=30, rim=0.3)
    visor = s.mat((15, 30, 45), spec=1.0, shine=90, rim=0.2)
    eye = s.mat((90, 240, 255), emissive=1.2, glyph="@", priority=6, glyph_min=2)
    lamp = s.mat((255, 90, 80) if (ph % 0.5) < 0.25 else (120, 40, 40), emissive=1.0, glyph="*", priority=6, glyph_min=1)
    chest = s.mat((255, 160, 60), emissive=0.9 * (0.6 + 0.4 * math.sin(ph * 6.28 * 2)), glyph="#", priority=4, glyph_min=4)
    g = s.group(k=0.04)
    g.items += [(round_box((0, -0.25, 0), (0.58, 0.62, 0.40), 0.12), metal),
                (round_box((0, -0.98, 0), (0.42, 0.16, 0.32), 0.06), dark),
                (capsule((0, 0.38, 0), (0, 0.52, 0), 0.16), dark)]
    for sx in (-1, 1):
        g.items += [(sphere((0.72 * sx, 0.18, 0), 0.20), dark),
                    (capsule((0.78 * sx, 0.10, 0.0), (0.86 * sx, -0.65, 0.12), 0.13), metal),
                    (round_box((0.88 * sx, -0.80, 0.14), (0.12, 0.10, 0.12), 0.04), dark),
                    (capsule((0.26 * sx, -1.10, 0), (0.28 * sx, -1.75, 0.05), 0.15), metal),
                    (round_box((0.30 * sx, -1.85, 0.12), (0.18, 0.07, 0.26), 0.04), dark)]
    s.group().items.append((round_box((0, -0.15, 0.40), (0.22, 0.20, 0.02), 0.03), chest))
    R = rot(0, 18 * math.sin(ph * 6.28), 0)
    H = _H((0, 0.82, 0.0), R)
    hg = s.group(k=0.03)
    hg.items += [(round_box(H((0, 0, 0)), (0.40, 0.30, 0.34), 0.12, R), metal),
                 (round_box(H((0, 0.0, 0.30)), (0.32, 0.09, 0.06), 0.04, R), visor),
                 (capsule(H((0.0, 0.30, 0.0)), H((0.0, 0.62, 0.0)), 0.025), dark)]
    scan = 0.24 * math.sin(ph * 6.28 * 2)
    s.group().items.append((ellipsoid(H((scan, 0.0, 0.36)), (0.07, 0.05, 0.03), R), eye))
    s.group().items.append((sphere(H((0.0, 0.66, 0.0)), 0.06), lamp))
    return s, ASCII_LIGHT, {"cam": (1.2, 0.2, 7.2), "target": (0.0, -0.45, 0.0), "fov": 31.0, "aspect": 1.05}


# =========================================================================== ASTRONOT

def _stars_overlay(seed=5, n=90):
    def ov(chars, colors, phase):
        rows, cols = chars.shape
        rs = np.random.default_rng(seed)
        for i in range(n):
            r, c = int(rs.integers(0, rows)), int(rs.integers(0, cols))
            if chars[r, c] != 32:
                continue
            tw = 0.5 + 0.5 * math.sin(phase * 6.28 * 2 + i * 1.3)
            chars[r, c] = ord("*" if tw > 0.85 else ("+" if tw > 0.55 else "."))
            v = int(140 + 110 * tw)
            colors[r, c] = (v, v, min(255, v + 25))
    return ov


def build_astronaut(ph: float):
    s = Scene()
    suit = s.mat((235, 238, 245), spec=0.3, rim=0.5, pattern=_fur(20, 0.08))
    grey = s.mat((150, 155, 168), spec=0.4, rim=0.3)
    visor = s.mat((230, 170, 60), spec=1.4, shine=90, rim=0.8, emissive=0.15)
    panel = s.mat((90, 200, 255), emissive=0.9, glyph="=", priority=4, glyph_min=3)
    red = s.mat((220, 60, 60), emissive=0.4, glyph="o", priority=4, glyph_min=2)
    fl = 0.06 * math.sin(ph * 6.28)
    R = rot(8 * math.sin(ph * 6.28), -20, -10 + 6 * math.sin(ph * 6.28))
    T = _H((0, fl, 0), R)
    g = s.group(k=0.10)
    g.items += [(ellipsoid(T((0, -0.25, 0)), (0.52, 0.62, 0.40), R), suit),
                (round_box(T((0, -0.20, -0.45)), (0.40, 0.48, 0.16), 0.08, R), grey)]
    for sx, a_ in ((-1, 25), (1, -55)):
        g.items += [(capsule(T((0.50 * sx, 0.12, 0)), T((0.85 * sx, -0.35 + (0.4 if a_ < 0 else 0), 0.25)), 0.16), suit),
                    (sphere(T((0.88 * sx, -0.40 + (0.42 if a_ < 0 else 0), 0.28)), 0.15), grey),
                    (capsule(T((0.24 * sx, -0.80, 0)), T((0.35 * sx, -1.45, 0.25 * sx)), 0.18), suit),
                    (ellipsoid(T((0.36 * sx, -1.58, 0.30 * sx + 0.05)), (0.18, 0.12, 0.25), R), grey)]
    hg = s.group(k=0.04)
    hg.items += [(sphere(T((0, 0.62, 0)), 0.42), suit), (torus(T((0, 0.30, 0)), 0.30, 0.07, R), grey)]
    s.group().items.append((ellipsoid(T((0, 0.64, 0.20)), (0.32, 0.27, 0.26), R), visor))
    s.group().items.append((round_box(T((0, -0.12, 0.40)), (0.20, 0.12, 0.02), 0.02, R), panel))
    s.group().items.append((sphere(T((0.12, -0.32, 0.40)), 0.045), red))
    li = Light(dir=(0.6, 0.5, 0.6), color=(1.0, 0.98, 0.92), sky=(0.12, 0.16, 0.30), rim_color=(0.5, 0.7, 1.0),
               ambient=0.30, shadow_k=6.0)
    return s, li, {"cam": (0.0, 0.0, 7.0), "target": (0.0, -0.40, 0.0), "fov": 33.0, "aspect": 1.0,
                   "overlay": _stars_overlay()}


# =========================================================================== BÜYÜCÜ + KİTAP

def _sparkle_overlay(center=(0.5, 0.62), radius=(0.18, 0.10), n=8, col=(255, 230, 120)):
    def ov(chars, colors, phase):
        rows, cols = chars.shape
        for i in range(n):
            a = phase * 6.28 + i * 6.28 / n
            r = int(rows * (center[1] + radius[1] * math.sin(a * 1.3)))
            c = int(cols * (center[0] + radius[0] * math.cos(a)))
            if 0 <= r < rows and 0 <= c < cols:
                chars[r, c] = ord("*" if i % 2 else "+")
                colors[r, c] = col
    return ov


def build_wizard(ph: float):
    s = Scene()
    robe = s.mat((90, 70, 190), rim=0.5, pattern=_fur(16, 0.2))
    robe2 = s.mat((60, 45, 140), rim=0.4)
    skin = s.mat((235, 190, 160), rim=0.3)
    beard = s.mat((240, 240, 245), rim=0.4, pattern=_fur(50, 0.25), outline=False)
    cover = s.mat((130, 75, 40), rim=0.3)
    page = s.mat((250, 240, 205), emissive=0.5, rim=0.1, outline=False)
    staff = s.mat((140, 95, 55), rim=0.3)
    orb = s.mat((120, 255, 230), emissive=1.2, glyph="O", priority=5, glyph_min=4)
    star = s.mat((250, 220, 90), emissive=0.8, glyph="*", priority=5, glyph_min=2)
    bob = 0.05 * math.sin(ph * 6.28)
    g = s.group(k=0.12)
    g.items += [(round_cone((0, -1.55, 0), (0, 0.20, 0), 0.82, 0.30), robe),
                (capsule((-0.40, 0.05, 0.1), (-0.30, -0.45, 0.55), 0.14), robe2),
                (capsule((0.40, 0.05, 0.1), (0.30, -0.45, 0.55), 0.14), robe2)]
    s.group(k=0.06).items += [(sphere((0, 0.55, 0.05), 0.28), skin),
                              (round_cone((0, 0.40, 0.22), (0, -0.25, 0.30), 0.22, 0.05), beard)]
    _eyes(s, _H((0, 0.60, 0.05), rot()), rot(), (-0.10, 0.10), 0.0, 0.24, 0.035, (60, 60, 90), pupil_r=0.7,
          blink=_blink(ph, 0.3, 0.04))
    hat = s.group(k=0.05)
    hat.items += [(torus((0, 0.78, 0), 0.40, 0.07), robe2), (round_cone((0, 0.80, 0), (0.05, 1.35, -0.05), 0.32, 0.13), robe),
                  (round_cone((0.05, 1.35, -0.05), (0.30, 1.62, -0.10), 0.13, 0.02), robe)]
    s.group().items.append((sphere((-0.08, 1.05, 0.28), 0.05), star))
    bk = s.group(k=0.0)
    R = rot(-35, 0, 0)
    bk.items += [(round_box((0, -0.38 + bob, 0.70), (0.42, 0.03, 0.30), 0.02, R), cover),
                 (round_box((-0.20, -0.33 + bob, 0.72), (0.19, 0.02, 0.27), 0.02, R @ rot(0, 0, 8)), page),
                 (round_box((0.20, -0.33 + bob, 0.72), (0.19, 0.02, 0.27), 0.02, R @ rot(0, 0, -8)), page)]
    s.group().items += [(capsule((-0.95, -1.55, 0.2), (-0.95, 0.95, 0.2), 0.05), staff)]
    s.group().items += [(sphere((-0.95, 1.08, 0.2), 0.14), orb)]
    return s, ASCII_LIGHT, {"cam": (0.9, 0.3, 8.0), "target": (0.0, -0.15, 0.0), "fov": 30.0, "aspect": 1.15,
                            "overlay": _sparkle_overlay((0.5, 0.60), (0.20, 0.06))}


# =========================================================================== BONSAİ

def build_bonsai(ph: float):
    s = Scene()
    pot = s.mat((190, 100, 70), spec=0.5, rim=0.4)
    soil = s.mat((80, 58, 40), rim=0.1, outline=False)
    bark = s.mat((120, 85, 55), rim=0.4, pattern=lambda p, n: 0.8 + 0.3 * (np.sin(p[:, 1] * 40 + 3 * value_noise(p, 6)) > 0))
    leaf = s.mat((80, 170, 80), rim=0.5, pattern=_fur(14, 0.45))
    leaf2 = s.mat((60, 140, 70), rim=0.5, pattern=_fur(14, 0.45))
    sway = 0.04 * math.sin(ph * 6.28)
    s.group(k=0.02).items += [(round_box((0, -1.05, 0), (0.95, 0.22, 0.55), 0.08), pot),
                              (round_box((0, -0.80, 0), (1.02, 0.04, 0.60), 0.03), pot),
                              (round_box((0, -0.78, 0), (0.88, 0.03, 0.50), 0.02), soil)]
    tr = s.group(k=0.08)
    pts = [(-0.05, -0.80, 0), (0.18, -0.45, 0.05), (0.05, -0.10, 0.0), (-0.22, 0.20, 0.05), (-0.10 + sway, 0.50, 0.0)]
    for i, (a_, b_) in enumerate(zip(pts, pts[1:])):
        tr.items.append((round_cone(a_, b_, 0.17 - 0.03 * i, 0.14 - 0.03 * i), bark))
    tr.items += [(capsule((0.05, -0.10, 0.0), (0.62 + sway, 0.05, 0.05), 0.06), bark),
                 (capsule((-0.22, 0.20, 0.05), (-0.75 + sway, 0.30, 0.0), 0.05), bark)]
    noise = lambda p: value_noise(p, 7.0, 4)  # noqa: E731
    from sdf import displace
    fo = s.group(k=0.15)
    for c, r, m in (((-0.10 + sway, 0.78, 0.0), 0.45, leaf), ((0.70 + sway, 0.20, 0.05), 0.32, leaf2),
                    ((-0.82 + sway, 0.42, 0.0), 0.30, leaf2)):
        fo.items.append((displace(ellipsoid(c, (r * 1.35, r * 0.75, r), None), noise, 0.10), m))
    return s, ASCII_LIGHT, {"cam": (0.5, 0.4, 7.0), "target": (0.0, -0.10, 0.0), "fov": 30.0, "aspect": 0.95}


# =========================================================================== ATLI SÜVARİ (sepya)

def build_rider(ph: float):
    s = Scene()
    sep = lambda k: tuple(min(255, int(c * k)) for c in (215, 175, 120))  # noqa: E731
    horse = s.mat((92, 66, 48), spec=0.5, shine=30, rim=0.8, pattern=_fur(22, 0.12))
    mane = s.mat((45, 34, 30), rim=0.6, pattern=_fur(40, 0.35))
    hoof = s.mat((40, 34, 32), rim=0.3)
    coat = s.mat(sep(0.95), rim=0.6, pattern=_fur(26, 0.2))
    hat = s.mat(sep(0.62), rim=0.5)
    skin = s.mat(sep(1.10), rim=0.4)
    leather = s.mat(sep(0.55), rim=0.4)
    eye = s.mat((235, 225, 210), emissive=0.6, glyph="o", priority=5, glyph_min=1)
    br = 1.0 + 0.015 * math.sin(ph * 6.28)
    nod = 4 * math.sin(ph * 6.28)
    hb = s.group(k=0.22)
    # gövde: göğüs (önde dolgun) + karın + sağrı (arkada yuvarlak) → doğal at sırtı eğrisi
    hb.items += [(ellipsoid((0.62, -0.10, 0), (0.48, 0.50 * br, 0.38 * br), rot(0, 0, -10)), horse),
                 (ellipsoid((0.0, -0.18, 0), (0.70, 0.42 * br, 0.38 * br), None), horse),
                 (ellipsoid((-0.62, -0.08, 0), (0.50, 0.50, 0.40), rot(0, 0, 8)), horse)]
    # boyun: göğüsten yukarı-öne kalınlaşarak; baş: ayrı grup, hafif baş sallama
    hb.items += [(round_cone((0.80, 0.05, 0), (1.18, 0.78, 0), 0.30, 0.17), horse)]
    hR = rot(0, 0, -38 + nod)
    hd = s.group(k=0.10)
    hd.items += [(round_cone((1.18, 0.80, 0), (1.18 + 0.52 * math.cos(math.radians(-38 + nod)),
                                               0.80 + 0.52 * math.sin(math.radians(-38 + nod)), 0), 0.17, 0.10), horse),
                 (round_cone((1.12, 0.92, 0.07), (1.08, 1.12, 0.09), 0.05, 0.01), horse),
                 (round_cone((1.12, 0.92, -0.07), (1.08, 1.12, -0.09), 0.05, 0.01), horse)]
    s.group().items.append((sphere((1.32, 0.75, 0.13), 0.035), eye))
    mn = s.group(k=0.05)
    mn.items += [(capsule((0.86, 0.30, 0.0), (1.12, 0.92, 0.0), 0.08), mane)]
    # bacaklar: üstte kaslı (yuvarlak koni), dizden aşağı ince, bileklikli toynak; bir ön bacak hafif bükük (adım)
    legs = s.group(k=0.08)
    for x, z, bend in ((0.70, 0.20, 0.18), (0.62, -0.20, 0.0), (-0.66, 0.20, 0.0), (-0.72, -0.20, -0.10)):
        knee = (x + 0.02 + bend * 0.6, -0.78, z)
        foot = (x + bend, -1.42, z)
        legs.items += [(round_cone((x, -0.35, z), knee, 0.15, 0.075), horse),
                       (round_cone(knee, foot, 0.07, 0.055), horse)]
        s.group().items.append((round_box((foot[0] + 0.02, -1.48, z), (0.07, 0.05, 0.07), 0.02), hoof))
    tw = 0.12 * math.sin(ph * 6.28)
    tail = s.group(k=0.06)
    tail.items += [(round_cone((-1.08, 0.12, 0), (-1.30, -0.40, tw), 0.10, 0.08), mane),
                   (round_cone((-1.30, -0.40, tw), (-1.30, -0.95, tw * 1.6), 0.08, 0.04), mane)]
    # binici
    rd = s.group(k=0.08)
    rd.items += [(round_box((-0.05, 0.28, 0), (0.32, 0.10, 0.34), 0.05), leather),  # eyer
                 (ellipsoid((-0.02, 0.80, 0), (0.24, 0.40, 0.22), None), coat),  # gövde
                 (round_cone((0.0, 0.42, 0.24), (0.20, -0.05, 0.36), 0.11, 0.08), coat),  # uyluk
                 (round_cone((0.20, -0.05, 0.36), (0.12, -0.45, 0.38), 0.08, 0.06), leather),  # çizme
                 (round_cone((0.0, 0.42, -0.24), (0.20, -0.05, -0.36), 0.11, 0.08), coat),
                 (round_cone((0.20, -0.05, -0.36), (0.12, -0.45, -0.38), 0.08, 0.06), leather),
                 (capsule((0.10, 1.05, 0.22), (0.55, 0.78, 0.12), 0.07), coat),  # kollar (dizgin)
                 (capsule((0.10, 1.05, -0.22), (0.55, 0.78, -0.06), 0.07), coat)]
    s.group(k=0.03).items += [(sphere((0.02, 1.36, 0), 0.15), skin)]
    s.group(k=0.02).items += [(torus((0.02, 1.47, 0), 0.30, 0.03), hat),
                              (round_cone((0.02, 1.45, 0), (0.02, 1.68, 0), 0.16, 0.12), hat)]
    s.group().items.append((capsule((0.55, 0.78, 0.05), (1.30, 0.62, 0.05), 0.012), leather))  # dizgin
    li = Light(dir=(-0.5, 0.6, 0.65), color=(1.15, 1.0, 0.78), sky=(0.45, 0.40, 0.30), rim_color=(1.0, 0.88, 0.6),
               ambient=0.48, shadow_k=4.0)
    return s, li, {"cam": (0.5, 0.35, 8.6), "target": (0.05, 0.05, 0.0), "fov": 30.0, "aspect": 0.82}


# =========================================================================== DEV İSKELET + SAVAŞÇI (kırmızı sis)

def _fog_overlay(top=0.35, bottom=0.85, col=(200, 40, 50), seed=9):
    def ov(chars, colors, phase):
        rows, cols = chars.shape
        rs = np.random.default_rng(seed)
        r0, r1 = int(rows * top), int(rows * bottom)
        for r in range(r0, r1):
            for c in range(0, cols, 2):
                v = math.sin(c * 0.11 + phase * 6.28 + r * 0.35) + 0.6 * math.sin(c * 0.05 - phase * 6.28 * 2 + r * 0.2)
                if v > 1.05 and chars[r, c] == 32 and rs.random() < 0.6:
                    chars[r, c] = ord("~" if v > 1.3 else "-")
                    k = 0.55 + 0.25 * (v - 1.05)
                    colors[r, c] = tuple(int(x * k) for x in col)
    return ov


def build_skeleton(ph: float):
    s = Scene()
    bone = s.mat((215, 205, 190), rim=0.4, pattern=_fur(18, 0.2))
    rock = s.mat((80, 70, 75), rim=0.3, pattern=_fur(9, 0.5))
    eyeg = s.mat((255, 70, 50), emissive=1.2 * (0.7 + 0.3 * math.sin(ph * 6.28)), glyph="*", priority=6, glyph_min=1)
    armor = s.mat((120, 125, 135), spec=0.8, rim=0.6)
    cape = s.mat((150, 30, 35), rim=0.4)
    water = s.mat((28, 45, 75), spec=0.9, shine=60, rim=0.1, outline=False)
    # uzak dev iskelet (kafatası + kaburgalar + kollar kayaya dayalı)
    sk = s.group(k=0.06)
    sk.items += [(ellipsoid((1.0, 1.35, -3.0), (0.62, 0.66, 0.58), None), bone),
                 (round_box((1.0, 0.82, -2.72), (0.34, 0.16, 0.30), 0.08), bone)]
    for sx in (-1, 1):
        s.group().items.append((sphere((1.0 + 0.22 * sx, 1.32, -2.47), 0.10), eyeg))
    rib = s.group(k=0.02)
    for i in range(5):
        y = 0.30 - i * 0.26
        rib.items.append((torus((1.0, y, -3.0), 0.62 - i * 0.04, 0.055, rot(90, 0, 0)), bone))
    rib.items.append((capsule((1.0, 0.65, -3.30), (1.0, -1.10, -3.30), 0.09), bone))
    for sx in (-1, 1):
        rib.items += [(capsule((1.0 + 0.75 * sx, 0.55, -3.0), (1.0 + 1.25 * sx, -0.35, -2.5), 0.09), bone),
                      (capsule((1.0 + 1.25 * sx, -0.35, -2.5), (1.0 + 1.35 * sx, -1.10, -2.0), 0.08), bone)]
    s.group(k=0.3).items += [(ellipsoid((1.0, -1.55, -3.0), (2.6, 0.6, 1.3), None), rock),
                             (ellipsoid((-1.8, -1.75, -2.0), (1.4, 0.7, 1.0), None), rock)]
    s.group().items.append((ellipsoid((0.2, -1.98, 0.4), (3.2, 0.03, 1.6), None), water))
    # öndeki küçük savaşçı (arkası dönük)
    w = s.group(k=0.05)
    w.items += [(ellipsoid((-1.25, -1.10, 1.6), (0.17, 0.25, 0.13), None), armor),
                (sphere((-1.25, -0.76, 1.6), 0.10), armor),
                (round_cone((-1.25, -0.95, 1.52), (-1.25, -1.65, 1.48), 0.16, 0.24), cape),
                (capsule((-1.32, -1.30, 1.6), (-1.34, -1.75, 1.6), 0.05), armor),
                (capsule((-1.18, -1.30, 1.6), (-1.16, -1.75, 1.6), 0.05), armor)]
    li = Light(dir=(-0.3, 0.6, 0.7), color=(1.0, 1.0, 1.1), sky=(0.40, 0.42, 0.55), rim_color=(1.0, 0.40, 0.35),
               ambient=0.48, shadow_k=4.0)
    return s, li, {"cam": (-0.8, 0.0, 7.2), "target": (0.0, -0.20, -1.0), "fov": 40.0, "aspect": 0.70,
                   "overlay": _fog_overlay()}
