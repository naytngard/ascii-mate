"""Hayvan/karakter SDF sahneleri (eski elipsoit modellerinin HD karşılıkları). Her `build_*` (faz) → Scene döner.

faz ∈ [0, 1): döngü içindeki konum (nefes, kuyruk, kulak, göz kırpma buradan türetilir).
"""

from __future__ import annotations

import math

import numpy as np

from sdf import Light, Scene, capsule, ellipsoid, rot, round_box, round_cone, sphere, torus, value_noise


# Gerçekçi stüdyo ışığı: yönlü anahtar ışık + yumuşak gölge + hafif gök dolgusu. Kontur olmadığından biçimi
# (kalp/satürn shader'larındaki gibi) yalnızca ışık-gölge geçişi anlatır; ortam ışığı düşük tutulur.
ASCII_LIGHT = Light(dir=(-0.50, 0.50, 0.70), color=(1.0, 0.95, 0.86), sky=(0.30, 0.32, 0.38), rim_color=(0.9, 0.85, 0.75),
                    ambient=0.22, shadow_k=5.0)


def _blink(ph: float, at: float = 0.78, width: float = 0.05) -> float:
    """0 = açık, 1 = kapalı (kısa göz kırpma)."""
    d = abs(((ph - at + 0.5) % 1.0) - 0.5)
    return max(0.0, 1.0 - d / width)


def _fur(scale=26.0, amp=0.28, seed=3):
    def pat(p, n):
        return (1.0 - amp / 2) + amp * value_noise(p, scale, seed)

    return pat


def _tabby_v(stripes=9.0, depth=0.22, seed=1, center=(0.0, 0.0)):
    """Gerçekçi tekir deseni: gövdeyi saran dikey/eğik çizgiler (yatay bant değil) + ince tüy gürültüsü."""
    cx, cz = center

    def pat(p, n):
        ang = np.arctan2(p[:, 2] - cz, p[:, 0] - cx)
        warp = 2.6 * value_noise(p, 3.0, seed) + 1.2 * p[:, 1]
        s = 0.5 + 0.5 * np.sin(ang * stripes + warp * 2.0)
        fur = 0.92 + 0.16 * value_noise(p, 46.0, seed + 7)
        return (1.0 - depth * np.clip((s - 0.55) * 4.0, 0.0, 1.0)) * fur

    return pat


def _furry(f, amount=0.012, scale=38.0, seed=2):
    """Yüzeye ince, düzensiz tüy pürüzü (gerçekçi doku; çizgi film pürüzsüzlüğü yerine)."""
    return lambda p: f(p) + amount * _fur_noise(p, scale, seed)


_NOISE_CACHE: dict = {}  # (ölçek, tohum) → gürültü; yalnızca son nokta dizisi için geçerli


def _fur_noise(p, scale: float, seed: int):
    """İki oktavlı tüy gürültüsü, nokta dizisi başına BİR kez hesaplanır. Bir sahnede onlarca parça aynı (ölçek, tohum)
    çiftini kullanır; her parça için yeniden hesaplamak derleme süresinin büyük kısmıydı (kedi: kare başına 78 sn)."""
    if _NOISE_CACHE.get("p") is not p:
        _NOISE_CACHE.clear()
        _NOISE_CACHE["p"] = p
    key = (scale, seed)
    n = _NOISE_CACHE.get(key)
    if n is None:
        n = (value_noise(p, scale, seed) - 0.5) + 0.5 * (value_noise(p, scale * 2.3, seed + 1) - 0.5)
        _NOISE_CACHE[key] = n
    return n


def _chain(points, r0, r1):
    """Noktalar boyunca incelen kapsül zinciri (kuyruk, boyun vb.)."""
    out = []
    n = len(points) - 1
    for i, (a, b) in enumerate(zip(points, points[1:])):
        ra = r0 + (r1 - r0) * i / n
        rb = r0 + (r1 - r0) * (i + 1) / n
        out.append(round_cone(a, b, ra, rb))
    return out


# =========================================================================== KEDİ (gerçekçi, tam boy oturan, 3/4)

