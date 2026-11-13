"""Örnek HD varlıkları ÜRETİR (hepsi bu betikle, kendi ürettiğimiz parametrik/procedural kaynaklardan; harici görsel/mesh yok).

  1. hd_torus_knot_spin   : parametrik torus düğümü (OBJ üretilir → tools/hd_convert.py ile 48 karelik döner döngü)
  2. hd_poppy_field       : procedural, rüzgârla sallanan çimen + gelincik tarlası (24 karelik döngü, 10 FPS)
  3. hd_portrait_static   : QPainter ile çizilmiş stilize portre (durağan)

Lisans: bu betiğin ürettiği tüm veriler proje lisansı altındadır (CC0'a eşdeğer kullanım). Kaynak görsel/mesh yoktur.
Kullanım: python tools/make_hd_samples.py
"""

from __future__ import annotations

import colorsys
import math
import random
import sys
from pathlib import Path

import numpy as np

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "tools"))
import hd_convert as hc  # noqa: E402

ANIM = BASE / "assets" / "animations"
SAMPLES = BASE / "tools" / "samples"


# --------------------------------------------------------------------------- 1) torus düğümü

def make_torus_knot_obj(path: Path, p: int = 2, q: int = 3, segs: int = 160, sides: int = 14, tube: float = 0.23) -> None:
    ts = np.linspace(0, 2 * math.pi, segs, endpoint=False)

    def curve(t: float) -> np.ndarray:
        r = 2.0 + math.cos(q * t)
        return np.array([r * math.cos(p * t), r * math.sin(p * t), -math.sin(q * t)], np.float64)

    pts = [curve(t) for t in ts]
    verts, cols, faces = [], [], []
    for i, t in enumerate(ts):
        c = pts[i]
        tan = curve(t + 1e-3) - curve(t - 1e-3)
        tan /= np.linalg.norm(tan)
        ref = np.array([0.0, 0.0, 1.0]) if abs(tan[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        nrm = np.cross(tan, ref)
        nrm /= np.linalg.norm(nrm)
        bin_ = np.cross(tan, nrm)
        rgb = colorsys.hsv_to_rgb((i / segs * 2.0) % 1.0, 0.72, 1.0)  # düğüm boyunca gökkuşağı
        for k in range(sides):
            a = 2 * math.pi * k / sides
            verts.append(c + tube * (math.cos(a) * nrm + math.sin(a) * bin_))
            cols.append(rgb)
    for i in range(segs):
        j = (i + 1) % segs
        for k in range(sides):
            l = (k + 1) % sides
            a, b, c2, d = i * sides + k, j * sides + k, j * sides + l, i * sides + l
            faces.append((a, b, c2))
            faces.append((a, c2, d))
    lines = ["# parametrik torus düğümü (ASCII Mate, CC0)"]
    lines += [f"v {v[0]:.5f} {v[1]:.5f} {v[2]:.5f} {c[0]:.3f} {c[1]:.3f} {c[2]:.3f}" for v, c in zip(verts, cols)]
    lines += [f"f {a + 1} {b + 1} {c + 1}" for a, b, c in faces]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def sample_torus() -> None:
    obj = SAMPLES / "torus_knot.obj"
    make_torus_knot_obj(obj)
    hc.main([str(obj), "--out", str(ANIM / "space_and_3d"), "--id", "hd_torus_knot_spin",
             "--name", "HD Dönen Torus Düğümü", "--category", "Uzay & Bilim Kurgu",
             "--cols", "150", "--frames", "48", "--rotate-y", "360", "--tilt", "22", "--fps", "15",
             "--gamma", "0.85", "--edge-boost", "0.6", "--bg-threshold", "0.03"])


# --------------------------------------------------------------------------- 2) gelincik tarlası

def sample_poppy() -> None:
    R, C, N = 44, 190, 24
    rng = random.Random(2026)
    blades = []
    for layer, (n, hmin, hmax, base_row, bright) in enumerate(((330, 6, 13, R - 9, 0.45), (380, 8, 17, R - 5, 0.70), (420, 10, 22, R - 1, 1.0))):
        for _ in range(n):
            x0 = rng.uniform(-2, C + 2)
            h = rng.uniform(hmin, hmax)
            hue = rng.uniform(0.22, 0.34)
            rgb = colorsys.hsv_to_rgb(hue, rng.uniform(0.55, 0.85), rng.uniform(0.45, 0.85) * bright + 0.1)
            blades.append((layer, x0, h, base_row, rng.uniform(0, 6.28), tuple(int(v * 255) for v in rgb)))
    flowers = []
    for _ in range(46):
        layer = rng.choice((1, 2, 2))
        flowers.append((layer, rng.uniform(6, C - 6), rng.uniform(15, 25) if layer == 2 else rng.uniform(11, 17),
                        R - 1 if layer == 2 else R - 5, rng.uniform(0, 6.28), rng.random() < 0.18))
    chars_all, colors_all = [], []
    for k in range(N):
        ph = 2 * math.pi * k / N
        ch = np.full((R, C), 32, np.uint8)
        co = np.zeros((R, C, 3), np.uint8)

        def put(y: int, x: int, c: str, rgb) -> None:
            if 0 <= y < R and 0 <= x < C:
                ch[y, x] = ord(c)
                co[y, x] = rgb

        def sway(layer: int, x0: float, h: float, phase: float, t: float) -> float:
            return math.sin(ph + phase + x0 * 0.045) * (1.0 + 0.5 * layer) * 1.3 * (t * t)

        for layer in range(3):
            for (ly, x0, h, base, phase, rgb) in blades:
                if ly != layer:
                    continue
                prev = x0
                for y in range(int(h)):
                    t = y / max(h, 1.0)
                    x = x0 + sway(layer, x0, h, phase, t)
                    dx = x - prev
                    c = "|" if abs(dx) < 0.28 else ("/" if dx > 0 else "\\")
                    put(base - y, int(round(x)), c, rgb)
                    prev = x
            for (fy, fx, fh, base, phase, daisy) in flowers:
                if fy != layer:
                    continue
                top_x = fx + sway(layer, fx, fh, phase, 1.0)
                prev = fx
                for y in range(int(fh)):
                    t = y / fh
                    x = fx + sway(layer, fx, fh, phase, t)
                    put(base - y, int(round(x)), "|" if abs(x - prev) < 0.3 else ("/" if x > prev else "\\"), (60, 140, 60))
                    prev = x
                cx, cy = int(round(top_x)), base - int(fh)
                if daisy:
                    for dx, dy, c in ((-1, 0, "-"), (1, 0, "-"), (0, -1, "|"), (0, 1, "|"), (0, 0, "*")):
                        put(cy + dy, cx + dx, c, (250, 250, 235) if c != "*" else (255, 210, 60))
                else:
                    for dx, dy, c in ((-2, 0, "("), (-1, 0, "@"), (0, 0, "@"), (1, 0, "@"), (2, 0, ")"), (-1, -1, "("), (0, -1, "^"), (1, -1, ")"), (-1, 1, "\\"), (0, 1, "v"), (1, 1, "/")):
                        put(cy + dy, cx + dx, c, (225, 38, 48) if c not in "@" else (150, 15, 25))
        chars_all.append(ch)
        colors_all.append(co)
    hc.write_asset(ANIM / "nature_and_weather", "hd_poppy_field", "HD Gelincik Tarlası (Rüzgârlı)", "Doğa & Hava Durumu",
                   chars_all, colors_all, 10.0, tags=["gelincik", "çimen", "rüzgar"])
    print(f"[OK] hd_poppy_field {C}x{R}, {N} kare")


# --------------------------------------------------------------------------- 3) durağan portre

def sample_portrait() -> None:
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QBrush, QColor, QImage, QPainter, QPainterPath, QPen, QRadialGradient, QLinearGradient

    hc.ensure_qt()
    W, H = 720, 900
    img = QImage(W, H, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    # omuzlar
    sh = QLinearGradient(0, 640, 0, 900)
    sh.setColorAt(0, QColor(36, 98, 120))
    sh.setColorAt(1, QColor(14, 50, 70))
    path = QPainterPath()
    path.moveTo(40, 900)
    path.cubicTo(60, 720, 250, 700, 360, 700)
    path.cubicTo(470, 700, 660, 720, 680, 900)
    path.closeSubpath()
    p.fillPath(path, QBrush(sh))
    # boyun
    p.setPen(Qt.PenStyle.NoPen)
    neck = QLinearGradient(300, 600, 420, 600)
    neck.setColorAt(0, QColor(196, 140, 112))
    neck.setColorAt(0.5, QColor(232, 176, 144))
    neck.setColorAt(1, QColor(176, 122, 98))
    p.setBrush(QBrush(neck))
    p.drawRoundedRect(QRectF(300, 560, 120, 170), 30, 30)
    # saç (arka)
    hair = QRadialGradient(QPointF(360, 330), 300)
    hair.setColorAt(0, QColor(92, 52, 32))
    hair.setColorAt(1, QColor(30, 16, 12))
    p.setBrush(QBrush(hair))
    p.drawEllipse(QRectF(150, 70, 420, 520))
    # yüz
    face = QRadialGradient(QPointF(330, 340), 260)
    face.setColorAt(0, QColor(250, 205, 172))
    face.setColorAt(0.7, QColor(226, 170, 138))
    face.setColorAt(1, QColor(176, 118, 92))
    p.setBrush(QBrush(face))
    p.drawEllipse(QRectF(210, 160, 300, 400))
    # saç (ön, kâkül)
    bang = QPainterPath()
    bang.moveTo(200, 330)
    bang.cubicTo(190, 120, 480, 80, 530, 300)
    bang.cubicTo(470, 210, 340, 190, 250, 260)
    bang.closeSubpath()
    p.setBrush(QColor(70, 38, 24))
    p.drawPath(bang)
    # gözler
    for cx in (295, 425):
        p.setBrush(QColor(250, 246, 240))
        p.drawEllipse(QRectF(cx - 36, 330, 72, 36))
        iris = QRadialGradient(QPointF(cx, 348), 20)
        iris.setColorAt(0, QColor(70, 150, 120))
        iris.setColorAt(1, QColor(30, 80, 70))
        p.setBrush(QBrush(iris))
        p.drawEllipse(QRectF(cx - 17, 331, 34, 34))
        p.setBrush(QColor(8, 8, 10))
        p.drawEllipse(QRectF(cx - 7, 341, 14, 14))
        p.setPen(QPen(QColor(50, 28, 20), 5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(cx - 40, 316, 80, 40), 20 * 16, 140 * 16)
        p.drawLine(int(cx - 44), 296, int(cx + 40), 290)
        p.setPen(Qt.PenStyle.NoPen)
    # burun gölgesi, dudak, yanak
    p.setBrush(QColor(190, 130, 104, 150))
    p.drawEllipse(QRectF(340, 380, 40, 70))
    p.setBrush(QColor(210, 84, 92))
    p.drawEllipse(QRectF(318, 478, 84, 30))
    p.setBrush(QColor(255, 140, 130, 70))
    p.drawEllipse(QRectF(238, 410, 70, 50))
    p.drawEllipse(QRectF(412, 410, 70, 50))
    p.end()
    arr = hc.qimage_to_rgba(img)
    ramp = hc.build_ramp("auto")
    cols = 130
    rows = hc.grid_rows(W, H, cols)
    ch, co = hc.convert_rgba(arr, cols, rows, ramp, gamma=0.7, edge_boost=0.3, bg_threshold=0.03, color_lift=0.6)
    hc.write_asset(ANIM / "study_and_lofi", "hd_portrait_static", "HD Stilize Portre (Durağan)", "Ders & Lo-Fi Odak", [ch], [co], 1.0,
                   tags=["portre", "durağan"])
    print(f"[OK] hd_portrait_static {cols}x{rows}")


if __name__ == "__main__":
    sample_torus()
    sample_poppy()
    sample_portrait()
