"""3B ASCII hayvan/karakter modelleri (ascii_models motoru üzerinde). Doğrudan değil, procedural_engine üzerinden içe aktarılır."""

from __future__ import annotations

import math
from typing import Any, Dict, Optional

from src.core import ascii_models as E
from src.core.ascii_models import Ell, ModelRenderer, register

FUR = (232, 160, 92)
FUR_DARK = (190, 120, 62)
CREAM = (250, 228, 196)
PINK = (255, 140, 170)
GREEN = (110, 245, 150)
INK = (60, 40, 40)


def _blink(t: float, period: float, dur: float = 0.18, phase: float = 0.0) -> bool:
    return ((t + phase) % period) > (period - dur)


@register("cat_bust_3d", 46, 24)
class CatBust(ModelRenderer):
    extent = (1.0, 1.08)
    center = (0.0, -0.02)
    sway = 0.30
    sway_speed = 0.7

    def build(self) -> None:
        # grup 1: baş, grup 2: kuyruk
        self.body = self.add((0.0, -0.70, -0.04), (0.50, 0.44, 0.38), FUR)
        self.add((0.0, -0.36, 0.08), (0.33, 0.07, 0.28), (255, 90, 120), flat=True, outline=False)  # tasma
        self.add((0.0, 0.10, 0.0), (0.58, 0.48, 0.50), FUR, group=1)  # baş
        for s in (-1.0, 1.0):
            self.add((s * 0.33, 0.66, -0.02), (0.15, 0.30, 0.07), FUR, rot=(0, 0, 0.30 * s), group=1)  # kulak
            self.add((s * 0.32, 0.62, 0.05), (0.075, 0.19, 0.04), PINK, rot=(0, 0, 0.30 * s), group=1, outline=False)
        self.add((0.0, -0.05, 0.40), (0.24, 0.16, 0.14), CREAM, group=1)  # ağız çevresi
        self.eyes = [
            self.add((s * 0.23, 0.20, 0.42), (0.10, 0.075, 0.08), GREEN, chars=("o", "O", "@"), group=1, outline=False)
            for s in (-1.0, 1.0)
        ]
        self.add((0.0, 0.04, 0.52), (0.06, 0.04, 0.04), PINK, chars=("v", "v", "v"), group=1, outline=False)
        self.mark((0.0, -0.09, 0.53), "w", (170, 80, 100), group=1)
        for s in (-1.0, 1.0):
            self.stroke((s * 0.24, -0.02, 0.50), (s * 0.80, 0.05, 0.38), (240, 232, 222), char="-", group=1)
            self.stroke((s * 0.24, -0.07, 0.50), (s * 0.78, -0.12, 0.38), (240, 232, 222), char="-", group=1)
        # kuyruk: gövdenin sağından yukarı kıvrılan halkalar
        self.tail = [self.add((0.5, -0.8, -0.3), (0.1, 0.1, 0.1), FUR_DARK, group=2) for _ in range(7)]

    def pose(self, t: float) -> None:
        look = self.cursor_look
        self.set_group(1, (0.0, -0.3, 0.0), rx=0.04 * math.sin(t * 1.3) - look[1] * 0.18, ry=look[0] * 0.35, rz=0.03 * math.sin(t * 0.9))
        blink = _blink(t, 4.2)
        for e in self.eyes:
            e.chars = ("-", "-", "-") if blink else ("o", "O", "@")
            e.color = (255, 220, 140) if blink else GREEN
        # kuyruk salınımı (yay üzerinde)
        for k, seg in enumerate(self.tail):
            f = k / (len(self.tail) - 1)
            sw = 0.16 * math.sin(t * 1.7 - f * 2.0) * (0.3 + f)
            seg.c = (0.46 + 0.30 * math.sin(f * 2.1) + sw, -0.95 + 0.95 * f, -0.18 - 0.08 * f)
            r = 0.115 - f * 0.03
            seg.r = (r, r, r)
            seg.update()
        self.set_group(2, (0.0, 0.0, 0.0))


# =========================================================================== BAYKUŞ
OWL_BROWN = (170, 125, 85)
OWL_DARK = (120, 85, 58)
OWL_BELLY = (238, 214, 176)
GOLD = (255, 214, 90)