def build_cat(ph: float) -> tuple[Scene, Light, dict]:
    """Gerçek oranlı tekir kedi: küçük kafa, badem gözler, üçgen kulaklar, oturan gövde, öne dolanan kuyruk."""
    s = Scene()
    w = 2 * math.pi * ph
    fur = s.mat((200, 130, 68), rim=0.25, pattern=_tabby_v(10.0, 0.26))
    pale = s.mat((236, 214, 182), rim=0.2, pattern=_fur(44, 0.16))
    inner = s.mat((205, 140, 130), rim=0.1)
    nose = s.mat((200, 120, 120), spec=0.3, shine=30, rim=0.05)
    eye = s.mat((175, 210, 80), spec=1.0, shine=120, rim=0.0, emissive=0.30)  # kedi gözü ışığı geri yansıtır
    pupil = s.mat((18, 18, 16), spec=0.9, shine=90, rim=0.0)
    lid = s.mat((120, 78, 45), rim=0.05)

    breath = 1.0 + 0.012 * math.sin(w)
    turn = rot(0, -28, 0)

    def T(p):
        return tuple((np.asarray(p, np.float64) @ turn.T).tolist())

    body = s.group(k=0.10)
    body.items += [
        (_furry(ellipsoid(T((0, 1.00, 0.10)), (0.27 * breath, 0.42, 0.27 * breath), turn)), fur),   # göğüs
        (_furry(ellipsoid(T((0, 0.48, -0.18)), (0.36, 0.34, 0.44), turn)), fur),                    # kalça/gövde
        (_furry(ellipsoid(T((0.27, 0.36, -0.08)), (0.15, 0.27, 0.30), turn)), fur),                 # arka bacak (sağ)
        (_furry(ellipsoid(T((-0.27, 0.36, -0.08)), (0.15, 0.27, 0.30), turn)), fur),                # arka bacak (sol)
        (_furry(ellipsoid(T((0, 0.98, 0.26)), (0.17, 0.30, 0.10), turn), 0.008), pale),             # göğüs beyazı
        (_furry(capsule(T((0, 1.22, 0.12)), T((0, 1.46, 0.18)), 0.16)), fur),                      # boyun
    ]
    for sx in (-1, 1):
        body.items += [
            (_furry(round_cone(T((0.11 * sx, 0.95, 0.24)), T((0.12 * sx, 0.12, 0.36)), 0.075, 0.058), 0.008), fur),  # ön bacak
            (ellipsoid(T((0.12 * sx, 0.055, 0.42)), (0.068, 0.045, 0.095), turn), pale),           # ön pati
            (ellipsoid(T((0.30 * sx, 0.05, 0.20)), (0.07, 0.045, 0.13), turn), fur),              # arka pati
        ]
    sway = 0.10 * math.sin(w + 0.6)
    tail_pts = [T((0.28, 0.16, -0.50)), T((0.52, 0.09, -0.12)), T((0.50, 0.07, 0.28)),
                T((0.30 + 0.5 * sway, 0.07, 0.52)), T((0.02 + sway, 0.08 + 0.03 * max(0.0, math.sin(w)), 0.60))]
    tail = s.group(k=0.04)
    tail.items += [(_furry(f, 0.008), fur) for f in _chain(tail_pts, 0.062, 0.042)]

    # baş: gövdeden bağımsız, izleyiciye dönük; hafif eğilip yavaşça bakınır
    hr = rot(-4 + 2 * math.sin(w * 2), -6 + 10 * math.sin(w), 3 * math.sin(w + 1.0))
    hc = np.array(T((0, 1.58, 0.22)))

    def H(p):
        return tuple((hc + np.asarray(p, np.float64) @ hr.T).tolist())

    head = s.group(k=0.06)
    head.items += [
        (_furry(ellipsoid(H((0, 0.02, -0.02)), (0.235, 0.205, 0.215), hr), 0.007), fur),            # kafatası
        (_furry(ellipsoid(H((0.115, -0.07, 0.10)), (0.12, 0.10, 0.11), hr), 0.006), fur),          # yanaklar
        (_furry(ellipsoid(H((-0.115, -0.07, 0.10)), (0.12, 0.10, 0.11), hr), 0.006), fur),
        (ellipsoid(H((0.04, -0.085, 0.185)), (0.052, 0.042, 0.050), hr), pale),                     # bıyık yastıkları
        (ellipsoid(H((-0.04, -0.085, 0.185)), (0.052, 0.042, 0.050), hr), pale),
        (ellipsoid(H((0, -0.125, 0.160)), (0.042, 0.028, 0.040), hr), pale),                        # çene
        (capsule(H((0, 0.035, 0.175)), H((0, -0.035, 0.215)), 0.032), fur),                         # burun köprüsü
    ]
    s.group().items.append((ellipsoid(H((0, -0.045, 0.232)), (0.024, 0.016, 0.014), hr), nose))
    ears = s.group(k=0.015)
    twitch = 14.0 * max(0.0, math.sin((ph - 0.30) * 2 * math.pi * 4)) if 0.30 < ph < 0.42 else 0.0
    for sx in (-1, 1):
        er = hr @ rot(-8, 0, -14 * sx + (twitch if sx < 0 else 0.0) * 0.6)
        base = H((0.125 * sx, 0.150, 0.00))
        tip = H((0.175 * sx, 0.345, -0.03))
        ears.items.append((round_cone(base, tip, 0.085, 0.012), fur))
        ears.items.append((round_cone(H((0.123 * sx, 0.165, 0.035)), H((0.165 * sx, 0.315, 0.005)), 0.050, 0.008), inner))
        del er
    bl = _blink(ph, 0.72, 0.035)
    eyes = s.group(k=0.0)
    for sx in (-1, 1):
        c = H((0.090 * sx, 0.010, 0.186))
        er = hr @ rot(0, 22 * sx, 12 * sx)  # badem göz: dış köşe hafif yukarı, yüz eğrisine oturur
        if bl > 0.5:
            eyes.items.append((ellipsoid(c, (0.054, 0.011, 0.030), er), lid))
        else:
            eyes.items.append((ellipsoid(c, (0.054, 0.038 * (1 - 0.6 * bl), 0.030), er), eye))
            eyes.items.append((ellipsoid(H((0.090 * sx, 0.010, 0.208)), (0.010, 0.031 * (1 - 0.6 * bl), 0.014), hr), pupil))
    return s, ASCII_LIGHT, {"cam": (0.32, 1.72, 2.25), "target": (0.02, 1.47, 0.10), "fov": 30.0, "aspect": 0.95}


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


def _mottled(base_amp=0.30, scale=14.0, seed=5, bars=0.0):
    """Benekli tüy deseni (baykuş/kurt): iki ölçekli gürültü + isteğe bağlı ince yatay çizgiler (göğüs)."""
    def pat(p, n):
        a = value_noise(p, scale, seed)
        b = value_noise(p, scale * 3.1, seed + 3)
        v = 1.0 - base_amp * np.clip((a - 0.45) * 2.5, 0, 1) - 0.12 * (b > 0.6)
        if bars:
            v = v - bars * (np.sin(p[:, 1] * 70 + 4 * a) > 0.75)
        return v

    return pat


# =========================================================================== BAYKUŞ (gerçekçi puhu, dalda)

def build_owl(ph: float):
    """Puhu (büyük boynuzlu baykuş): kulak tüyleri, pas rengi yüz diski, beyaz gerdan, benekli/çizgili göğüs,
    sarı-turuncu gözler; başını yavaşça sağa sola çevirir ve göz kırpar."""
    s = Scene()
    w = 2 * math.pi * ph
    brown = s.mat((138, 100, 66), rim=0.2, pattern=_mottled(0.35, 12.0, 5))
    wing = s.mat((105, 74, 48), rim=0.15, pattern=_mottled(0.40, 10.0, 8))
    breast = s.mat((200, 172, 132), rim=0.2, pattern=_mottled(0.25, 16.0, 6, bars=0.22))
    disc = s.mat((190, 128, 76), rim=0.15, pattern=_fur(50, 0.18))
    rimd = s.mat((60, 42, 30), rim=0.05)
    throat = s.mat((232, 222, 200), rim=0.15)
    beak = s.mat((52, 48, 46), spec=0.6, shine=50)
    eye = s.mat((250, 175, 30), spec=1.0, shine=140, emissive=0.35)
    pupil = s.mat((10, 10, 10), spec=1.0, shine=140)
    branch = s.mat((92, 68, 48), rim=0.1, pattern=_mottled(0.45, 9.0, 11))
    talon = s.mat((70, 64, 58), spec=0.4)
    breath = 1.0 + 0.012 * math.sin(w)

    body = s.group(k=0.10)
    body.items += [
        (_furry(ellipsoid((0, 0.80, 0.0), (0.40 * breath, 0.60, 0.36 * breath), None), 0.014, 30), brown),
        (_furry(ellipsoid((0, 0.72, 0.17), (0.30, 0.48, 0.22), None), 0.014, 30), breast),
        (_furry(ellipsoid((-0.34, 0.78, -0.06), (0.15, 0.52, 0.30), rot(0, 0, -6)), 0.012, 26), wing),
        (_furry(ellipsoid((0.34, 0.78, -0.06), (0.15, 0.52, 0.30), rot(0, 0, 6)), 0.012, 26), wing),
        (ellipsoid((0, 0.22, -0.20), (0.16, 0.14, 0.10), rot(30, 0, 0)), wing),                     # kuyruk ucu
    ]
    yaw = 28 * math.sin(w)  # baykuşlar başı gövdeden bağımsız çevirir
    hr = rot(-4, yaw, 4 * math.sin(w * 2))
    H = _H((0, 1.42, 0.02), hr)
    head = s.group(k=0.08)
    head.items += [
        (_furry(ellipsoid(H((0, 0.0, 0.0)), (0.30, 0.26, 0.27), hr), 0.010, 34), brown),
        (_furry(ellipsoid(H((0.115, -0.01, 0.17)), (0.13, 0.14, 0.07), hr), 0.006, 50), disc),       # yüz diski
        (_furry(ellipsoid(H((-0.115, -0.01, 0.17)), (0.13, 0.14, 0.07), hr), 0.006, 50), disc),
        (ellipsoid(H((0, -0.20, 0.15)), (0.12, 0.05, 0.08), hr), throat),                           # beyaz gerdan
    ]
    for sx in (-1, 1):  # yüz diskinin koyu kenarı ve kulak tüyleri
        head.items.append((ellipsoid(H((0.235 * sx, -0.02, 0.10)), (0.035, 0.15, 0.06), hr @ rot(0, 0, 8 * sx)), rimd))
        head.items.append((_furry(round_cone(H((0.15 * sx, 0.20, 0.0)), H((0.22 * sx, 0.40, -0.04)), 0.060, 0.010), 0.006), wing))
    feat = s.group()
    bl = _blink(ph, 0.83, 0.03)
    for sx in (-1, 1):
        c = H((0.108 * sx, 0.015, 0.255))
        if bl > 0.5:
            feat.items.append((ellipsoid(c, (0.062, 0.014, 0.035), hr), disc))
        else:
            feat.items.append((ellipsoid(c, (0.062, 0.060 * (1 - 0.7 * bl), 0.035), hr), eye))
            feat.items.append((ellipsoid(H((0.108 * sx, 0.015, 0.285)), (0.032, 0.032 * (1 - 0.7 * bl), 0.012), hr), pupil))
        feat.items.append((ellipsoid(H((0.10 * sx, 0.092, 0.250)), (0.080, 0.018, 0.03), hr @ rot(0, 0, -18 * sx)), throat))  # kaş
    feat.items.append((round_cone(H((0, -0.04, 0.290)), H((0, -0.12, 0.305)), 0.034, 0.007), beak))
    perch = s.group(k=0.02)
    perch.items.append((_furry(capsule((-1.3, 0.12, 0.10), (1.3, 0.08, -0.05), 0.085), 0.02, 14), branch))
    perch.items.append((capsule((0.7, 0.10, 0.0), (1.05, 0.30, -0.15), 0.04), branch))
    for sx in (-1, 1):
        for k in (-0.05, 0.0, 0.05):
            perch.items.append((capsule((0.12 * sx + k, 0.22, 0.17), (0.12 * sx + k * 1.3, 0.16, 0.24), 0.018), talon))
    return s, ASCII_LIGHT, {"cam": (0.7, 1.15, 4.3), "target": (0.0, 0.92, 0.0), "fov": 30.0, "aspect": 1.12}