@register("owl_bust_3d", 46, 24)
class OwlBust(ModelRenderer):
    extent = (1.0, 1.12)
    center = (0.0, -0.02)
    sway = 0.28
    sway_speed = 0.55

    def build(self) -> None:
        self.add((0.0, -0.12, 0.0), (0.64, 0.92, 0.50), OWL_BROWN)  # gövde+baş
        self.add((0.0, -0.40, 0.22), (0.42, 0.55, 0.34), OWL_BELLY)  # göğüs
        for k in range(3):  # göğüs tüyleri
            self.mark((-0.18 + k * 0.18, -0.30 - (k % 2) * 0.12, 0.54), "v", OWL_DARK)
            self.mark((-0.09 + k * 0.18, -0.52 + (k % 2) * 0.06, 0.52), "v", OWL_DARK)
        for s in (-1.0, 1.0):
            self.add((s * 0.50, -0.20, -0.02), (0.17, 0.62, 0.34), OWL_DARK, rot=(0, 0, 0.10 * s))  # kanat
            self.add((s * 0.38, 0.82, 0.02), (0.10, 0.22, 0.09), OWL_DARK, rot=(0, 0, -0.45 * s))  # kulak tüyü
        self.discs = [self.add((s * 0.27, 0.36, 0.40), (0.25, 0.25, 0.10), (252, 240, 205), chars=("(", "O", "O"), outline=False)
                      for s in (-1.0, 1.0)]
        self.pupils = [self.add((s * 0.27, 0.36, 0.49), (0.10, 0.10, 0.06), (255, 190, 40), chars=("@", "@", "@"), outline=False)
                       for s in (-1.0, 1.0)]
        self.add((0.0, 0.15, 0.50), (0.07, 0.12, 0.07), (255, 150, 40), chars=("v", "v", "v"), outline=False)  # gaga
        self.add((0.0, -1.0, 0.04), (0.92, 0.07, 0.20), (110, 78, 48), outline=True)  # dal
        for s in (-1.0, 1.0):
            self.mark((s * 0.18, -0.94, 0.30), "m", OWL_BELLY)  # pençeler

    def pose(self, t: float) -> None:
        blink = (t % 4.8) > 4.6
        for d in self.discs:
            d.chars = ("-", "-", "-") if blink else ("(", "O", "O")
        for p in self.pupils:
            p.visible = not blink
            p.c = (p.c[0], p.c[1], p.c[2])
        lx = self.cursor_look[0] * 0.07
        for k, p in enumerate(self.pupils):
            p.c = ((-0.27 if k == 0 else 0.27) + lx, 0.36 + self.cursor_look[1] * -0.04, 0.49)
            p.update()


# =========================================================================== KÖPEK
DOG_FUR = (226, 170, 100)
DOG_DARK = (160, 105, 58)


@register("dog_bust_3d", 46, 24)
class DogBust(ModelRenderer):
    extent = (1.05, 1.1)
    center = (0.0, -0.05)
    sway = 0.32
    sway_speed = 0.75

    def build(self) -> None:
        self.add((0.0, -0.74, -0.04), (0.52, 0.44, 0.38), DOG_FUR)
        self.add((0.0, -0.40, 0.10), (0.34, 0.07, 0.27), (70, 140, 255), flat=True, outline=False)  # tasma
        self.add((0.0, 0.10, 0.0), (0.56, 0.48, 0.50), DOG_FUR, group=1)  # baş
        self.ears = [self.add((s * 0.56, 0.02, 0.0), (0.17, 0.42, 0.22), DOG_DARK, rot=(0, 0, 0.14 * s), group=1) for s in (-1.0, 1.0)]
        self.add((0.0, -0.13, 0.40), (0.28, 0.21, 0.27), (246, 214, 168), group=1)  # çıkık burun bölgesi
        self.add((0.0, -0.02, 0.64), (0.085, 0.06, 0.05), (130, 150, 175), chars=("@", "@", "@"), group=1, outline=False)  # burun
        self.eyes = [self.add((s * 0.21, 0.24, 0.42), (0.06, 0.06, 0.05), (255, 255, 255), chars=("o", "o", "@"), group=1, outline=False)
                     for s in (-1.0, 1.0)]
        self.tongue = self.add((0.0, -0.36, 0.50), (0.075, 0.11, 0.05), (255, 120, 150), group=1, outline=False)
        self.tail = [self.add((0.5, -0.9, -0.3), (0.10, 0.10, 0.10), DOG_DARK, group=2, outline=False) for _ in range(5)]

    def pose(self, t: float) -> None:
        look = self.cursor_look
        self.set_group(1, (0.0, -0.3, 0.0), rx=-look[1] * 0.15, ry=look[0] * 0.30, rz=0.05 * math.sin(t * 1.1))
        blink = (t % 3.9) > 3.75
        for e in self.eyes:
            e.chars = ("-", "-", "-") if blink else ("o", "o", "@")
        pant = 0.5 + 0.5 * math.sin(t * 7.0)
        self.tongue.r = (0.075, 0.07 + 0.06 * pant, 0.05)
        self.tongue.c = (0.0, -0.34 - 0.04 * pant, 0.50)
        self.tongue.update()
        for k, e in enumerate(self.ears):
            s = -1.0 if k == 0 else 1.0
            e.rot = (0, 0, s * (0.14 + 0.06 * math.sin(t * 2.0 + k)))
            e.update()
        for k, seg in enumerate(self.tail):  # kuyruk sallama
            f = k / 4.0
            seg.c = (0.46 + 0.28 * f + 0.20 * math.sin(t * 8.0) * f, -0.86 + 0.5 * f, -0.30)
            seg.update()