# =========================================================================== KÖPEK (gerçekçi golden retriever büstü)

def build_dog(ph: float):
    """Golden retriever: uzun burun, belirgin alın kırımı, sarkık kulaklar, uzun tüylü göğüs, hafif soluma."""
    s = Scene()
    w = 2 * math.pi * ph
    gold = s.mat((214, 158, 86), rim=0.25, pattern=_fur(40, 0.22))
    light_m = s.mat((232, 196, 132), rim=0.2, pattern=_fur(46, 0.18))
    ear_m = s.mat((165, 98, 46), rim=0.2, pattern=_fur(52, 0.30))
    nose = s.mat((34, 28, 28), spec=0.9, shine=70, rim=0.0)
    eye = s.mat((60, 34, 20), spec=1.0, shine=60, rim=0.0, emissive=0.05)
    lip = s.mat((60, 40, 38), rim=0.0)
    tongue = s.mat((222, 110, 118), spec=0.5, shine=40, rim=0.05)
    pant = 0.5 + 0.5 * math.sin(w * 3)
    breath = 1.0 + 0.015 * math.sin(w * 3)

    body = s.group(k=0.12)
    body.items += [
        (_furry(ellipsoid((0, 0.80, -0.05), (0.42 * breath, 0.55, 0.36 * breath), None), 0.03, 26), gold),  # göğüs/omuz
        (_furry(ellipsoid((0, 0.88, 0.20), (0.26, 0.40, 0.16), None), 0.035, 24), light_m),                # göğüs tüyü
        (_furry(capsule((0, 1.05, 0.02), (0, 1.42, 0.10), 0.22), 0.025, 26), gold),                         # boyun
    ]
    hr = rot(-6 + 3 * math.sin(w), 42 + 6 * math.sin(w + 0.4), -3 * math.sin(w + 1.3))  # 3/4 profil: namlu görünür
    H = _H((0, 1.55, 0.14), hr)
    head = s.group(k=0.07)
    head.items += [
        (_furry(ellipsoid(H((0, 0.03, -0.03)), (0.215, 0.195, 0.225), hr), 0.010), gold),           # kafatası
        (_furry(ellipsoid(H((0, 0.07, 0.12)), (0.15, 0.10, 0.12), hr), 0.006), gold),              # alın / kaş çıkıntısı
        (round_cone(H((0, -0.04, 0.14)), H((0, -0.075, 0.36)), 0.115, 0.080), light_m),           # burun (namlu)
        (ellipsoid(H((0.065, -0.12, 0.27)), (0.075, 0.07, 0.09), hr), light_m),                   # dudak sarkıkları
        (ellipsoid(H((-0.065, -0.12, 0.27)), (0.075, 0.07, 0.09), hr), light_m),
        (ellipsoid(H((0, -0.14 - 0.02 * pant, 0.25)), (0.06, 0.035, 0.08), hr @ rot(14 * pant, 0, 0)), light_m),  # alt çene
    ]
    feat = s.group(k=0.0)
    feat.items += [
        (ellipsoid(H((0, -0.050, 0.425)), (0.050, 0.036, 0.034), hr), nose),
        (capsule(H((0, -0.085, 0.43)), H((0, -0.12, 0.40)), 0.008), lip),
        (ellipsoid(H((0, -0.185 - 0.03 * pant, 0.33)), (0.042, 0.016, 0.060 + 0.02 * pant), hr @ rot(28 + 10 * pant, 0, 0)), tongue),
    ]
    bl = _blink(ph, 0.58, 0.03)
    for sx in (-1, 1):
        feat.items.append((ellipsoid(H((0.095 * sx, 0.040, 0.178)), (0.040, 0.034 * (1 - 0.85 * bl) + 0.004, 0.024), hr @ rot(0, 25 * sx, 0)),
                           eye if bl < 0.5 else ear_m))
    ears = s.group(k=0.01)
    flop = 5 * math.sin(w * 2)
    for sx in (-1, 1):
        er = hr @ rot(0, 0, (14 + flop) * sx)
        ears.items.append((_furry(ellipsoid(H((0.215 * sx, -0.07, -0.06)), (0.055, 0.175, 0.125), er), 0.014, 50), ear_m))
    li = Light(dir=(0.35, 0.55, 0.75), color=(1.0, 0.95, 0.86), sky=(0.30, 0.32, 0.38), rim_color=(0.9, 0.85, 0.75),
               ambient=0.22, shadow_k=5.0)
    return s, li, {"cam": (-0.35, 1.66, 2.45), "target": (0.08, 1.38, 0.10), "fov": 30.0, "aspect": 0.92}