# =========================================================================== TİLKİ
FOX = (238, 130, 55)
FOX_WHITE = (252, 244, 232)
FOX_DARK = (70, 45, 40)


@register("fox_bust_3d", 46, 24)
class FoxBust(ModelRenderer):
    extent = (1.12, 1.1)
    center = (0.05, -0.05)
    sway = 0.30
    sway_speed = 0.65

    def build(self) -> None:
        self.add((0.0, -0.72, -0.04), (0.46, 0.42, 0.36), FOX)
        self.add((0.0, -0.64, 0.24), (0.26, 0.32, 0.20), FOX_WHITE)  # göğüs
        self.add((0.0, 0.10, 0.0), (0.58, 0.42, 0.46), FOX, group=1)  # baş
        for s in (-1.0, 1.0):
            self.add((s * 0.40, -0.10, 0.22), (0.24, 0.20, 0.28), FOX_WHITE, group=1)  # yanak tüyü
            self.add((s * 0.36, 0.62, -0.02), (0.16, 0.36, 0.07), FOX, rot=(0, 0, 0.28 * s), group=1)  # kulak
            self.add((s * 0.395, 0.80, -0.02), (0.075, 0.17, 0.06), FOX_DARK, rot=(0, 0, 0.28 * s), group=1)  # kulak ucu (siyah)
        self.add((0.0, -0.07, 0.46), (0.17, 0.13, 0.30), FOX_WHITE, group=1)  # uzun burun
        self.add((0.0, -0.03, 0.74), (0.06, 0.05, 0.05), FOX_DARK, chars=("@", "@", "@"), group=1, outline=False)  # burun ucu
        self.eyes = [self.add((s * 0.24, 0.20, 0.40), (0.09, 0.05, 0.07), (255, 205, 80), chars=("-", "o", "o"), group=1, outline=False)
                     for s in (-1.0, 1.0)]
        for s in (-1.0, 1.0):
            self.stroke((s * 0.30, 0.00, 0.50), (s * 0.78, 0.08, 0.34), (255, 240, 220), char="-", group=1)
        self.tail = []
        for k in range(8):
            col = FOX_WHITE if k >= 6 else FOX
            self.tail.append(self.add((0.5, -0.9, -0.3), (0.17, 0.17, 0.17), col, group=2, outline=False))

    def pose(self, t: float) -> None:
        look = self.cursor_look
        self.set_group(1, (0.0, -0.3, 0.0), rx=-look[1] * 0.15, ry=look[0] * 0.30, rz=0.04 * math.sin(t * 1.2))
        blink = (t % 5.0) > 4.85
        for e in self.eyes:
            e.chars = ("-", "-", "-") if blink else ("-", "o", "o")
        for k, seg in enumerate(self.tail):
            f = k / 7.0
            sw = 0.22 * math.sin(t * 1.4 - f * 1.8) * (0.2 + f)
            seg.c = (0.55 + 0.45 * math.sin(f * 1.6) + sw, -0.95 + 0.80 * f, -0.22 - 0.05 * f)
            r = 0.10 + 0.06 * math.sin(f * math.pi)
            seg.r = (r, r, r)
            seg.update()


# =========================================================================== ŞÖVALYE (çimde oturan)
STEEL = (176, 188, 208)
STEEL_D = (118, 130, 152)
GRASS = (70, 170, 80)