# =========================================================================== TİLKİ (gerçekçi kızıl tilki, oturan, 3/4)

def build_fox(ph: float):
    """Kızıl tilki: ince uzun burun, büyük sivri kulaklar (arkası siyah), beyaz yanak/göğüs, siyah 'çoraplı' bacaklar,
    öne dolanan gür, beyaz uçlu kuyruk."""
    s = Scene()
    w = 2 * math.pi * ph
    red = s.mat((214, 104, 40), rim=0.25, pattern=_fur(40, 0.24))
    white = s.mat((238, 230, 218), rim=0.2, pattern=_fur(48, 0.14))
    black = s.mat((48, 34, 30), rim=0.1, pattern=_fur(40, 0.2))
    ear_in = s.mat((176, 140, 120), rim=0.05, pattern=_fur(50, 0.2))
    nose = s.mat((26, 22, 22), spec=0.9, shine=70)
    eye = s.mat((205, 140, 40), spec=1.0, shine=120, emissive=0.20)
    pupil = s.mat((15, 12, 10), spec=0.8, shine=80)
    breath = 1.0 + 0.012 * math.sin(w)
    turn = rot(0, 32, 0)

    def T(p):
        return tuple((np.asarray(p, np.float64) @ turn.T).tolist())

    body = s.group(k=0.09)
    body.items += [
        (_furry(ellipsoid(T((0, 0.95, 0.05)), (0.22 * breath, 0.38, 0.22 * breath), turn), 0.016), red),   # göğüs
        (_furry(ellipsoid(T((0, 0.48, -0.20)), (0.30, 0.30, 0.38), turn), 0.016), red),                   # gövde/kalça
        (_furry(ellipsoid(T((0, 0.92, 0.19)), (0.13, 0.30, 0.08), turn), 0.012), white),                  # göğüs beyazı
        (_furry(capsule(T((0, 1.12, 0.06)), T((0, 1.30, 0.14)), 0.14), 0.016), red),                      # boyun
    ]
    for sx in (-1, 1):
        body.items += [
            (_furry(ellipsoid(T((0.22 * sx, 0.36, -0.12)), (0.12, 0.24, 0.26), turn), 0.014), red),       # arka bacak
            (round_cone(T((0.09 * sx, 0.85, 0.16)), T((0.09 * sx, 0.40, 0.24)), 0.058, 0.045), red),       # ön bacak üst
            (round_cone(T((0.09 * sx, 0.40, 0.24)), T((0.10 * sx, 0.06, 0.28)), 0.045, 0.040), black),    # siyah çorap
            (ellipsoid(T((0.10 * sx, 0.04, 0.33)), (0.05, 0.035, 0.08), turn), black),                    # pati
        ]
    sway = 0.08 * math.sin(w + 0.9)
    tail_pts = [T((-0.10, 0.25, -0.52)), T((-0.42, 0.13, -0.30)), T((-0.48, 0.12, 0.10)),
                T((-0.30 + sway, 0.14, 0.42)), T((-0.02 + 1.5 * sway, 0.16, 0.56))]
    tail = s.group(k=0.08)
    segs = _chain(tail_pts, 0.10, 0.15)
    tail.items += [(_furry(f, 0.03, 22), red) for f in segs[:-1]]
    tail.items.append((_furry(round_cone(tail_pts[-2], tail_pts[-1], 0.14, 0.09), 0.03, 22), white))  # beyaz uç

    hr = turn @ rot(-3 + 2 * math.sin(w * 2), -54 + 9 * math.sin(w), 3 * math.sin(w + 0.7))  # baş 3/4: gözler ve burun görünür
    hc = np.array(T((0, 1.40, 0.16)))
    K = 1.5  # baş ölçeği (gerçek tilkide baş gövdeye göre iridir)

    def H(p):
        return tuple((hc + K * np.asarray(p, np.float64) @ hr.T).tolist())

    def hE(c, r, R=None):  # baş içi: yarıçaplar da ölçeklenir
        return ellipsoid(c, tuple(K * v for v in r), R)

    def hRC(a, b, r1, r2):
        return round_cone(a, b, K * r1, K * r2)

    head = s.group(k=0.05 * K)
    head.items += [
        (_furry(hE(H((0, 0.02, -0.02)), (0.165, 0.145, 0.165), hr), 0.007), red),                   # kafatası
        (_furry(hE(H((0.105, -0.075, 0.03)), (0.085, 0.065, 0.085), hr), 0.012), white),           # beyaz yanaklar
        (_furry(hE(H((-0.105, -0.075, 0.03)), (0.085, 0.065, 0.085), hr), 0.012), white),
        (hRC(H((0, -0.025, 0.10)), H((0, -0.065, 0.33)), 0.075, 0.030), red),                      # ince uzun burun
        (hRC(H((0, -0.075, 0.10)), H((0, -0.085, 0.30)), 0.055, 0.022), white),                   # alt çene
    ]
    s.group().items.append((sphere(H((0, -0.058, 0.355)), K * 0.030), nose))
    ears = s.group(k=0.012 * K)
    tw = 12 * max(0.0, math.sin((ph - 0.25) * 2 * math.pi * 4)) if 0.25 < ph < 0.37 else 0.0
    for sx in (-1, 1):
        base = H((0.095 * sx, 0.115, -0.03))
        tip = H((0.165 * sx, 0.355 - 0.01 * tw * (sx > 0), -0.06 - 0.004 * tw * (sx > 0)))
        ears.items.append((hRC(base, tip, 0.075, 0.012), black))                                   # kulak arkası siyah
        ears.items.append((hRC(H((0.093 * sx, 0.125, 0.0)), H((0.155 * sx, 0.315, -0.03)), 0.058, 0.010), red))
        ears.items.append((hRC(H((0.092 * sx, 0.13, 0.030)), H((0.145 * sx, 0.27, 0.000)), 0.028, 0.006), ear_in))
    bl = _blink(ph, 0.66, 0.03)
    eyes = s.group()
    for sx in (-1, 1):
        er = hr @ rot(0, 28 * sx, 18 * sx)  # çekik badem göz
        c = H((0.070 * sx, 0.035, 0.125))
        if bl > 0.5:
            eyes.items.append((hE(c, (0.038, 0.008, 0.022), er), black))
        else:
            eyes.items.append((hE(c, (0.038, 0.022, 0.024), er), eye))
            eyes.items.append((hE(H((0.072 * sx, 0.035, 0.142)), (0.006, 0.018, 0.010), hr), pupil))
    return s, ASCII_LIGHT, {"cam": (0.0, 1.15, 4.3), "target": (0.0, 0.92, 0.0), "fov": 30.0, "aspect": 1.08}