@register("knight_sitting_3d", 60, 28)
class KnightSitting(ModelRenderer):
    extent = (1.45, 1.15)
    center = (0.0, -0.05)
    sway = 0.22
    sway_speed = 0.45

    def build(self) -> None:
        self.ground = self.add((0.0, -1.02, 0.1), (1.55, 0.10, 0.95), (58, 130, 70), outline=False)
        # bacaklar (yere oturmuş)
        for s in (-1.0, 1.0):
            self.add((s * 0.26, -0.78, 0.36), (0.17, 0.15, 0.42), STEEL_D)  # uyluk
            self.add((s * 0.30, -0.86, 0.80), (0.16, 0.14, 0.18), STEEL)  # diz altı/çizme
        self.torso = self.add((0.0, -0.18, 0.0), (0.44, 0.52, 0.34), STEEL)
        self.add((0.0, -0.12, 0.22), (0.30, 0.34, 0.20), STEEL_D)  # göğüs plakası
        self.add((0.0, -0.52, 0.10), (0.40, 0.08, 0.30), (120, 78, 50), flat=True, outline=False)  # kemer
        for s in (-1.0, 1.0):
            self.add((s * 0.52, 0.22, 0.0), (0.19, 0.16, 0.19), STEEL)  # omuzluk
            self.add((s * 0.58, -0.22, 0.12), (0.11, 0.30, 0.11), STEEL_D, rot=(0, 0, 0.18 * s))  # kol
        self.add((-0.52, -0.62, 0.38), (0.10, 0.10, 0.10), STEEL)  # el (dizde)
        # kafa + miğfer (grup 1: arada başını çevirir)
        self.add((0.0, 0.58, 0.0), (0.27, 0.31, 0.27), STEEL, group=1)
        self.add((0.0, 0.40, 0.04), (0.20, 0.10, 0.22), STEEL_D, group=1, outline=False)  # gorget
        self.plume = self.add((0.0, 0.92, -0.10), (0.07, 0.20, 0.26), (220, 60, 60), group=1)
        self.stroke((-0.17, 0.58, 0.25), (0.17, 0.58, 0.25), (255, 210, 90), char="=", group=1)  # göz yarığı
        self.stroke((0.0, 0.70, 0.25), (0.0, 0.46, 0.27), (255, 235, 170), char="|", group=1)  # burun siperi
        # kalkan (yere dayalı)
        self.add((-1.05, -0.38, 0.30), (0.10, 0.52, 0.40), (60, 90, 190), rot=(0, 0.5, 0))
        self.mark((-0.98, -0.30, 0.55), "+", GOLD)
        self.mark((-0.98, -0.45, 0.55), "+", GOLD)
        # kılıç (yere saplı)
        self.stroke((0.95, -1.00, 0.35), (0.95, 0.50, 0.35), (230, 236, 250), char="|")
        self.stroke((0.80, 0.36, 0.35), (1.10, 0.36, 0.35), (240, 200, 80), char="-")
        self.mark((0.95, 0.58, 0.35), "o", (240, 200, 80))
        # çimen: sabit noktalarda sallanan bıçaklar
        import random

        rng = random.Random(7)
        self.blades = []
        for _ in range(54):
            x = rng.uniform(-1.45, 1.45)
            z = rng.uniform(-0.2, 0.95)
            if abs(x) < 0.5 and z < 0.7 and z > -0.2 and False:
                continue
            col = (rng.randint(40, 90), rng.randint(150, 215), rng.randint(50, 95))
            self.blades.append((self.mark((x, -0.88 + rng.uniform(0, 0.06), z), "|", col), x))

    def pose(self, t: float) -> None:
        br = math.sin(t * 1.4)
        self.torso.r = (0.44, 0.52 + 0.012 * br, 0.34 + 0.010 * br)
        self.torso.update()
        # arada başını çevir (yumuşak, 9 sn'de bir)
        ph = (t % 9.0) / 9.0
        turn = 0.0
        if 0.55 < ph < 0.8:
            turn = 0.5 * math.sin((ph - 0.55) / 0.25 * math.pi)
        self.set_group(1, (0.0, 0.40, 0.0), ry=turn, rx=0.02 * br)
        self.plume.c = (0.02 * math.sin(t * 2.2), 0.92, -0.10 - 0.02 * math.sin(t * 2.2 + 1))
        self.plume.update()
        for m, x in self.blades:
            w = math.sin(t * 2.3 + x * 2.6)
            m.char = "/" if w > 0.35 else ("\\" if w < -0.35 else "|")


# =========================================================================== EJDERHA YAVRUSU
DR = (96, 200, 120)
DR_BELLY = (250, 226, 150)


@register("dragon_baby_3d", 52, 26)
class DragonBaby(ModelRenderer):
    extent = (1.25, 1.1)
    center = (0.0, -0.02)
    sway = 0.30
    sway_speed = 0.6

    def build(self) -> None:
        self.add((0.0, -0.55, -0.05), (0.52, 0.46, 0.44), DR)
        self.add((0.0, -0.58, 0.26), (0.34, 0.36, 0.24), DR_BELLY, outline=False)
        for s in (-1.0, 1.0):
            self.add((s * 0.30, -0.98, 0.18), (0.17, 0.09, 0.26), DR)  # ayaklar
        self.add((0.05, 0.22, 0.12), (0.42, 0.36, 0.40), DR, group=1)  # baş
        self.add((0.05, 0.10, 0.52), (0.22, 0.16, 0.22), (130, 220, 150), group=1)  # burun
        for s in (-1.0, 1.0):
            self.add((0.05 + s * 0.24, 0.62, 0.0), (0.06, 0.22, 0.06), (250, 236, 200), rot=(0.25, 0, -0.40 * s), group=1)  # boynuz
            self.mark((0.05 + s * 0.08, 0.08, 0.72), ":", (40, 70, 50), group=1)
        self.eyes = [self.add((0.05 + s * 0.20, 0.34, 0.42), (0.085, 0.085, 0.07), (255, 220, 70), chars=("o", "O", "@"), group=1, outline=False)
                     for s in (-1.0, 1.0)]
        self.wings = [self.add((s * 0.85, -0.05, -0.28), (0.52, 0.06, 0.36), (70, 150, 210), group=3 if s < 0 else 4) for s in (-1.0, 1.0)]
        self.spikes = [self.mark((0.0, 0.62 - 0.35 * k, -0.40 - 0.05 * k), "^", (250, 230, 120)) for k in range(4)]
        self.tail = [self.add((0.5, -0.9, -0.3), (0.14, 0.14, 0.14), DR, outline=False) for _ in range(7)]
        self.fire = [self.mark((0.05, 0.05, 0.9), "*", (255, 150, 40), group=1) for _ in range(3)]

    def pose(self, t: float) -> None:
        look = self.cursor_look
        self.set_group(1, (0.0, -0.2, 0.0), rx=-look[1] * 0.15, ry=look[0] * 0.3, rz=0.04 * math.sin(t * 1.2))
        flap = 0.35 * math.sin(t * 3.0)
        self.set_group(3, (-0.45, -0.1, -0.2), rz=-0.3 - flap, ry=0.3)
        self.set_group(4, (0.45, -0.1, -0.2), rz=0.3 + flap, ry=-0.3)
        for e in self.eyes:
            e.chars = ("-", "-", "-") if (t % 4.4) > 4.25 else ("o", "O", "@")
        for k, seg in enumerate(self.tail):
            f = k / 6.0
            seg.c = (0.45 + 0.55 * f + 0.15 * math.sin(t * 1.5 - f * 2), -0.92 + 0.05 * f - 0.05 * f * f, -0.25 - 0.25 * f)
            r = 0.15 - 0.10 * f
            seg.r = (r, r, r)
            seg.update()
        puff = (t % 6.0) < 0.7
        for k, m in enumerate(self.fire):
            m.visible = puff
            if puff:
                m.p = (0.05 + 0.05 * k, 0.05 + 0.06 * math.sin(t * 20 + k), 0.9 + 0.12 * k)
                m.char = "*" if k % 2 == 0 else "~"


# =========================================================================== NÖBETÇİ ROBOT
ROBO = (160, 175, 195)
ROBO_D = (100, 112, 135)
CYAN = (90, 235, 255)


@register("sentinel_robot_3d", 50, 26)
class SentinelRobot(ModelRenderer):
    extent = (1.0, 1.25)
    center = (0.0, -0.1)
    sway = 0.40
    sway_speed = 0.5

    def build(self) -> None:
        self.add((0.0, -0.10, 0.0), (0.50, 0.52, 0.38), ROBO)
        self.panel = self.add((0.0, -0.05, 0.33), (0.20, 0.20, 0.10), (255, 160, 60), chars=("+", "#", "#"), flat=True, outline=False)
        self.add((0.0, 0.46, 0.0), (0.20, 0.10, 0.18), ROBO_D)  # boyun
        self.add((0.0, 0.70, 0.0), (0.38, 0.30, 0.34), ROBO, group=1)  # kafa
        self.add((0.0, 0.70, 0.27), (0.30, 0.10, 0.12), (20, 40, 60), group=1, flat=True, outline=False)  # vizör
        self.eye = self.add((0.0, 0.70, 0.34), (0.07, 0.06, 0.05), CYAN, chars=("o", "O", "@"), flat=True, group=1, outline=False)
        self.stroke((0.0, 1.0, 0.0), (0.0, 1.28, 0.0), ROBO_D, char="|", group=1)
        self.beacon = self.mark((0.0, 1.34, 0.0), "*", (255, 80, 80), group=1)
        for s in (-1.0, 1.0):
            self.add((s * 0.46, 0.30, 0.0), (0.16, 0.14, 0.16), ROBO_D)  # omuz
            self.add((s * 0.70, -0.10, 0.0), (0.12, 0.40, 0.12), ROBO)  # kol
            self.add((s * 0.70, -0.55, 0.0), (0.12, 0.10, 0.12), ROBO_D)  # el
            self.add((s * 0.23, -0.82, 0.0), (0.17, 0.30, 0.18), ROBO)  # bacak
            self.add((s * 0.25, -1.08, 0.10), (0.21, 0.08, 0.28), ROBO_D)  # ayak

    def pose(self, t: float) -> None:
        # vizör tarama: göz soldan sağa gider
        sc = math.sin(t * 1.5)
        self.eye.c = (0.19 * sc + self.cursor_look[0] * 0.05, 0.70, 0.34)
        self.eye.update()
        self.set_group(1, (0.0, 0.5, 0.0), ry=0.25 * math.sin(t * 0.6) + self.cursor_look[0] * 0.3)
        self.beacon.visible = (t % 1.2) < 0.6
        self.panel.chars = ("+", "#", "#") if (t % 2.0) < 1.0 else ("-", "+", "+")