# =========================================================================== KAMP ATEŞİ BAŞINDA KURT (gerçekçi, profil)

def build_wolf(ph: float):
    """Gri kurt ateşe dönük oturur: uzun burun, dik kulaklar, kalın boyun yelesi, koyu sırt, gür kuyruk.
    Sahne ateşin turuncu ışığı (yandan, alçak) ve soğuk ay dolgusu ile aydınlanır; alevler titrer."""
    s = Scene()
    w = 2 * math.pi * ph
    grey = s.mat((150, 148, 146), rim=0.3, pattern=_mottled(0.25, 14.0, 21))
    saddle = s.mat((88, 84, 82), rim=0.25, pattern=_mottled(0.30, 12.0, 22))
    pale = s.mat((222, 214, 200), rim=0.25, pattern=_fur(44, 0.16))
    nose = s.mat((25, 22, 22), spec=0.9, shine=60)
    eye = s.mat((230, 170, 60), spec=1.0, shine=120, emissive=0.45)
    log = s.mat((92, 60, 38), rim=0.1, pattern=_mottled(0.4, 10.0, 31))
    ember = s.mat((255, 110, 30), emissive=1.1, rim=0.0)
    # düşük emisyon: sahne koyu olduğundan otomatik pozlama (~2,8×) rengi zaten parlatır; yüksek emisyonda
    # kırmızı-turuncu kanal taşıp alevin tamamı sarıya dönüyordu
    flame_o = s.mat((235, 70, 14), emissive=0.34, rim=0.0)
    flame_y = s.mat((255, 180, 60), emissive=0.50, rim=0.0)
    stone = s.mat((90, 86, 84), rim=0.1, pattern=_mottled(0.3, 8.0, 41))
    ground = s.mat((52, 54, 48), rim=0.0, pattern=_fur(5, 0.4))
    breath = 1.0 + 0.012 * math.sin(w)

    b = s.group(k=0.10)
    b.items += [
        (_furry(ellipsoid((-0.05, 0.92, 0.0), (0.30, 0.44 * breath, 0.27), rot(0, 0, -22)), 0.02, 26), grey),   # göğüs
        (_furry(ellipsoid((-0.48, 0.45, 0.0), (0.42, 0.32, 0.34), None), 0.02, 26), grey),                       # kalça
        (_furry(ellipsoid((-0.30, 0.86, 0.0), (0.30, 0.30, 0.22), rot(0, 0, -30)), 0.02, 22), saddle),           # koyu sırt
        (_furry(ellipsoid((0.10, 0.95, 0.0), (0.16, 0.36, 0.20), rot(0, 0, -15)), 0.03, 22), pale),             # açık göğüs
        (_furry(capsule((0.0, 1.10, 0.0), (0.20, 1.42, 0.0), 0.22), 0.035, 20), grey),                          # boyun yelesi
        (_furry(ellipsoid((-0.40, 0.30, 0.20), (0.22, 0.20, 0.14), None), 0.015), grey),                         # arka bacak
    ]
    for sz in (-0.11, 0.11):
        b.items += [
            (round_cone((0.08, 0.80, sz), (0.16, 0.08, sz), 0.07, 0.045), grey if sz > 0 else saddle),           # ön bacaklar
            (ellipsoid((0.21, 0.04, sz), (0.08, 0.04, 0.05), None), pale),
        ]
    b.items.append((ellipsoid((-0.10, 0.04, 0.26), (0.10, 0.04, 0.06), None), pale))                         # arka pati
    tail = s.group(k=0.06)
    sw = 0.06 * math.sin(w + 1.2)
    tail_pts = [(-0.82, 0.32, -0.05), (-1.05, 0.14, 0.05), (-0.95, 0.07, 0.30), (-0.62 + sw, 0.07, 0.42)]
    tail.items += [(_furry(f, 0.035, 20), saddle if i == 0 else grey) for i, f in enumerate(_chain(tail_pts, 0.10, 0.12))]

    hr = rot(0, 0, -4 + 3 * math.sin(w)) @ rot(0, 8 * math.sin(w), 0)  # profil; başı hafifçe kaldırıp çevirir
    H = _H((0.30, 1.55, 0.0), hr)
    head = s.group(k=0.06)
    head.items += [
        (_furry(ellipsoid(H((0, 0, 0)), (0.18, 0.15, 0.15), hr), 0.01), grey),                                  # kafatası
        (round_cone(H((0.10, -0.03, 0)), H((0.38, -0.09, 0)), 0.095, 0.050), grey),                             # uzun burun
        (round_cone(H((0.10, -0.08, 0)), H((0.34, -0.13, 0)), 0.070, 0.035), pale),                             # alt çene
        (_furry(ellipsoid(H((0.02, -0.08, 0)), (0.14, 0.09, 0.13), hr), 0.015), pale),                         # yanak tüyü
    ]
    ears = s.group(k=0.02)
    for sz in (-0.075, 0.075):
        ears.items.append((round_cone(H((-0.06, 0.10, sz)), H((-0.10, 0.30, sz * 1.15)), 0.065, 0.012), saddle))
    f = s.group()
    f.items.append((sphere(H((0.405, -0.075, 0)), 0.035), nose))
    bl = _blink(ph, 0.8, 0.03)
    for sz in (-0.08, 0.08):
        f.items.append((ellipsoid(H((0.13, 0.03, sz)), (0.028, 0.014 * (1 - 0.8 * bl) + 0.003, 0.015), hr @ rot(0, 0, -12)),
                        eye if bl < 0.5 else saddle))
    # ateş (sağda): taş halka, çapraz kütükler, titreyen alevler ve közler
    fire = s.group(k=0.0)
    FX = 1.55
    for i in range(9):
        a = 2 * math.pi * i / 9
        fire.items.append((ellipsoid((FX + 0.36 * math.cos(a), 0.04, 0.36 * math.sin(a)), (0.10, 0.07, 0.09), None), stone))
    fire.items += [(capsule((FX - 0.30, 0.10, 0.18), (FX + 0.28, 0.16, -0.12), 0.055), log),
                   (capsule((FX - 0.26, 0.15, -0.16), (FX + 0.30, 0.10, 0.16), 0.055), log)]
    # alev dilleri: ince, ayrı ayrı titreyen, uçları kıvrılan; dışta kızıl-turuncu, içte sarı çekirdek
    fl = s.group(k=0.035)
    core = s.group(k=0.03)
    tongues = ((0.0, 0.0, 0.70), (-0.12, 0.05, 0.46), (0.11, -0.04, 0.52), (0.04, 0.10, 0.38), (-0.06, -0.09, 0.40),
               (0.15, 0.07, 0.30), (-0.16, -0.02, 0.28))
    for i, (dx, dz, hgt) in enumerate(tongues):
        fh = hgt * (0.78 + 0.24 * math.sin(w * 4 + i * 1.9) + 0.10 * math.sin(w * 9 + i * 2.3))
        wob = 0.06 * math.sin(w * 3 + i * 1.3)
        base = (FX + dx, 0.17, dz)
        mid = (FX + dx + wob * 0.5, 0.17 + 0.5 * fh, dz)
        tip = (FX + dx + wob * 1.6, 0.17 + fh, dz + 0.02 * math.sin(w * 5 + i))
        fl.items.append((round_cone(base, mid, 0.095, 0.050), flame_o))
        fl.items.append((round_cone(mid, tip, 0.045, 0.004), flame_o))
        if hgt > 0.35:
            core.items.append((round_cone((FX + dx * 0.7, 0.17, dz * 0.7 + 0.05), (FX + dx * 0.7 + wob, 0.17 + 0.45 * fh, dz * 0.7 + 0.05), 0.045, 0.006), flame_y))
    s.group().items.append((ellipsoid((FX, 0.14, 0.0), (0.18, 0.05, 0.15), None), ember))
    s.group().items.append((ellipsoid((0.4, -0.05, 0.0), (2.6, 0.06, 1.2), None), ground))
    flick = 0.92 + 0.08 * math.sin(w * 4) + 0.04 * math.sin(w * 9)
    li = Light(dir=(0.85, 0.30, 0.42), color=(1.20 * flick, 0.66 * flick, 0.30 * flick), sky=(0.14, 0.18, 0.30),
               rim_color=(0.5, 0.6, 0.9), ambient=0.16, shadow_k=6.0)
    return s, li, {"cam": (0.45, 1.05, 5.4), "target": (0.38, 0.72, 0.0), "fov": 30.0, "aspect": 0.62,
                   "overlay": _spark_overlay(ph)}