# =========================================================================== BÜYÜCÜ + KİTAP
ROBE = (110, 90, 205)
ROBE_D = (74, 58, 150)


@register("wizard_book_3d", 50, 28)
class WizardBook(ModelRenderer):
    extent = (1.0, 1.55)
    center = (0.0, 0.1)
    sway = 0.30
    sway_speed = 0.5

    def build(self) -> None:
        self.add((0.0, -0.42, 0.0), (0.62, 0.90, 0.48), ROBE)  # cüppe
        self.add((0.0, -0.95, 0.10), (0.70, 0.10, 0.55), ROBE_D, outline=False)  # etek
        self.add((0.0, 0.62, 0.0), (0.28, 0.28, 0.26), (246, 210, 175), group=1)  # kafa
        self.add((0.0, 0.34, 0.20), (0.22, 0.38, 0.14), (245, 245, 250), group=1)  # sakal
        for s in (-1.0, 1.0):
            self.mark((s * 0.10, 0.68, 0.25), ".", (40, 40, 60), group=1)
        self.add((0.0, 0.88, 0.0), (0.46, 0.08, 0.46), ROBE_D, group=1)  # şapka kenarı
        self.add((0.0, 1.10, 0.0), (0.30, 0.22, 0.30), ROBE, group=1)
        self.add((0.06, 1.38, -0.04), (0.18, 0.22, 0.18), ROBE, group=1, rot=(0, 0, -0.25))
        self.add((0.18, 1.62, -0.08), (0.09, 0.16, 0.09), ROBE, group=1, rot=(0, 0, -0.7))
        self.mark((-0.05, 1.05, 0.30), "*", GOLD, group=1)
        for s in (-1.0, 1.0):
            self.add((s * 0.62, -0.05, 0.12), (0.13, 0.36, 0.13), ROBE_D, rot=(0, 0, 0.35 * s))  # kollar
        self.book = [
            self.add((0.0, -0.05, 0.62), (0.40, 0.30, 0.05), (130, 80, 45), group=2),  # kapak
            self.add((0.0, -0.05, 0.68), (0.36, 0.26, 0.03), (250, 240, 210), group=2, outline=False),  # sayfalar
        ]
        self.stroke((0.0, 0.10, 0.70), (0.0, -0.20, 0.70), (150, 110, 70), char="|", group=2)
        # asa + küre
        self.stroke((-0.95, -1.0, 0.2), (-0.95, 0.85, 0.2), (150, 105, 60), char="|")
        self.orb = self.mark((-0.95, 0.95, 0.2), "O", (120, 255, 235))
        self.sparks = [self.mark((0.0, 0.0, 0.7), "*", GOLD) for _ in range(4)]

    def pose(self, t: float) -> None:
        bob = 0.05 * math.sin(t * 1.8)
        self.set_group(2, (0.0, -0.05, 0.62), rx=-0.15 + 0.05 * math.sin(t * 1.1))
        for k, b in enumerate(self.book):
            b.c = (b.c[0], -0.05 + bob, b.c[2])
            b.update()
        for k, m in enumerate(self.sparks):
            a = t * 1.6 + k * math.pi / 2
            m.p = (0.5 * math.cos(a), 0.15 + 0.12 * math.sin(a * 1.7) + bob, 0.7 + 0.25 * math.sin(a))
            m.char = "*" if k % 2 == 0 else "+"
        self.orb.char = "O" if (t % 1.0) < 0.6 else "o"
        self.set_group(1, (0.0, 0.3, 0.0), ry=self.cursor_look[0] * 0.3, rz=0.03 * math.sin(t))