def _spark_overlay(ph: float, n: int = 22, seed: int = 13, rise: float = 0.55):
    """Ateşten yükselen kıvılcımlar (hücre uzayında). Ateş, en parlak sarı-turuncu hücrelerden bulunur; kıvılcımlar
    döngüyle senkron yükselir (faz 0 ve 1 aynı kare → kesintisiz döngü), yükseldikçe söner."""
    def ov(chars: np.ndarray, colors: np.ndarray, phase: float) -> None:
        c = colors.astype(np.int32)
        hot = (c[..., 0] > 220) & (c[..., 1] > 150) & (c[..., 2] < 140) & (chars != 32)
        if not hot.any():
            return
        rr, cc = np.nonzero(hot)
        top, cx = int(rr.min()), float(np.median(cc))
        rows, cols = chars.shape
        span = max(4, int(rows * rise))
        rs = np.random.default_rng(seed)
        for k in range(n):
            off, sp, amp, fq, dx = rs.random(), int(rs.integers(1, 3)), rs.uniform(0.5, 2.5), rs.uniform(1, 3), rs.uniform(-3, 3)
            t = (phase * sp + off) % 1.0
            y = int(round(top - t * span))
            x = int(round(cx + dx + amp * math.sin(2 * math.pi * (fq * t + off))))
            if 0 <= y < rows and 0 <= x < cols and chars[y, x] == 32:
                fade = 1.0 - t
                chars[y, x] = ord("*" if fade > 0.7 else ("+" if fade > 0.4 else "."))
                colors[y, x] = (255, int(120 + 110 * fade), int(40 * fade))

    return ov


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