# =========================================================================== KAMP ATEŞİ BAŞINDA KURT
WOLF = (150, 158, 170)
WOLF_L = (210, 214, 222)


@register("wolf_campfire_3d", 62, 28)
class WolfCampfire(ModelRenderer):
    extent = (1.5, 1.05)
    center = (0.0, -0.05)
    sway = 0.18
    sway_speed = 0.4
    light = (0.5, 0.5, 0.7)  # ışık ateşten gelir

    def build(self) -> None:
        self.add((0.0, -1.0, 0.1), (1.6, 0.08, 0.9), (60, 90, 70), outline=False)
        self.add((-0.45, -0.55, 0.0), (0.52, 0.48, 0.38), WOLF)  # gövde (oturan)
        self.add((-0.05, -0.50, 0.28), (0.30, 0.42, 0.20), WOLF_L)  # göğüs
        self.add((-0.50, -0.85, 0.30), (0.30, 0.15, 0.34), WOLF)  # ön patiler
        self.add((-0.80, -0.82, 0.0), (0.30, 0.18, 0.25), WOLF)  # arka bacak
        self.add((0.0, 0.08, 0.05), (0.34, 0.32, 0.30), WOLF, group=1)  # baş
        self.add((0.40, -0.04, 0.06), (0.30, 0.13, 0.15), WOLF_L, group=1)  # burun
        self.mark((0.69, -0.02, 0.06), "@", (30, 30, 40), group=1)
        for s in (-1.0, 1.0):
            self.add((-0.08 + s * 0.13, 0.46, 0.0), (0.085, 0.22, 0.07), WOLF, rot=(0, 0, 0.12 * s), group=1)
        self.eye = self.mark((0.12, 0.14, 0.34), "o", (255, 210, 80), group=1)
        self.tail = [self.add((-0.9, -0.75, -0.2), (0.12, 0.12, 0.12), WOLF, outline=False) for _ in range(6)]
        # ateş: tomruklar + alevler
        self.stroke((0.75, -0.95, 0.55), (1.35, -0.88, 0.75), (140, 90, 50), char="=")
        self.stroke((0.75, -0.88, 0.75), (1.35, -0.95, 0.55), (120, 75, 40), char="=")
        self.flames = [self.mark((1.05, -0.8, 0.65), "^", (255, 160, 40)) for _ in range(18)]

    def pose(self, t: float) -> None:
        look = self.cursor_look
        self.set_group(1, (-0.15, -0.2, 0.0), rz=-0.05 + 0.04 * math.sin(t * 0.8), ry=look[0] * 0.25)
        self.eye.char = "-" if (t % 5.5) > 5.35 else "o"
        for k, seg in enumerate(self.tail):
            f = k / 5.0
            seg.c = (-0.85 - 0.5 * f, -0.80 + 0.12 * f + 0.06 * math.sin(t * 1.5 - f * 2), -0.15 - 0.15 * f)
            r = 0.13 - 0.04 * f
            seg.r = (r, r, r)
            seg.update()
        for k, m in enumerate(self.flames):
            ph = (t * 1.8 + k * 0.37) % 1.0
            spread = 0.12 * (1.0 - ph) * math.sin(k * 2.1 + t * 5)
            m.p = (1.05 + spread, -0.82 + ph * 0.75, 0.65 + 0.06 * math.sin(k + t * 3))
            m.char = "^" if ph < 0.35 else ("(" if k % 2 else ")") if ph < 0.7 else ("'" if k % 2 else ".")
            m.color = (255, int(200 - 130 * ph), int(60 * (1 - ph)))


# =========================================================================== UZAY YÜRÜYÜŞÜ ASTRONOTU
SUIT = (240, 244, 252)
SUIT_D = (188, 196, 214)


@register("astronaut_eva_3d", 56, 28)
class AstronautEVA(ModelRenderer):
    extent = (1.3, 1.25)
    center = (0.0, -0.05)
    sway = 0.45
    sway_speed = 0.35
    base_pitch = 0.0

    def build(self) -> None:
        import random

        rng = random.Random(11)
        self.stars = [self.mark((rng.uniform(-1.4, 1.4), rng.uniform(-1.2, 1.2), -3.0), rng.choice(".+*"), (200, 215, 255)) for _ in range(26)]
        self.add((0.0, -0.20, 0.0), (0.46, 0.56, 0.36), SUIT)  # gövde
        self.add((0.0, -0.18, -0.42), (0.36, 0.46, 0.18), SUIT_D)  # sırt çantası
        self.add((0.0, -0.10, 0.31), (0.22, 0.16, 0.09), (255, 120, 90), chars=("=", "#", "#"), flat=True, outline=False)  # panel
        self.add((0.0, 0.50, 0.0), (0.40, 0.40, 0.38), SUIT, group=1)  # kask
        self.add((0.0, 0.50, 0.22), (0.30, 0.27, 0.22), (56, 100, 215), group=1, outline=False)  # vizör
        self.mark((-0.10, 0.60, 0.43), ".", (210, 230, 255), group=1)
        self.mark((-0.06, 0.55, 0.43), ".", (210, 230, 255), group=1)
        self.arms = []
        for s in (-1.0, 1.0):
            self.arms.append(self.add((s * 0.66, -0.12, 0.10), (0.15, 0.36, 0.15), SUIT, rot=(0, 0, 0.5 * s)))
            self.add((s * 0.34, -0.92, 0.04), (0.18, 0.40, 0.18), SUIT, rot=(0, 0, 0.08 * s))
            self.add((s * 0.36, -1.28, 0.10), (0.21, 0.09, 0.26), SUIT_D)
        self.tether = [self.mark((0.5, -0.4, -0.3), "~", (255, 230, 120)) for _ in range(12)]

    def pose(self, t: float) -> None:
        for k, m in enumerate(self.stars):
            m.char = "*" if ((t * 1.2 + k * 0.7) % 2.4) < 0.3 else ("+" if k % 3 == 0 else ".")
        self.set_group(1, (0.0, 0.2, 0.0), ry=self.cursor_look[0] * 0.3 + 0.1 * math.sin(t * 0.7))
        for k, m in enumerate(self.tether):
            f = k / 11.0
            m.p = (0.55 + 1.0 * f, -0.35 + 0.25 * math.sin(f * 5.0 + t * 1.5), -0.35)


# =========================================================================== BONSAİ
LEAF = (70, 185, 90)
LEAF_D = (46, 140, 70)
TRUNK = (126, 88, 58)


@register("bonsai_tree_3d", 52, 28)
class BonsaiTree(ModelRenderer):
    extent = (1.2, 1.25)
    center = (0.0, 0.1)
    sway = 0.55
    sway_speed = 0.30

    def build(self) -> None:
        self.add((0.0, -1.0, 0.0), (0.70, 0.20, 0.50), (196, 106, 76))  # saksı
        self.add((0.0, -0.84, 0.0), (0.76, 0.06, 0.55), (214, 126, 92), outline=False)  # kenar
        self.add((0.0, -0.80, 0.0), (0.62, 0.05, 0.42), (88, 62, 44), outline=False)  # toprak
        # gövde: kıvrık halkalar
        pts = [(-0.05, -0.78), (0.10, -0.55), (0.18, -0.30), (0.02, -0.05), (-0.12, 0.20), (-0.02, 0.45)]
        for (x, y) in pts:
            self.add((x, y, 0.0), (0.12, 0.17, 0.12), TRUNK, outline=False)
        self.add((0.35, -0.12, 0.0), (0.22, 0.07, 0.07), TRUNK, rot=(0, 0, 0.5))  # yan dal
        self.add((-0.38, 0.10, 0.0), (0.22, 0.07, 0.07), TRUNK, rot=(0, 0, -0.5))
        self.clumps = [
            self.add((0.0, 0.62, 0.0), (0.58, 0.30, 0.46), LEAF),
            self.add((-0.65, 0.22, 0.05), (0.40, 0.22, 0.34), LEAF_D),
            self.add((0.62, 0.05, 0.05), (0.40, 0.22, 0.34), LEAF),
        ]
        self.leaves = [self.mark((0.0, 0.0, 0.5), ".", LEAF) for _ in range(5)]

    def pose(self, t: float) -> None:
        for k, c in enumerate(self.clumps):
            s = 1.0 + 0.025 * math.sin(t * 1.3 + k)
            c.r = (c.r[0], c.r[1] * 1.0, c.r[2])
            c.c = (c.c[0], c.c[1] + 0.0, c.c[2])
        for k, m in enumerate(self.leaves):
            ph = (t * 0.35 + k * 0.21) % 1.0
            m.p = (-0.7 + 1.4 * ((k * 0.37) % 1.0) + 0.12 * math.sin(t + k), 0.55 - 1.3 * ph, 0.45)
            m.char = "." if k % 2 else "'"


# modelin eksik kalan ayrıntısı: yuvarlak çimen/yaprak parlaması için basit kesinlik
