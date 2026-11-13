"""Real-time 3D Raytracer, Z-Buffer & Shader Procedural Engine (24-30 FPS).

Every renderer outputs strictly printable classic ASCII characters (0x20..0x7E)
with Z-buffer occlusion, luminance shading ramps, and per-cell RGB palettes.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

RGB = Tuple[int, int, int]

CHARS_RAMP = " .:-=+*#%@"
DONUT_RAMP = ".,-~:;=!*#$@"
THERMAL_RAMP = " .:-=+*#%@"
WAVE_RAMP = " .~:-=+*#%@"


@dataclass
class ProceduralFrame:
    """Single rendered frame with pure classic ASCII rows and optional per-cell RGB colors."""

    lines: List[str]
    colors: List[List[Optional[RGB]]]


def hsv_to_rgb(h: float, s: float, v: float) -> RGB:
    i = int(h * 6.0)
    f = (h * 6.0) - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    i %= 6
    if i == 0:
        r, g, b = v, t, p
    elif i == 1:
        r, g, b = q, v, p
    elif i == 2:
        r, g, b = p, v, t
    elif i == 3:
        r, g, b = p, q, v
    elif i == 4:
        r, g, b = t, p, v
    else:
        r, g, b = v, p, q
    return (int(r * 255), int(g * 255), int(b * 255))


class BaseProceduralRenderer:
    """Base class for live procedural 3D/shader ASCII renderers."""

    def __init__(self, width: int = 52, height: int = 24, params: Optional[Dict[str, Any]] = None) -> None:
        self.width = max(24, int(width))
        self.height = max(14, int(height))
        self.params = params or {}
        self.t = 0.0
        self.yaw_offset = 0.0
        self.pitch_offset = 0.0
        self.cursor_look: Tuple[float, float] = (0.0, 0.0)
        self.progress: Optional[float] = None

    def set_grid_size(self, width: int, height: int) -> None:
        nw, nh = max(24, int(width)), max(14, int(height))
        if nw != self.width or nh != self.height:
            self.width = nw
            self.height = nh
            self._on_grid_resized()

    def _on_grid_resized(self) -> None:
        """Hook for renderers that cache grid-sized buffers or rays."""

    def step(
        self,
        dt: float,
        speed_mult: float = 1.0,
        yaw_offset: float = 0.0,
        pitch_offset: float = 0.0,
        cursor_look: Tuple[float, float] = (0.0, 0.0),
        progress: Optional[float] = None,
    ) -> ProceduralFrame:
        self.t += dt * speed_mult
        self.yaw_offset = yaw_offset
        self.pitch_offset = pitch_offset
        self.cursor_look = cursor_look
        self.progress = progress
        return self.render_at(self.t)

    def render_at(self, t: float) -> ProceduralFrame:
        raise NotImplementedError


def _draw_line_z(
    buf: List[List[str]],
    zbuf: List[List[float]],
    cbuf: List[List[Optional[RGB]]],
    w: int,
    h: int,
    x0: float,
    y0: float,
    z0: float,
    x1: float,
    y1: float,
    z1: float,
    ch: str,
    col: RGB,
) -> None:
    steps = max(2, int(max(abs(x1 - x0), abs(y1 - y0)) * 1.6) + 1)
    for s in range(steps + 1):
        u = s / steps
        x = int(round(x0 + (x1 - x0) * u))
        y = int(round(y0 + (y1 - y0) * u))
        z = z0 + (z1 - z0) * u
        if 0 <= x < w and 0 <= y < h and z >= zbuf[y][x]:
            zbuf[y][x] = z
            buf[y][x] = ch
            cbuf[y][x] = col


class Saturn3DRenderer(BaseProceduralRenderer):
    """3D Raytraced Saturn with Cassini ring gap, mutual shadows, and twinkling starfield."""

    def __init__(self, width: int = 54, height: int = 24, params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(width, height, params)
        self.tilt_x = 0.42
        self.aspect = 0.52
        self.R = 1.0
        self.R_in = 1.32
        self.R_out = 2.45
        self.cassini_in = 1.83
        self.cassini_out = 1.95
        self.cam_dist = 4.35
        self.fov = 1.75

        ll = math.sqrt(0.7 * 0.7 + 0.4 * 0.4 + 0.6 * 0.6)
        self.lx_w = -0.7 / ll
        self.ly_w = -0.4 / ll
        self.lz_w = -0.6 / ll
        self._on_grid_resized()

    def _on_grid_resized(self) -> None:
        scale = min(self.height * 0.44, self.width * self.aspect * 0.38)
        self._rays: List[List[Tuple[float, float, float]]] = []
        for py in range(self.height):
            vy = (py - self.height / 2.0) / scale
            row_rays: List[Tuple[float, float, float]] = []
            for px in range(self.width):
                vx = (px - self.width / 2.0) / scale * self.aspect
                dl = math.sqrt(vx * vx + vy * vy + self.fov * self.fov)
                row_rays.append((vx / dl, vy / dl, self.fov / dl))
            self._rays.append(row_rays)

        rng = random.Random(42)
        self._stars: Dict[Tuple[int, int], Tuple[str, RGB, float]] = {}
        palette = [(255, 220, 140), (160, 200, 255), (220, 225, 235)]
        for y in range(self.height):
            for x in range(self.width):
                if rng.random() < 0.028:
                    ch = rng.choice([".", ",", "*", "+", "'"])
                    col = rng.choice(palette)
                    phase = rng.uniform(0.0, 6.28)
                    self._stars[(x, y)] = (ch, col, phase)

    def render_at(self, t: float) -> ProceduralFrame:
        angle = t * 1.15 + self.yaw_offset
        tilt_x = max(-1.35, min(1.35, self.tilt_x + self.pitch_offset * 0.65 + self.cursor_look[1] * 0.16))
        tilt_z = 0.22 + math.sin(angle * 0.35) * 0.05 + self.cursor_look[0] * 0.14
        cos_tx, sin_tx = math.cos(tilt_x), math.sin(tilt_x)
        cos_tz, sin_tz = math.cos(tilt_z), math.sin(tilt_z)

        def w2l(x: float, y: float, z: float) -> Tuple[float, float, float]:
            y1 = y * cos_tx + z * sin_tx
            z1 = -y * sin_tx + z * cos_tx
            x2 = x * cos_tz + y1 * sin_tz
            y2 = -x * sin_tz + y1 * cos_tz
            return x2, y2, z1

        lx, ly, lz = w2l(self.lx_w, self.ly_w, self.lz_w)
        ox, oy, oz = w2l(0.0, 0.0, -self.cam_dist)
        o2_minus_r2 = (ox * ox + oy * oy + oz * oz) - self.R * self.R

        R = self.R
        R_in = self.R_in
        R_out = self.R_out
        c_in = self.cassini_in
        c_out = self.cassini_out
        ramp_max = len(CHARS_RAMP) - 1

        lines: List[str] = []
        colors: List[List[Optional[RGB]]] = []

        for py in range(self.height):
            row_chars = [" "] * self.width
            row_cols: List[Optional[RGB]] = [None] * self.width
            row_rays = self._rays[py]

            for px in range(self.width):
                dwx, dwy, dwz = row_rays[px]
                y1 = dwy * cos_tx + dwz * sin_tx
                dz = -dwy * sin_tx + dwz * cos_tx
                dx = dwx * cos_tz + y1 * sin_tz
                dy = -dwx * sin_tz + y1 * cos_tz

                b = 2.0 * (ox * dx + oy * dy + oz * dz)
                disc = b * b - 4.0 * o2_minus_r2
                t_sphere = 1e9
                if disc >= 0.0:
                    t1 = (-b - math.sqrt(disc)) * 0.5
                    if t1 > 0.0:
                        t_sphere = t1

                t_ring = 1e9
                ring_r = 0.0
                if abs(dy) > 1e-5:
                    tr = -oy / dy
                    if tr > 0.0:
                        rx = ox + tr * dx
                        rz = oz + tr * dz
                        dist = math.sqrt(rx * rx + rz * rz)
                        if R_in <= dist <= R_out and not (c_in <= dist <= c_out):
                            t_ring = tr
                            ring_r = dist

                if t_sphere < t_ring and t_sphere < 1e8:
                    hx = ox + t_sphere * dx
                    hy = oy + t_sphere * dy
                    hz = oz + t_sphere * dz

                    diffuse = max(0.0, -(hx * lx + hy * ly + hz * lz))
                    shadow = 1.0
                    if abs(ly) > 1e-4:
                        sr = hy / ly
                        if sr > 0.0:
                            shx = hx - sr * lx
                            shz = hz - sr * lz
                            sh_dist = math.sqrt(shx * shx + shz * shz)
                            if R_in <= sh_dist <= R_out and not (c_in <= sh_dist <= c_out):
                                shadow = 0.32

                    lon = math.atan2(hz, hx)
                    bands = (
                        math.sin(hy * 18.0) * 0.08
                        + math.cos(hy * 36.0 + 1.2) * 0.05
                        + math.sin(hy * 60.0) * 0.03
                        + math.sin(lon * 3.0 + angle * 1.6) * 0.04
                    )
                    intensity = max(0.05, min(1.0, diffuse * shadow * 0.85 + 0.14 + bands))
                    row_chars[px] = CHARS_RAMP[int(intensity * ramp_max)]
                    br = intensity * shadow
                    row_cols[px] = (
                        min(255, int(235 * br + 35)),
                        min(255, int(188 * br + 25)),
                        min(255, int(115 * br + 15)),
                    )

                elif t_ring < 1e8:
                    rx = ox + t_ring * dx
                    rz = oz + t_ring * dz
                    sb = -2.0 * (rx * lx + rz * lz)
                    sc = (rx * rx + rz * rz) - R * R
                    sdisc = sb * sb - 4.0 * sc
                    ring_shadow = 1.0
                    if sdisc >= 0.0:
                        st = (-sb - math.sqrt(sdisc)) * 0.5
                        if st > 0.01:
                            ring_shadow = 0.22

                    groove = math.sin(ring_r * 45.0) * 0.25 + 0.75
                    intensity = max(0.04, min(1.0, ring_shadow * groove * 0.88))
                    row_chars[px] = CHARS_RAMP[int(intensity * ramp_max)]
                    row_cols[px] = (
                        min(255, int(215 * intensity + 30)),
                        min(255, int(202 * intensity + 25)),
                        min(255, int(180 * intensity + 20)),
                    )

                else:
                    star = self._stars.get((px, py))
                    if star:
                        ch, col, phase = star
                        twinkle = 0.65 + 0.35 * math.sin(t * 2.5 + phase)
                        row_chars[px] = ch
                        row_cols[px] = (
                            int(col[0] * twinkle),
                            int(col[1] * twinkle),
                            int(col[2] * twinkle),
                        )

            lines.append("".join(row_chars))
            colors.append(row_cols)

        return ProceduralFrame(lines=lines, colors=colors)


class Donut3DRenderer(BaseProceduralRenderer):
    """3D Spinning Torus Z-Buffer renderer with HSV rainbow glaze."""

    def __init__(self, width: int = 50, height: int = 22, params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(width, height, params)
        self.R1 = 1.0
        self.R2 = 2.0
        self.K2 = 5.4
        self.aspect = 0.52
        self._on_grid_resized()

        self._phis = [(j, math.cos(j), math.sin(j)) for j in [k * 0.14 for k in range(45)]]
        self._thetas = [(math.cos(i), math.sin(i)) for i in [k * 0.07 for k in range(90)]]

    def _on_grid_resized(self) -> None:
        scale = min(self.height * 0.34, self.width * self.aspect * 0.34)
        self.K1 = (scale * self.K2) / (self.R1 + self.R2)

    def render_at(self, t: float) -> ProceduralFrame:
        A = t * 1.25 + self.pitch_offset + self.cursor_look[1] * 0.22
        B = t * 0.68 + self.yaw_offset + self.cursor_look[0] * 0.22
        cosA, sinA = math.cos(A), math.sin(A)
        cosB, sinB = math.cos(B), math.sin(B)

        w, h = self.width, self.height
        half_w = w / 2.0
        half_h = h / 2.0
        k1_x = self.K1 * self.aspect * 1.85
        k1_y = self.K1
        R1, R2, K2 = self.R1, self.R2, self.K2

        buf = [[" "] * w for _ in range(h)]
        zbuf = [[0.0] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]
        ramp_len = len(DONUT_RAMP)

        for j, cos_phi, sin_phi in self._phis:
            hue = (j / 6.283185 + A * 0.18) % 1.0
            for cos_theta, sin_theta in self._thetas:
                circlex = R2 + R1 * cos_theta
                circley = R1 * sin_theta

                x = circlex * (cosB * cos_phi + sinA * sinB * sin_phi) - circley * cosA * sinB
                y = circlex * (sinB * cos_phi - sinA * cosB * sin_phi) + circley * cosA * cosB
                z = K2 + cosA * circlex * sin_phi + circley * sinA
                ooz = 1.0 / z

                xp = int(half_w + k1_x * ooz * x)
                yp = int(half_h - k1_y * ooz * y)

                if 0 <= xp < w and 0 <= yp < h:
                    L = (
                        cos_phi * cos_theta * sinB
                        - cosA * cos_theta * sin_phi
                        - sinA * sin_theta
                        + cosB * (cosA * sin_theta - cos_theta * sinA * sin_phi)
                    )
                    if L > 0.0 and ooz > zbuf[yp][xp]:
                        zbuf[yp][xp] = ooz
                        idx = min(ramp_len - 1, max(0, int(L * 8.0)))
                        buf[yp][xp] = DONUT_RAMP[idx]
                        br = min(1.0, L * 0.88 + 0.22)
                        cbuf[yp][xp] = hsv_to_rgb(hue, 0.85, br)

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class ChristmasTree3DRenderer(BaseProceduralRenderer):
    """3D Rotating Christmas Tree with blinking ornaments, topper star, and falling snow."""

    def __init__(self, width: int = 48, height: int = 26, params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(width, height, params)
        rng = random.Random(2025)
        self.mesh: List[Tuple[float, float, float, float, float, float, str, str]] = []
        tiers = [
            (-1.45, -0.85, 0.08, 0.55),
            (-0.92, -0.20, 0.22, 0.95),
            (-0.25, 0.50, 0.38, 1.35),
            (0.45, 1.25, 0.55, 1.78),
        ]
        for y_top, y_bottom, r_top, r_bottom in tiers:
            n_y = 18
            for iy in range(n_y):
                fy = iy / (n_y - 1)
                y = y_top + fy * (y_bottom - y_top)
                base_r = r_top + fy * (r_bottom - r_top)
                n_phi = int(base_r * 42) + 14
                for iphi in range(n_phi):
                    phi = iphi * (2.0 * math.pi / n_phi)
                    wave = math.sin(phi * 9.0 + iy * 2.3) * 0.08 + math.cos(phi * 4.0) * 0.04
                    r = base_r * (1.0 + wave)
                    x = r * math.cos(phi)
                    z = r * math.sin(phi)
                    nx, ny, nz = x / r, 0.35, z / r
                    nl = math.sqrt(nx * nx + ny * ny + nz * nz)
                    ch = rng.choice(["*", "^", "#", "%", "/", "\\"])
                    self.mesh.append((x, y, z, nx / nl, ny / nl, nz / nl, ch, "foliage"))

        trunk_r = 0.28
        for iy in range(9):
            y = 1.25 + (iy / 8.0) * 0.60
            for iphi in range(16):
                phi = iphi * (2.0 * math.pi / 16)
                x = trunk_r * math.cos(phi)
                z = trunk_r * math.sin(phi)
                self.mesh.append((x, y, z, x / trunk_r, 0.0, z / trunk_r, "|", "trunk"))

        orn_colors = [
            (255, 55, 75),
            (255, 215, 0),
            (0, 235, 255),
            (255, 70, 205),
            (255, 145, 20),
            (255, 255, 255),
        ]
        self.ornaments: List[Tuple[float, float, float, str, RGB, float]] = []
        orn_tiers = [
            (-1.40, -0.85, 0.12, 0.52),
            (-0.90, -0.20, 0.25, 0.90),
            (-0.25, 0.50, 0.40, 1.30),
            (0.45, 1.20, 0.60, 1.70),
        ]
        for _ in range(72):
            y_top, y_bottom, r_top, r_bottom = rng.choice(orn_tiers)
            fy = rng.uniform(0.12, 0.95)
            y = y_top + fy * (y_bottom - y_top)
            r = (r_top + fy * (r_bottom - r_top)) * 1.03
            phi = rng.uniform(0.0, 2.0 * math.pi)
            ch = rng.choice(["@", "o", "O", "*", "+"])
            col = rng.choice(orn_colors)
            phase = rng.uniform(0.0, 6.28)
            self.ornaments.append((r * math.cos(phi), y, r * math.sin(phi), ch, col, phase))

        self.snow = [
            (rng.uniform(-2.6, 2.6), rng.uniform(-2.1, 2.1), rng.uniform(-1.8, 2.2), rng.uniform(0.6, 1.4), rng.choice([".", ",", "*", "+"]))
            for _ in range(55)
        ]

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        aspect = 0.52
        cam_dist = 4.35
        scale_y = h * 0.78
        scale_x = scale_y * aspect * 1.85
        if (scale_x * 0.48) > (w * 0.44):
            scale_x = (w * 0.44) / 0.48
            scale_y = scale_x / (aspect * 1.85)

        angle = t * 1.05 + self.yaw_offset + self.cursor_look[0] * 0.35
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        lx, ly, lz = -0.577, -0.577, -0.577

        buf = [[" "] * w for _ in range(h)]
        zbuf = [[-999.0] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]
        half_w, half_h = w / 2.0, h / 2.0

        for x0, y0, z0, nx0, ny0, nz0, ch, kind in self.mesh:
            xr = x0 * cos_a + z0 * sin_a
            zr = -x0 * sin_a + z0 * cos_a
            dist = cam_dist - zr
            if dist > 0.2:
                sx = int(half_w + (xr / dist) * scale_x)
                sy = int(half_h + (y0 / dist) * scale_y)
                if 0 <= sx < w and 0 <= sy < h and zr > zbuf[sy][sx]:
                    zbuf[sy][sx] = zr
                    buf[sy][sx] = ch
                    if kind == "foliage":
                        nrx = nx0 * cos_a + nz0 * sin_a
                        nrz = -nx0 * sin_a + nz0 * cos_a
                        diff = -(nrx * lx + ny0 * ly + nrz * lz)
                        diff = max(0.18, min(1.0, diff * 0.65 + 0.35))
                        cbuf[sy][sx] = (int(25 * diff), int(220 * diff + 35), int(65 * diff))
                    else:
                        cbuf[sy][sx] = (150, 92, 48)

        for ox0, oy0, oz0, ch, base_col, phase in self.ornaments:
            ox = ox0 * cos_a + oz0 * sin_a
            oz = -ox0 * sin_a + oz0 * cos_a
            dist = cam_dist - oz
            if dist > 0.2:
                sx = int(half_w + (ox / dist) * scale_x)
                sy = int(half_h + (oy0 / dist) * scale_y)
                if 0 <= sx < w and 0 <= sy < h and oz >= zbuf[sy][sx] - 0.12:
                    zbuf[sy][sx] = oz + 0.05
                    buf[sy][sx] = ch
                    blink = 0.5 * (math.sin(t * 4.5 + phase) + 1.0)
                    mult = 0.42 if blink < 0.25 else 1.0
                    cbuf[sy][sx] = (int(base_col[0] * mult), int(base_col[1] * mult), int(base_col[2] * mult))

        star_sx = int(half_w)
        star_sy = int(half_h + (-1.58 / cam_dist) * scale_y)
        if 1 <= star_sy < h - 1 and 1 <= star_sx < w - 1:
            star_shapes = [
                (" * ", "/*\\", " \\ "),
                (" + ", "<*>", " /\\"),
                (" * ", "-*-", " \\ "),
                (" + ", "\\*/", " /\\"),
            ]
            shape = star_shapes[int((angle * 3.5) % 4)]
            for dy_i, row_str in enumerate(shape, start=-1):
                for dx_i, ch in enumerate(row_str, start=-1):
                    px, py = star_sx + dx_i, star_sy + dy_i
                    if 0 <= px < w and 0 <= py < h and ch != " ":
                        buf[py][px] = ch
                        cbuf[py][px] = (255, 235, 70)
                        zbuf[py][px] = 999.0

        for sx0, sy0, sz0, spd, ch in self.snow:
            y_cur = ((sy0 + t * spd + 2.1) % 4.2) - 2.1
            drift_x = sx0 + math.sin(t * 1.5 + y_cur) * 0.14
            dist = cam_dist - sz0
            if dist > 0.2:
                sx = int(half_w + (drift_x / dist) * scale_x)
                sy = int(half_h + (y_cur / dist) * scale_y)
                if 0 <= sx < w and 0 <= sy < h and buf[sy][sx] == " ":
                    buf[sy][sx] = ch
                    cbuf[sy][sx] = (220, 238, 255)

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class DNAHelix3DRenderer(BaseProceduralRenderer):
    """3D Double Helix DNA with color-coded A-T / G-C base pairs and Z-depth shading."""

    def __init__(self, width: int = 44, height: int = 24, params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(width, height, params)
        self.R = 1.35
        self.h_total = 3.2
        self.cam_dist = 4.2
        self.aspect = 0.52
        self.base_pairs = [
            ("A", "T", (255, 65, 65), (255, 215, 0)),
            ("G", "C", (55, 235, 90), (0, 220, 255)),
            ("T", "A", (255, 215, 0), (255, 65, 65)),
            ("C", "G", (0, 220, 255), (55, 235, 90)),
        ]
        rng = random.Random(1337)
        self._on_grid_resized()

    def _on_grid_resized(self) -> None:
        rng = random.Random(1337)
        self.particles = [
            (rng.randrange(self.width), rng.randrange(self.height), rng.choice([".", "'", "+", "*"]), rng.uniform(0, 6.28))
            for _ in range(max(10, (self.width * self.height) // 55))
        ]

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        scale_y = h * 0.84
        scale_x = scale_y * self.aspect * 1.85
        if (scale_x * 0.35) > (w * 0.46):
            scale_x = (w * 0.46) / 0.35
            scale_y = scale_x / (self.aspect * 1.85)

        angle = t * 1.3 + self.yaw_offset + self.cursor_look[0] * 0.35
        R = self.R
        cam_dist = self.cam_dist
        half_w, half_h = w / 2.0, h / 2.0

        buf = [[" "] * w for _ in range(h)]
        zbuf = [[-999.0] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]

        n_rungs = 18
        for irung in range(n_rungs):
            frac = irung / (n_rungs - 1)
            y = -self.h_total / 2.0 + frac * self.h_total
            theta = y * 2.1 + angle
            x1, z1 = R * math.cos(theta), R * math.sin(theta)
            x2, z2 = -x1, -z1

            b1_ch, b2_ch, b1_rgb, b2_rgb = self.base_pairs[irung % len(self.base_pairs)]
            steps = 14
            for s in range(1, steps):
                u = s / steps
                rx = x1 + u * (x2 - x1)
                rz = z1 + u * (z2 - z1)
                dist = cam_dist - rz
                if dist > 0.1:
                    sx = int(half_w + (rx / dist) * scale_x)
                    sy = int(half_h + (y / dist) * scale_y)
                    if 0 <= sx < w and 0 <= sy < h and rz > zbuf[sy][sx] - 0.05:
                        zbuf[sy][sx] = rz
                        if s == 2:
                            ch, col = b1_ch, b1_rgb
                        elif s == steps - 2:
                            ch, col = b2_ch, b2_rgb
                        elif s == steps // 2:
                            ch, col = "=", (210, 215, 250)
                        else:
                            ch = "-"
                            col = b1_rgb if s < steps // 2 else b2_rgb
                        depth_b = max(0.32, min(1.0, (rz + R) / (2.0 * R) * 0.6 + 0.4))
                        buf[sy][sx] = ch
                        cbuf[sy][sx] = (int(col[0] * depth_b), int(col[1] * depth_b), int(col[2] * depth_b))

        n_points = 120
        chains = ((0.0, (0, 225, 255)), (math.pi, (255, 75, 205)))
        for ip in range(n_points):
            frac = ip / (n_points - 1)
            y = -self.h_total / 2.0 + frac * self.h_total
            theta = y * 2.1 + angle
            for phase, base_col in chains:
                x = R * math.cos(theta + phase)
                z = R * math.sin(theta + phase)
                dist = cam_dist - z
                if dist > 0.1:
                    sx = int(half_w + (x / dist) * scale_x)
                    sy = int(half_h + (y / dist) * scale_y)
                    if 0 <= sx < w and 0 <= sy < h and z > zbuf[sy][sx]:
                        zbuf[sy][sx] = z
                        ch = "@" if z > 0.4 else ("O" if z > -0.4 else "o")
                        depth_b = max(0.35, min(1.0, (z + R) / (2.0 * R) * 0.65 + 0.35))
                        buf[sy][sx] = ch
                        cbuf[sy][sx] = (int(base_col[0] * depth_b), int(base_col[1] * depth_b), int(base_col[2] * depth_b))

        for px, py, ch, phase in self.particles:
            if buf[py][px] == " ":
                tw = 0.55 + 0.45 * math.sin(t * 2.2 + phase)
                buf[py][px] = ch
                cbuf[py][px] = (int(90 * tw), int(145 * tw), int(195 * tw))

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class OceanWave3DRenderer(BaseProceduralRenderer):
    """3D Perspective Ocean Swell Shader with normal lighting and pure ASCII foam crests."""

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        buf = [[" "] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]
        ramp_max = len(WAVE_RAMP) - 1

        horizon = max(2, min(h - 4, int(h * (0.28 + max(-0.14, min(0.18, self.pitch_offset * 0.14))))))
        moon_shift = max(-0.35, min(0.35, (self.yaw_offset * 0.16) + self.cursor_look[0] * 0.10))
        moon_x = int(w * (0.72 + moon_shift))
        for y in range(horizon):
            for x in range(w):
                dx = (x - moon_x) * 0.55
                dy = y - (horizon * 0.45)
                d2 = dx * dx + dy * dy
                if d2 < 3.2:
                    buf[y][x] = "@" if d2 < 1.3 else "+"
                    cbuf[y][x] = (255, 245, 200)
                elif ((x * 37 + y * 91) % 73) == 0:
                    tw = 0.6 + 0.4 * math.sin(t * 2.0 + x)
                    buf[y][x] = "*" if (x % 2 == 0) else "."
                    cbuf[y][x] = (int(160 * tw), int(195 * tw), int(245 * tw))

        for sy in range(horizon, h):
            depth = (sy - horizon + 1) / max(1, (h - horizon))
            z = 1.0 / (0.12 + depth * 0.88)
            for sx in range(w):
                wx = (sx - w * 0.5) * 0.12 * z + self.yaw_offset * 2.5
                wz = z * 2.4 - t * 1.9 + self.pitch_offset * 1.5

                h1 = math.sin(wx * 0.9 + wz * 1.1) * 0.55
                h2 = math.sin(wx * 1.7 - wz * 0.75 + t * 0.8) * 0.28
                h3 = math.cos(wx * 2.6 + wz * 1.9 - t * 1.3) * 0.14
                elev = h1 + h2 + h3

                slope = (
                    math.cos(wx * 0.9 + wz * 1.1) * 0.50
                    + math.cos(wx * 1.7 - wz * 0.75 + t * 0.8) * 0.35
                )
                crest = max(0.0, min(1.0, (elev + 0.6) / 1.55))
                glint = max(0.0, 1.0 - abs(sx - moon_x) / (w * 0.16)) * (0.4 + 0.6 * max(0.0, slope))

                lum = max(0.08, min(1.0, 0.22 + crest * 0.55 + slope * 0.18 + glint * 0.45))
                ch = WAVE_RAMP[int(lum * ramp_max)]
                if crest > 0.78:
                    ch = "~" if ((sx + sy + int(t * 8)) % 2 == 0) else "^"

                buf[sy][sx] = ch
                if crest > 0.80 or glint > 0.55:
                    cbuf[sy][sx] = (
                        min(255, int(190 + 65 * lum)),
                        min(255, int(235 + 20 * lum)),
                        255,
                    )
                else:
                    cbuf[sy][sx] = (
                        int(12 + 40 * lum),
                        int(75 + 135 * lum),
                        int(135 + 115 * lum),
                    )

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class FireplaceThermalRenderer(BaseProceduralRenderer):
    """Thermodynamic cellular heat-diffusion fireplace with glowing classic ASCII logs."""

    def __init__(self, width: int = 48, height: int = 22, params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(width, height, params)
        self.rng = random.Random(77)
        self._on_grid_resized()

    def _on_grid_resized(self) -> None:
        self.heat = [[0.0] * self.width for _ in range(self.height)]
        for i in range(24):
            self._advance_heat(i * 0.04)

    def _advance_heat(self, t: float) -> None:
        w, h = self.width, self.height
        rng = self.rng
        margin = max(4, w // 6)
        for x in range(margin, w - margin):
            dist_center = abs(x - w / 2.0) / max(1.0, (w / 2.0 - margin))
            base = (1.0 - dist_center * 0.55) * (0.85 + 0.25 * math.sin(t * 7.0 + x * 0.6))
            self.heat[h - 2][x] = min(1.0, max(0.0, base + rng.uniform(-0.15, 0.22)))
            self.heat[h - 1][x] = min(1.0, base * 0.9)

        new_heat = [[0.0] * w for _ in range(h)]
        new_heat[h - 1] = list(self.heat[h - 1])
        new_heat[h - 2] = list(self.heat[h - 2])

        for y in range(h - 3, -1, -1):
            for x in range(1, w - 1):
                below = self.heat[y + 1][x]
                below_l = self.heat[y + 1][x - 1]
                below_r = self.heat[y + 1][x + 1]
                below2 = self.heat[min(h - 1, y + 2)][x]
                avg = (below * 0.44 + below_l * 0.22 + below_r * 0.22 + below2 * 0.12)
                cool = 0.042 + rng.uniform(0.0, 0.045)
                val = max(0.0, avg - cool)
                wind = int(round(math.sin(t * 4.0 + y * 0.45) * 0.45))
                nx = max(1, min(w - 2, x + wind))
                new_heat[y][nx] = max(new_heat[y][nx], val)

        self.heat = new_heat

    def step(
        self,
        dt: float,
        speed_mult: float = 1.0,
        yaw_offset: float = 0.0,
        pitch_offset: float = 0.0,
        cursor_look: Tuple[float, float] = (0.0, 0.0),
        progress: Optional[float] = None,
    ) -> ProceduralFrame:
        self.t += dt * speed_mult
        self.yaw_offset = yaw_offset
        self.pitch_offset = pitch_offset
        self.cursor_look = cursor_look
        self.progress = progress
        self._advance_heat(self.t)
        return self._to_frame(self.t)

    def render_at(self, t: float) -> ProceduralFrame:
        self._advance_heat(t)
        return self._to_frame(t)

    def _to_frame(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        buf = [[" "] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]
        ramp_max = len(THERMAL_RAMP) - 1

        for y in range(h - 2):
            for x in range(w):
                val = self.heat[y][x]
                if val > 0.08:
                    idx = min(ramp_max, max(1, int(val * ramp_max)))
                    buf[y][x] = THERMAL_RAMP[idx]
                    if val > 0.82:
                        cbuf[y][x] = (255, 250, min(255, int(190 + (val - 0.82) * 350)))
                    elif val > 0.56:
                        u = (val - 0.56) / 0.26
                        cbuf[y][x] = (255, int(150 + 95 * u), int(20 + 130 * u))
                    elif val > 0.28:
                        u = (val - 0.28) / 0.28
                        cbuf[y][x] = (int(210 + 45 * u), int(45 + 105 * u), 10)
                    else:
                        u = val / 0.28
                        cbuf[y][x] = (int(90 + 120 * u), int(15 + 30 * u), 5)

        margin = max(3, w // 7)
        for x in range(margin, w - margin):
            buf[h - 2][x] = "#" if (x % 3 == 0) else "="
            cbuf[h - 2][x] = (175, 85, 35) if (x % 4) else (255, 130, 30)
            buf[h - 1][x] = "_"
            cbuf[h - 1][x] = (130, 72, 38)

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class MatrixRainHDRenderer(BaseProceduralRenderer):
    """Multi-layer Matrix Digital Rain using crisp pure classic ASCII glyphs."""

    GLYPHS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz@#$%&*+=<>/"

    def __init__(self, width: int = 50, height: int = 22, params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(width, height, params)
        self._on_grid_resized()

    def _on_grid_resized(self) -> None:
        rng = random.Random(1999)
        self.cols = []
        for x in range(self.width):
            active = (x % 2 == 0) or rng.random() < 0.45
            speed = rng.uniform(5.0, 14.0)
            offset = rng.uniform(0.0, self.height * 2.0)
            trail = rng.randint(5, max(7, self.height - 4))
            depth = rng.uniform(0.55, 1.0)
            self.cols.append((active, speed, offset, trail, depth))

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        buf = [[" "] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]
        glen = len(self.GLYPHS)
        span = h + 12

        for x, (active, speed, offset, trail, depth) in enumerate(self.cols):
            if not active:
                continue
            head_y = (offset + t * speed) % span
            head_iy = int(head_y)
            for dy in range(trail):
                y = head_iy - dy
                if 0 <= y < h:
                    g_idx = (x * 17 + y * 31 + int(t * 6.0) + dy) % glen
                    buf[y][x] = self.GLYPHS[g_idx]
                    if dy == 0:
                        cbuf[y][x] = (220, 255, 230)
                    elif dy == 1:
                        cbuf[y][x] = (90, 255, 145)
                    else:
                        fade = max(0.15, (1.0 - dy / trail) * depth)
                        cbuf[y][x] = (0, int(235 * fade), int(85 * fade))

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class GalaxyVortex3DRenderer(BaseProceduralRenderer):
    """3D Tilted Spiral Galaxy & Black Hole Accretion Disk with Z-buffer."""

    def __init__(self, width: int = 52, height: int = 24, params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(width, height, params)
        rng = random.Random(9001)
        self.particles: List[Tuple[float, float, float, float, str, int]] = []
        for i in range(420):
            arm = i % 3
            r = 0.28 + (rng.random() ** 0.75) * 2.15
            theta = arm * (2.0 * math.pi / 3.0) + r * 2.35 + rng.gauss(0.0, 0.24)
            yj = rng.gauss(0.0, 0.08 * (1.0 - r / 2.6))
            ang_spd = 1.65 / (0.35 + r * 0.75)
            ch = rng.choice(["*", "+", "o", ".", ","] if r < 1.2 else [".", ",", "*", "+"])
            self.particles.append((r, theta, yj, ang_spd, ch, arm))

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        aspect = 0.52
        tilt = max(-1.35, min(1.35, 0.62 + self.pitch_offset * 0.7))
        cos_t, sin_t = math.cos(tilt), math.sin(tilt)
        cam_dist = 4.5
        scale = min(h * 0.66, w * aspect * 0.62)
        half_w, half_h = w / 2.0, h / 2.0

        buf = [[" "] * w for _ in range(h)]
        zbuf = [[-999.0] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]

        cx, cy = int(half_w), int(half_h)
        for dy in range(-2, 3):
            for dx in range(-4, 5):
                px, py = cx + dx, cy + dy
                if 0 <= px < w and 0 <= py < h:
                    d = math.sqrt((dx * aspect) ** 2 + dy ** 2)
                    if d < 2.1:
                        buf[py][px] = "@" if d < 0.8 else ("#" if d < 1.4 else "*")
                        cbuf[py][px] = (255, 245, 200) if d < 1.2 else (255, 200, 120)
                        zbuf[py][px] = 0.1

        arm_colors = [(110, 225, 255), (195, 130, 255), (255, 165, 110)]
        for r, theta0, yj, ang_spd, ch, arm in self.particles:
            th = theta0 + t * ang_spd + self.yaw_offset
            x0 = r * math.cos(th)
            z0 = r * math.sin(th)
            y1 = yj * cos_t - z0 * sin_t
            z1 = yj * sin_t + z0 * cos_t

            dist = cam_dist - z1
            if dist > 0.3:
                sx = int(half_w + (x0 / dist) * scale / aspect)
                sy = int(half_h + (y1 / dist) * scale)
                if 0 <= sx < w and 0 <= sy < h and z1 > zbuf[sy][sx]:
                    zbuf[sy][sx] = z1
                    buf[sy][sx] = ch
                    depth_b = max(0.35, min(1.0, (z1 + 2.4) / 4.8 * 0.65 + 0.35))
                    base = arm_colors[arm]
                    core_mix = max(0.0, 1.0 - r / 1.1)
                    cr = int((base[0] * (1.0 - core_mix) + 255 * core_mix) * depth_b)
                    cg = int((base[1] * (1.0 - core_mix) + 235 * core_mix) * depth_b)
                    cb = int((base[2] * (1.0 - core_mix) + 180 * core_mix) * depth_b)
                    cbuf[sy][sx] = (min(255, cr), min(255, cg), min(255, cb))

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class Heart3DRenderer(BaseProceduralRenderer):
    """3D Rotating & Beating Parametric Heart Surface with ruby/rose ASCII lighting."""

    def __init__(self, width: int = 48, height: int = 22, params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(width, height, params)
        # Precompute 3D volumetric/surface heart samples (u around outline, v depth thickness)
        self.samples: List[Tuple[float, float, float, float, float, float]] = []
        n_u = 72
        n_v = 24
        for iu in range(n_u):
            u = (iu / n_u) * 2.0 * math.pi
            # Classic parametric heart curve
            hx = 16.0 * (math.sin(u) ** 3)
            hy = -(
                13.0 * math.cos(u)
                - 5.0 * math.cos(2.0 * u)
                - 2.0 * math.cos(3.0 * u)
                - math.cos(4.0 * u)
            )
            # Tangent for outer normal
            dxu = 48.0 * (math.sin(u) ** 2) * math.cos(u)
            dyu = (
                13.0 * math.sin(u)
                - 10.0 * math.sin(2.0 * u)
                - 6.0 * math.sin(3.0 * u)
                - 4.0 * math.sin(4.0 * u)
            )
            tl = math.hypot(dxu, dyu) or 1.0
            nx_2d, ny_2d = dyu / tl, -dxu / tl

            hx /= 16.0
            hy = (hy - 2.0) / 16.0

            # Revolve cross-section profile across front/back thickness
            for iv in range(n_v + 1):
                phi = -math.pi * 0.5 + (iv / n_v) * math.pi  # -pi/2 .. pi/2
                # Radial pinch factor toward center and front/back bulge
                radial = math.cos(phi) ** 0.72
                z = 0.52 * math.sin(phi) * (1.0 - 0.15 * abs(hx))
                # Blend radial toward center (0, 0.1) so surface stays smooth & filled
                x = hx * (0.28 + 0.72 * radial)
                y = hy * (0.28 + 0.72 * radial)
                nz = math.sin(phi)
                nx = nx_2d * math.cos(phi)
                ny = ny_2d * math.cos(phi)
                nl = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                self.samples.append((x, y, z, nx / nl, ny / nl, nz / nl))
                if abs(z) > 0.02:
                    self.samples.append((x, y, -z, nx / nl, ny / nl, -nz / nl))

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        aspect = 0.52
        pulse = 1.0 + 0.085 * (max(0.0, math.sin(t * 3.6)) ** 4)
        scale_y = h * 0.41 * pulse
        scale_x = scale_y / aspect
        if scale_x * 1.15 > w * 0.46:
            scale_x = (w * 0.46) / 1.15
            scale_y = scale_x * aspect

        yaw = t * 1.15 + self.yaw_offset + self.cursor_look[0] * 0.35
        pitch = 0.22 * math.sin(t * 0.75) + self.pitch_offset + self.cursor_look[1] * 0.25
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)

        lx, ly, lz = -0.45, -0.52, -0.72
        ll = math.sqrt(lx * lx + ly * ly + lz * lz)
        lx, ly, lz = lx / ll, ly / ll, lz / ll

        buf = [[" "] * w for _ in range(h)]
        zbuf = [[-999.0] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]
        half_w, half_h = w / 2.0, h / 2.0
        cam_dist = 3.8
        ramp_max = len(DONUT_RAMP) - 1

        for x0, y0, z0, nx0, ny0, nz0 in self.samples:
            x1 = x0 * cy + z0 * sy
            z1 = -x0 * sy + z0 * cy
            y2 = y0 * cp - z1 * sp
            z2 = y0 * sp + z1 * cp

            dist = cam_dist - z2
            if dist <= 0.2:
                continue
            sx = int(half_w + (x1 / dist) * scale_x * 2.8)
            sy_p = int(half_h + (y2 / dist) * scale_y * 2.8)
            if 0 <= sx < w and 0 <= sy_p < h and z2 > zbuf[sy_p][sx]:
                nrx = nx0 * cy + nz0 * sy
                nrz1 = -nx0 * sy + nz0 * cy
                nry = ny0 * cp - nrz1 * sp
                nrz = ny0 * sp + nrz1 * cp

                diff = max(0.0, -(nrx * lx + nry * ly + nrz * lz))
                spec = diff ** 5
                lum = max(0.08, min(1.0, diff * 0.78 + 0.16 + spec * 0.35))
                zbuf[sy_p][sx] = z2
                buf[sy_p][sx] = DONUT_RAMP[int(lum * ramp_max)]
                r = min(255, int(130 + 125 * lum + 60 * spec))
                g = min(255, int(18 + 65 * lum + 125 * spec))
                b = min(255, int(45 + 75 * lum + 115 * spec))
                cbuf[sy_p][sx] = (r, g, b)

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class CrystalDiamond3DRenderer(BaseProceduralRenderer):
    """3D Rotating Faceted Crystal Gem with normal shading and wireframe ridges."""

    def __init__(self, width: int = 46, height: int = 22, params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(width, height, params)
        # Octahedral / brilliant-cut crystal vertices
        n_seg = 6
        self.verts: List[Tuple[float, float, float]] = [(0.0, -1.25, 0.0), (0.0, 1.35, 0.0)]  # 0: top apex, 1: bottom apex
        for i in range(n_seg):
            a = i * 2.0 * math.pi / n_seg
            self.verts.append((1.05 * math.cos(a), -0.15, 1.05 * math.sin(a)))  # 2..7 equator ring
        self.faces: List[Tuple[int, int, int, str]] = []
        self.edges: List[Tuple[int, int]] = []
        for i in range(n_seg):
            a = 2 + i
            b = 2 + ((i + 1) % n_seg)
            self.faces.append((0, b, a, "@#*=+"[i % 5]))
            self.faces.append((1, a, b, "+=:-."[i % 5]))
            self.edges.extend([(0, a), (1, a), (a, b)])

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        aspect = 0.52
        scale = min(h * 0.42, w * aspect * 0.42) * 2.6
        half_w, half_h = w / 2.0, h / 2.0
        cam_dist = 3.9

        yaw = t * 1.15 + self.yaw_offset + self.cursor_look[0] * 0.35
        pitch = 0.36 + 0.14 * math.sin(t * 0.8) + self.pitch_offset + self.cursor_look[1] * 0.25
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)

        lx, ly, lz = -0.5, -0.55, -0.66
        ll = math.sqrt(lx * lx + ly * ly + lz * lz)
        lx, ly, lz = lx / ll, ly / ll, lz / ll

        rot_v: List[Tuple[float, float, float]] = []
        proj_v: List[Tuple[float, float, float]] = []
        for vx, vy, vz in self.verts:
            x1 = vx * cy + vz * sy
            z1 = -vx * sy + vz * cy
            y2 = vy * cp - z1 * sp
            z2 = vy * sp + z1 * cp
            rot_v.append((x1, y2, z2))
            dist = cam_dist - z2
            px = half_w + (x1 / dist) * scale
            py = half_h + (y2 / dist) * scale * aspect
            proj_v.append((px, py, z2))

        buf = [[" "] * w for _ in range(h)]
        zbuf = [[-999.0] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]
        ramp_max = len(CHARS_RAMP) - 1

        # Fill visible facets via barycentric sampling
        for i0, i1, i2, _ in self.faces:
            v0, v1, v2 = rot_v[i0], rot_v[i1], rot_v[i2]
            e1 = (v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2])
            e2 = (v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2])
            nx = e1[1] * e2[2] - e1[2] * e2[1]
            ny = e1[2] * e2[0] - e1[0] * e2[2]
            nz = e1[0] * e2[1] - e1[1] * e2[0]
            nl = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            nx, ny, nz = nx / nl, ny / nl, nz / nl

            p0, p1, p2 = proj_v[i0], proj_v[i1], proj_v[i2]
            # Screen-space bounding box
            min_x = max(0, int(math.floor(min(p0[0], p1[0], p2[0]))))
            max_x = min(w - 1, int(math.ceil(max(p0[0], p1[0], p2[0]))))
            min_y = max(0, int(math.floor(min(p0[1], p1[1], p2[1]))))
            max_y = min(h - 1, int(math.ceil(max(p0[1], p1[1], p2[1]))))

            area = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1])
            if abs(area) < 1e-4:
                continue

            diff = max(0.0, -(nx * lx + ny * ly + nz * lz))
            spec = diff ** 6
            lum = max(0.14, min(1.0, diff * 0.75 + 0.16 + spec * 0.45))
            ch = CHARS_RAMP[max(1, int(lum * ramp_max))]
            col: RGB = (
                min(255, int(65 + 155 * lum + 85 * spec)),
                min(255, int(165 + 90 * lum)),
                min(255, int(215 + 40 * lum)),
            )

            for py in range(min_y, max_y + 1):
                for px in range(min_x, max_x + 1):
                    w0 = ((p1[0] - px) * (p2[1] - py) - (p2[0] - px) * (p1[1] - py)) / area
                    w1 = ((p2[0] - px) * (p0[1] - py) - (p0[0] - px) * (p2[1] - py)) / area
                    w2 = 1.0 - w0 - w1
                    if (w0 >= -0.02 and w1 >= -0.02 and w2 >= -0.02) or (w0 <= 0.02 and w1 <= 0.02 and w2 <= 0.02):
                        z = w0 * p0[2] + w1 * p1[2] + w2 * p2[2]
                        if z > zbuf[py][px]:
                            zbuf[py][px] = z
                            buf[py][px] = ch
                            cbuf[py][px] = col

        # Crisp wireframe edges over ridges
        for a, b in self.edges:
            pa, pb = proj_v[a], proj_v[b]
            _draw_line_z(buf, zbuf, cbuf, w, h, pa[0], pa[1], pa[2] + 0.04, pb[0], pb[1], pb[2] + 0.04, "+", (220, 250, 255))

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class Cube3DRenderer(BaseProceduralRenderer):
    """3D Shaded & Wireframe Rotating Neon Cube (true Z-buffer multi-axis cube)."""

    FACES = (
        ((-1, -1, 1), (1, -1, 1), (1, 1, 1), (-1, 1, 1), (0, 0, 1), "@", (80, 235, 255)),
        ((1, -1, -1), (-1, -1, -1), (-1, 1, -1), (1, 1, -1), (0, 0, -1), "#", (245, 95, 225)),
        ((-1, -1, -1), (-1, -1, 1), (-1, 1, 1), (-1, 1, -1), (-1, 0, 0), "*", (120, 255, 165)),
        ((1, -1, 1), (1, -1, -1), (1, 1, -1), (1, 1, 1), (1, 0, 0), "=", (255, 200, 90)),
        ((-1, -1, -1), (1, -1, -1), (1, -1, 1), (-1, -1, 1), (0, -1, 0), "+", (150, 175, 255)),
        ((-1, 1, 1), (1, 1, 1), (1, 1, -1), (-1, 1, -1), (0, 1, 0), ":", (255, 125, 165)),
    )

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        aspect = 0.52
        scale = min(h * 0.42, w * aspect * 0.40) * 2.15
        half_w, half_h = w / 2.0, h / 2.0
        cam_dist = 4.6

        A, B, C = t * 1.1 + self.pitch_offset, t * 0.78 + self.yaw_offset + self.cursor_look[0] * 0.35, t * 0.45
        ca, sa = math.cos(A), math.sin(A)
        cb, sb = math.cos(B), math.sin(B)
        cc, sc = math.cos(C), math.sin(C)

        def rot(x: float, y: float, z: float) -> Tuple[float, float, float]:
            # X
            y1 = y * ca - z * sa
            z1 = y * sa + z * ca
            # Y
            x2 = x * cb + z1 * sb
            z2 = -x * sb + z1 * cb
            # Z
            x3 = x2 * cc - y1 * sc
            y3 = x2 * sc + y1 * cc
            return x3, y3, z2

        buf = [[" "] * w for _ in range(h)]
        zbuf = [[-999.0] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]
        lx, ly, lz = -0.45, -0.55, -0.70

        step = 0.08
        for p0, p1, p2, p3, (nx0, ny0, nz0), face_ch, base_col in self.FACES:
            nrx, nry, nrz = rot(nx0, ny0, nz0)
            diff = max(0.18, min(1.0, -(nrx * lx + nry * ly + nrz * lz) * 0.75 + 0.30))

            u = -1.0
            while u <= 1.001:
                v = -1.0
                while v <= 1.001:
                    is_edge = abs(u) > 0.88 or abs(v) > 0.88
                    if abs(nx0) > 0.5:
                        lx0, ly0, lz0 = nx0, u, v
                    elif abs(ny0) > 0.5:
                        lx0, ly0, lz0 = u, ny0, v
                    else:
                        lx0, ly0, lz0 = u, v, nz0

                    xr, yr, zr = rot(lx0, ly0, lz0)
                    dist = cam_dist - zr
                    if dist > 0.3:
                        sx = int(half_w + (xr / dist) * scale / aspect)
                        sy = int(half_h + (yr / dist) * scale)
                        if 0 <= sx < w and 0 <= sy < h and zr > zbuf[sy][sx]:
                            zbuf[sy][sx] = zr
                            if is_edge:
                                buf[sy][sx] = "+" if (abs(u) > 0.88 and abs(v) > 0.88) else "-"
                                cbuf[sy][sx] = (240, 252, 255)
                            else:
                                buf[sy][sx] = face_ch
                                cbuf[sy][sx] = (
                                    int(base_col[0] * diff),
                                    int(base_col[1] * diff),
                                    int(base_col[2] * diff),
                                )
                    v += step
                u += step

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class Pyramid3DRenderer(BaseProceduralRenderer):
    """3D Golden Rotating Pyramid with Z-buffer sunlit shading and desert shimmer."""

    VERTS = (
        (0.0, -1.35, 0.0),   # apex
        (-1.1, 0.95, 1.1),
        (1.1, 0.95, 1.1),
        (1.1, 0.95, -1.1),
        (-1.1, 0.95, -1.1),
    )
    TRIS = (
        (0, 1, 2),
        (0, 2, 3),
        (0, 3, 4),
        (0, 4, 1),
    )

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        aspect = 0.52
        scale = min(h * 0.42, w * aspect * 0.40) * 2.55
        half_w, half_h = w / 2.0, h / 2.0
        cam_dist = 4.2

        yaw = t * 0.95 + self.yaw_offset + self.cursor_look[0] * 0.35
        pitch = 0.25 + self.pitch_offset + self.cursor_look[1] * 0.25
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)
        lx, ly, lz = -0.60, -0.45, -0.66

        rot_v: List[Tuple[float, float, float]] = []
        proj_v: List[Tuple[float, float, float]] = []
        for vx, vy, vz in self.VERTS:
            x1 = vx * cy + vz * sy
            z1 = -vx * sy + vz * cy
            y2 = vy * cp - z1 * sp
            z2 = vy * sp + z1 * cp
            rot_v.append((x1, y2, z2))
            d = cam_dist - z2
            proj_v.append((half_w + (x1 / d) * scale, half_h + (y2 / d) * scale * aspect, z2))

        buf = [[" "] * w for _ in range(h)]
        zbuf = [[-999.0] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]
        ramp_max = len(CHARS_RAMP) - 1

        for i0, i1, i2 in self.TRIS:
            v0, v1, v2 = rot_v[i0], rot_v[i1], rot_v[i2]
            e1 = (v1[0] - v0[0], v1[1] - v0[1], v1[2] - v0[2])
            e2 = (v2[0] - v0[0], v2[1] - v0[1], v2[2] - v0[2])
            nx = e1[1] * e2[2] - e1[2] * e2[1]
            ny = e1[2] * e2[0] - e1[0] * e2[2]
            nz = e1[0] * e2[1] - e1[1] * e2[0]
            nl = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
            nx, ny, nz = nx / nl, ny / nl, nz / nl

            p0, p1, p2 = proj_v[i0], proj_v[i1], proj_v[i2]
            min_x = max(0, int(math.floor(min(p0[0], p1[0], p2[0]))))
            max_x = min(w - 1, int(math.ceil(max(p0[0], p1[0], p2[0]))))
            min_y = max(0, int(math.floor(min(p0[1], p1[1], p2[1]))))
            max_y = min(h - 1, int(math.ceil(max(p0[1], p1[1], p2[1]))))

            area = (p1[0] - p0[0]) * (p2[1] - p0[1]) - (p2[0] - p0[0]) * (p1[1] - p0[1])
            if abs(area) < 1e-4:
                continue

            diff = max(0.12, min(1.0, -(nx * lx + ny * ly + nz * lz) * 0.78 + 0.28))
            ch = CHARS_RAMP[max(1, int(diff * ramp_max))]
            col: RGB = (min(255, int(250 * diff + 15)), min(255, int(195 * diff + 10)), int(55 * diff))

            for py in range(min_y, max_y + 1):
                for px in range(min_x, max_x + 1):
                    w0 = ((p1[0] - px) * (p2[1] - py) - (p2[0] - px) * (p1[1] - py)) / area
                    w1 = ((p2[0] - px) * (p0[1] - py) - (p0[0] - px) * (p2[1] - py)) / area
                    w2 = 1.0 - w0 - w1
                    if w0 >= -0.02 and w1 >= -0.02 and w2 >= -0.02:
                        z = w0 * p0[2] + w1 * p1[2] + w2 * p2[2]
                        if z > zbuf[py][px]:
                            zbuf[py][px] = z
                            # Brick horizontal banding
                            buf[py][px] = "=" if ((py % 2 == 0) and diff > 0.45) else ch
                            cbuf[py][px] = col

        for a, b in ((0, 1), (0, 2), (0, 3), (0, 4), (1, 2), (2, 3), (3, 4), (4, 1)):
            pa, pb = proj_v[a], proj_v[b]
            _draw_line_z(buf, zbuf, cbuf, w, h, pa[0], pa[1], pa[2] + 0.04, pb[0], pb[1], pb[2] + 0.04, "*", (255, 240, 140))

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class GlobeEarth3DRenderer(BaseProceduralRenderer):
    """3D Raytraced Spinning Earth Globe with procedural continents, ice caps & stars."""

    def __init__(self, width: int = 50, height: int = 24, params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(width, height, params)
        self.aspect = 0.52
        self.R = 1.0
        self.cam_dist = 3.2
        self._on_grid_resized()

    def _on_grid_resized(self) -> None:
        scale = min(self.height * 0.44, self.width * self.aspect * 0.44)
        self._rays: List[List[Tuple[float, float, float]]] = []
        fov = 1.48
        for py in range(self.height):
            vy = (py - self.height / 2.0) / scale
            row: List[Tuple[float, float, float]] = []
            for px in range(self.width):
                vx = (px - self.width / 2.0) / scale * self.aspect
                dl = math.sqrt(vx * vx + vy * vy + fov * fov)
                row.append((vx / dl, vy / dl, fov / dl))
            self._rays.append(row)

        rng = random.Random(303)
        self._stars: Dict[Tuple[int, int], Tuple[str, float]] = {}
        for y in range(self.height):
            for x in range(self.width):
                if rng.random() < 0.025:
                    self._stars[(x, y)] = (rng.choice([".", "*", "+"]), rng.uniform(0.0, 6.28))

    def render_at(self, t: float) -> ProceduralFrame:
        spin = t * 0.9 + self.yaw_offset + self.cursor_look[0] * 0.35
        tilt = max(-1.2, min(1.2, 0.32 + self.pitch_offset * 0.7 + self.cursor_look[1] * 0.22))
        ct, st = math.cos(tilt), math.sin(tilt)
        lx, ly, lz = -0.60, -0.45, -0.66
        oz = -self.cam_dist
        o2_r2 = oz * oz - 1.0
        ramp_max = len(CHARS_RAMP) - 1

        lines: List[str] = []
        colors: List[List[Optional[RGB]]] = []

        for py in range(self.height):
            row_chars = [" "] * self.width
            row_cols: List[Optional[RGB]] = [None] * self.width
            row_rays = self._rays[py]

            for px in range(self.width):
                dx, dy, dz = row_rays[px]
                b = 2.0 * oz * dz
                disc = b * b - 4.0 * o2_r2
                if disc >= 0.0:
                    ts = (-b - math.sqrt(disc)) * 0.5
                    if ts > 0.0:
                        hx = ts * dx
                        hy = ts * dy
                        hz = oz + ts * dz
                        # Axial tilt
                        ry = hy * ct - hz * st
                        rz = hy * st + hz * ct
                        lon = math.atan2(rz, hx) + spin
                        lat = math.asin(max(-1.0, min(1.0, ry)))

                        diff = max(0.0, -(hx * lx + hy * ly + hz * lz))
                        lum = max(0.09, min(1.0, diff * 0.85 + 0.16))

                        # Continents noise
                        cont = (
                            math.sin(lon * 2.0 + math.cos(lat * 2.5)) * 0.55
                            + math.cos(lon * 3.0 - lat * 3.2) * 0.35
                            + math.sin(lat * 4.5 + lon * 1.5) * 0.25
                        )
                        is_pole = abs(lat) > 1.24 + 0.08 * math.sin(lon * 3.0)
                        row_chars[px] = CHARS_RAMP[max(1, int(lum * ramp_max))]
                        if is_pole:
                            row_cols[px] = (int(235 * lum), int(245 * lum), 255)
                        elif cont > 0.18:
                            if cont > 0.62:
                                row_cols[px] = (int(195 * lum), int(175 * lum), int(105 * lum))
                            else:
                                row_cols[px] = (int(45 * lum), int(215 * lum + 20), int(85 * lum))
                        else:
                            row_cols[px] = (int(25 * lum), int(115 * lum + 25), int(235 * lum + 20))
                        continue

                star = self._stars.get((px, py))
                if star:
                    ch, phase = star
                    tw = 0.6 + 0.4 * math.sin(t * 2.4 + phase)
                    row_chars[px] = ch
                    row_cols[px] = (int(180 * tw), int(205 * tw), int(250 * tw))

            lines.append("".join(row_chars))
            colors.append(row_cols)

        return ProceduralFrame(lines=lines, colors=colors)


class Atom3DRenderer(BaseProceduralRenderer):
    """3D Quantum Atom Nucleus with 3 tilted 3D electron orbital rings and Z-occlusion."""

    def __init__(self, width: int = 48, height: int = 22, params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(width, height, params)
        self.orbits = (
            (0.45, 0.25, (80, 230, 255), 2.6, 0.0),
            (0.45, 1.30, (255, 105, 220), 2.9, 2.1),
            (0.45, 2.35, (255, 215, 95), 3.2, 4.2),
        )
        rng = random.Random(707)
        self.nucleons: List[Tuple[float, float, float, str, RGB]] = []
        for i in range(28):
            th = rng.uniform(0, 2 * math.pi)
            ph = rng.uniform(-1, 1)
            r = 0.28 * (rng.random() ** 0.33)
            sr = math.sqrt(max(0.0, 1 - ph * ph))
            x, y, z = r * sr * math.cos(th), r * ph, r * sr * math.sin(th)
            col = (255, 95, 110) if i % 2 == 0 else (255, 200, 90)
            self.nucleons.append((x, y, z, "@" if i % 3 == 0 else "O", col))

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        aspect = 0.52
        scale = min(h * 0.43, w * aspect * 0.43) * 2.5
        half_w, half_h = w / 2.0, h / 2.0
        cam_dist = 4.0

        buf = [[" "] * w for _ in range(h)]
        zbuf = [[-999.0] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]

        # Nucleus wobble
        nw = t * 1.4 + self.yaw_offset
        cn, sn = math.cos(nw), math.sin(nw)
        for nx0, ny0, nz0, ch, col in self.nucleons:
            x = nx0 * cn + nz0 * sn
            z = -nx0 * sn + nz0 * cn
            d = cam_dist - z
            sx = int(half_w + (x / d) * scale / aspect)
            sy = int(half_h + (ny0 / d) * scale)
            if 0 <= sx < w and 0 <= sy < h and z > zbuf[sy][sx]:
                zbuf[sy][sx] = z
                buf[sy][sx] = ch
                cbuf[sy][sx] = col

        # 3 tilted rings + fast electrons
        R = 1.45
        for tilt_x, tilt_z, ring_col, spd, phase0 in self.orbits:
            ctx, stx = math.cos(tilt_x + self.pitch_offset * 0.6), math.sin(tilt_x + self.pitch_offset * 0.6)
            ctz, stz = math.cos(tilt_z + t * 0.22 + self.yaw_offset * 0.4), math.sin(tilt_z + t * 0.22 + self.yaw_offset * 0.4)
            for k in range(84):
                a = k * 2.0 * math.pi / 84
                ox, oy, oz = R * math.cos(a), 0.0, R * math.sin(a)
                # tilt around x then rotate around z
                y1 = oy * ctx - oz * stx
                z1 = oy * stx + oz * ctx
                x2 = ox * ctz - y1 * stz
                y2 = ox * stz + y1 * ctz
                d = cam_dist - z1
                sx = int(half_w + (x2 / d) * scale / aspect)
                sy = int(half_h + (y2 / d) * scale)
                if 0 <= sx < w and 0 <= sy < h and z1 > zbuf[sy][sx]:
                    zbuf[sy][sx] = z1
                    fade = max(0.28, min(0.85, (z1 + R) / (2 * R) * 0.55 + 0.3))
                    buf[sy][sx] = "." if fade < 0.55 else "+"
                    cbuf[sy][sx] = (int(ring_col[0] * fade), int(ring_col[1] * fade), int(ring_col[2] * fade))

            # Glowing electron + short comet tail
            e_base = phase0 + t * spd
            for tail_i in range(6):
                ea = e_base - tail_i * 0.14
                ox, oy, oz = R * math.cos(ea), 0.0, R * math.sin(ea)
                y1 = oy * ctx - oz * stx
                z1 = oy * stx + oz * ctx
                x2 = ox * ctz - y1 * stz
                y2 = ox * stz + y1 * ctz
                d = cam_dist - z1
                sx = int(half_w + (x2 / d) * scale / aspect)
                sy = int(half_h + (y2 / d) * scale)
                if 0 <= sx < w and 0 <= sy < h and z1 >= zbuf[sy][sx] - 0.1:
                    zbuf[sy][sx] = z1 + 0.05
                    if tail_i == 0:
                        buf[sy][sx] = "@"
                        cbuf[sy][sx] = (255, 255, 255)
                    else:
                        buf[sy][sx] = "*" if tail_i < 3 else "-"
                        f = 1.0 - tail_i * 0.14
                        cbuf[sy][sx] = (int(ring_col[0] * f), int(ring_col[1] * f), int(ring_col[2] * f))

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class Coffee3DRenderer(BaseProceduralRenderer):
    """3D Slowly Turning Ceramic Coffee Mug with swirling crema and live ASCII steam."""

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        aspect = 0.52
        scale_y = h * 0.38
        scale_x = scale_y / aspect
        if scale_x * 1.4 > w * 0.46:
            scale_x = (w * 0.46) / 1.4
            scale_y = scale_x * aspect

        buf = [[" "] * w for _ in range(h)]
        zbuf = [[-999.0] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]

        half_w, half_h = w / 2.0, h * 0.62
        cam_dist = 4.2
        yaw = math.sin(t * 0.7) * 0.55 + self.yaw_offset + self.cursor_look[0] * 0.35
        pitch = max(-0.9, min(1.2, 0.34 + self.pitch_offset + self.cursor_look[1] * 0.22))
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)
        lx, ly, lz = -0.58, -0.40, -0.70
        ramp_max = len(CHARS_RAMP) - 1

        # 1. Cup cylinder (y from -0.45 top rim to +0.85 base)
        R_cup = 0.92
        for iy in range(28):
            fy = iy / 27.0
            y0 = -0.45 + fy * 1.30
            r_cur = R_cup * (1.0 - 0.10 * (fy ** 1.8))
            for iphi in range(64):
                phi = iphi * 2.0 * math.pi / 64.0
                x0 = r_cur * math.cos(phi)
                z0 = r_cur * math.sin(phi)
                nx0, ny0, nz0 = math.cos(phi), 0.1, math.sin(phi)

                x1 = x0 * cy + z0 * sy
                z1 = -x0 * sy + z0 * cy
                y2 = y0 * cp - z1 * sp
                z2 = y0 * sp + z1 * cp

                d = cam_dist - z2
                sx = int(half_w + (x1 / d) * scale_x * 2.8)
                sy_p = int(half_h + (y2 / d) * scale_y * 2.8)
                if 0 <= sx < w and 0 <= sy_p < h and z2 > zbuf[sy_p][sx]:
                    nrx = nx0 * cy + nz0 * sy
                    nrz1 = -nx0 * sy + nz0 * cy
                    nrz = ny0 * sp + nrz1 * cp
                    diff = max(0.14, min(1.0, -(nrx * lx + ny0 * ly + nrz * lz) * 0.75 + 0.28))
                    zbuf[sy_p][sx] = z2
                    if iy <= 1:
                        buf[sy_p][sx] = "="
                        cbuf[sy_p][sx] = (245, 236, 220)
                    else:
                        buf[sy_p][sx] = CHARS_RAMP[max(1, int(diff * ramp_max))]
                        cbuf[sy_p][sx] = (int(230 * diff + 25), int(205 * diff + 20), int(175 * diff + 15))

        # 2. Mug handle on right side
        for ia in range(26):
            a = -math.pi * 0.46 + (ia / 25.0) * math.pi * 0.92
            x0 = R_cup * 0.95 + 0.36 * math.cos(a)
            y0 = 0.18 + 0.42 * math.sin(a)
            z0 = 0.0
            x1 = x0 * cy + z0 * sy
            z1 = -x0 * sy + z0 * cy
            y2 = y0 * cp - z1 * sp
            z2 = y0 * sp + z1 * cp
            d = cam_dist - z2
            sx = int(half_w + (x1 / d) * scale_x * 2.8)
            sy_p = int(half_h + (y2 / d) * scale_y * 2.8)
            if 0 <= sx < w and 0 <= sy_p < h and z2 >= zbuf[sy_p][sx] - 0.05:
                zbuf[sy_p][sx] = z2
                buf[sy_p][sx] = ")" if math.cos(a) > 0.2 else "-"
                cbuf[sy_p][sx] = (230, 200, 170)

        # 3. Top coffee crema disk
        y0 = -0.34
        for ir in range(1, 14):
            rr = (ir / 13.0) * (R_cup * 0.88)
            for iphi in range(44):
                phi = iphi * 2.0 * math.pi / 44.0
                x0 = rr * math.cos(phi)
                z0 = rr * math.sin(phi)
                x1 = x0 * cy + z0 * sy
                z1 = -x0 * sy + z0 * cy
                y2 = y0 * cp - z1 * sp
                z2 = y0 * sp + z1 * cp
                d = cam_dist - z2
                sx = int(half_w + (x1 / d) * scale_x * 2.8)
                sy_p = int(half_h + (y2 / d) * scale_y * 2.8)
                if 0 <= sx < w and 0 <= sy_p < h and z2 > zbuf[sy_p][sx]:
                    swirl = math.sin(rr * 8.0 + phi * 2.0 - t * 2.5)
                    zbuf[sy_p][sx] = z2
                    buf[sy_p][sx] = "~" if swirl > 0.2 else "="
                    cbuf[sy_p][sx] = (210, 150, 95) if swirl > 0.35 else (115, 65, 32)

        # 4. Live curling ASCII steam columns above the cup
        rim_y = max(3, int(half_h - scale_y * 1.15))
        for col_i, x_off in enumerate((-5, -1, 3, 6)):
            for step_y in range(1, rim_y):
                frac = step_y / max(1, rim_y)
                sy = rim_y - step_y
                sway = math.sin(t * 3.2 - step_y * 0.55 + col_i * 1.6) * (1.2 + frac * 1.5)
                sx = int(round(half_w + x_off + sway))
                if 0 <= sx < w and 0 <= sy < h and buf[sy][sx] == " ":
                    ch = ("~", "(", ")", "'", ".")[int((step_y + t * 5 + col_i) % 5)]
                    if frac > 0.72:
                        ch = "." if (step_y % 2) else "'"
                    fade = max(0.25, 1.0 - frac * 0.75)
                    buf[sy][sx] = ch
                    cbuf[sy][sx] = (int(225 * fade), int(235 * fade), int(250 * fade))

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class Snowflake3DRenderer(BaseProceduralRenderer):
    """3D Rotating Crystalline Dendritic Snowflake with icy blue/white specular shimmer."""

    def __init__(self, width: int = 48, height: int = 24, params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(width, height, params)
        self.points: List[Tuple[float, float, float, str]] = []
        for arm in range(6):
            ang = arm * math.pi / 3.0
            ux, uy = math.cos(ang), math.sin(ang)
            px, py = -uy, ux
            # Main spine
            for k in range(1, 18):
                r = k * 0.082
                ch = "@" if k < 4 else ("*" if k % 3 == 0 else "+")
                self.points.append((ux * r, uy * r, 0.03 * math.sin(k), ch))
                self.points.append((ux * r, uy * r, -0.03 * math.sin(k), ch))
            # Dendritic side branches
            for br_r, br_len in ((0.48, 0.36), (0.88, 0.44), (1.18, 0.25)):
                bx, by = ux * br_r, uy * br_r
                for side in (-1.0, 1.0):
                    dx = ux * 0.6 + px * side * 0.8
                    dy = uy * 0.6 + py * side * 0.8
                    for s in range(1, 7):
                        d = (s / 6.0) * br_len
                        self.points.append((bx + dx * d, by + dy * d, 0.02 * side, "*" if s == 6 else "+"))

        rng = random.Random(1225)
        self.flurries = [
            (rng.randrange(self.width), rng.randrange(self.height), rng.uniform(0.6, 1.6), rng.choice([".", ",", "'"]))
            for _ in range(36)
        ]

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        aspect = 0.52
        scale = min(h * 0.42, w * aspect * 0.42) * 2.2
        half_w, half_h = w / 2.0, h / 2.0
        cam_dist = 3.8

        yaw = t * 1.15 + self.yaw_offset + self.cursor_look[0] * 0.35
        pitch = 0.45 * math.sin(t * 0.7) + self.pitch_offset + self.cursor_look[1] * 0.25
        roll = t * 0.35
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)
        cr, sr = math.cos(roll), math.sin(roll)

        buf = [[" "] * w for _ in range(h)]
        zbuf = [[-999.0] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]

        for x0, y0, z0, ch in self.points:
            # Z roll
            xr = x0 * cr - y0 * sr
            yr = x0 * sr + y0 * cr
            # Y yaw
            x1 = xr * cy + z0 * sy
            z1 = -xr * sy + z0 * cy
            # X pitch
            y2 = yr * cp - z1 * sp
            z2 = yr * sp + z1 * cp

            d = cam_dist - z2
            sx = int(half_w + (x1 / d) * scale / aspect)
            sy_p = int(half_h + (y2 / d) * scale)
            if 0 <= sx < w and 0 <= sy_p < h and z2 > zbuf[sy_p][sx]:
                zbuf[sy_p][sx] = z2
                buf[sy_p][sx] = ch
                depth = max(0.35, min(1.0, (z2 + 1.5) / 3.0 * 0.6 + 0.4))
                sparkle = 1.0 if ch in ("@", "*") else depth
                cbuf[sy_p][sx] = (int(165 * sparkle + 50), int(230 * sparkle + 25), 255)

        for fx0, fy0, spd, ch in self.flurries:
            fy = int((fy0 + t * spd * 3.0) % h)
            fx = int((fx0 + math.sin(t + fy * 0.4) * 1.5) % w)
            if buf[fy][fx] == " ":
                buf[fy][fx] = ch
                cbuf[fy][fx] = (170, 215, 250)

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class AuroraShaderRenderer(BaseProceduralRenderer):
    """Northern Lights Aurora Borealis Curtain Shader over Starry Pine Ridge."""

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        buf = [[" "] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]
        ramp = " .:-=+*#%@"
        ramp_max = len(ramp) - 1

        horizon = h - 4
        phase_yaw = self.yaw_offset * 1.8
        shift_pitch = max(-0.22, min(0.22, self.pitch_offset * 0.18 + self.cursor_look[1] * 0.08))
        for y in range(horizon):
            ny = y / max(1, horizon)
            for x in range(w):
                nx = x / max(1, w)
                # Multi-curtain sine field
                w1 = math.sin(nx * 7.5 + phase_yaw + t * 0.9 + math.sin(ny * 3.2 - t * 0.5))
                w2 = math.cos(nx * 13.0 - phase_yaw * 0.8 - t * 1.2 + ny * 4.0)
                band = math.exp(-((ny - 0.35 - shift_pitch - 0.14 * w1) ** 2) * 14.0)
                shimmer = max(0.0, 0.55 * band + 0.30 * band * (w2 * 0.5 + 0.5))
                if shimmer > 0.14:
                    lum = min(1.0, shimmer * 1.15)
                    buf[y][x] = ramp[max(1, int(lum * ramp_max))]
                    # Emerald bottom -> Cyan middle -> Violet upper glow
                    if ny < 0.25:
                        cbuf[y][x] = (int(175 * lum), int(95 * lum), int(255 * lum))
                    elif ny < 0.48:
                        cbuf[y][x] = (int(55 * lum), int(235 * lum), int(210 * lum))
                    else:
                        cbuf[y][x] = (int(45 * lum), int(255 * lum), int(125 * lum))
                elif ((x * 41 + y * 67) % 89) == 0:
                    tw = 0.6 + 0.4 * math.sin(t * 2.1 + x)
                    buf[y][x] = "*" if (x % 3 == 0) else "."
                    cbuf[y][x] = (int(175 * tw), int(195 * tw), int(240 * tw))

        # Pine silhouette mountain ridge at bottom
        for x in range(w):
            ridge_h = int(2 + 1.5 * math.sin(x * 0.22) + (x % 3 == 0))
            for y in range(max(0, h - ridge_h), h):
                is_tip = y == h - ridge_h
                buf[y][x] = "^" if is_tip else ("/" if (x + y) % 2 == 0 else "\\")
                cbuf[y][x] = (40, 85, 70)

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class WarpStars3DRenderer(BaseProceduralRenderer):
    """3D Hyperspace Star Tunnel with radial Doppler streaks."""

    def __init__(self, width: int = 50, height: int = 22, params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(width, height, params)
        rng = random.Random(1977)
        self.stars = [
            (rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0), rng.uniform(0.15, 4.0), rng.uniform(0.9, 2.2))
            for _ in range(180)
        ]

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        half_w, half_h = w / 2.0, h / 2.0
        vanish_x = max(4.0, min(w - 5.0, half_w + (self.yaw_offset * 0.25 + self.cursor_look[0] * 0.22) * half_w))
        vanish_y = max(3.0, min(h - 4.0, half_h + (self.pitch_offset * 0.25 + self.cursor_look[1] * 0.22) * half_h))
        buf = [[" "] * w for _ in range(h)]
        zbuf = [[999.0] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]

        buf[int(vanish_y)][int(vanish_x)] = "+"
        cbuf[int(vanish_y)][int(vanish_x)] = (120, 175, 255)

        for x0, y0, z0, spd in self.stars:
            if abs(x0) < 0.03 and abs(y0) < 0.03:
                continue
            z = ((z0 - t * spd) % 3.85) + 0.15
            sx = int(vanish_x + (x0 / z) * half_w * 0.9)
            sy = int(vanish_y + (y0 / z) * half_h * 0.9)
            if 0 <= sx < w and 0 <= sy < h and z < zbuf[sy][sx]:
                zbuf[sy][sx] = z
                closeness = 1.0 - (z / 4.0)
                if closeness > 0.78:
                    ch = "@"
                elif closeness > 0.58:
                    ch = "*"
                elif closeness > 0.36:
                    ch = "+"
                else:
                    ch = "."
                buf[sy][sx] = ch
                cbuf[sy][sx] = (
                    min(255, int(110 + 145 * closeness)),
                    min(255, int(170 + 85 * closeness)),
                    255,
                )

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class Hourglass3DRenderer(BaseProceduralRenderer):
    """3D Revolving & Flowing Sand Hourglass, optionally synced to Pomodoro progress."""

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        aspect = 0.52
        scale_y = h * 0.42
        scale_x = scale_y / aspect
        if scale_x * 1.1 > w * 0.45:
            scale_x = (w * 0.45) / 1.1
            scale_y = scale_x * aspect

        buf = [[" "] * w for _ in range(h)]
        zbuf = [[-999.0] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]

        half_w, half_h = w / 2.0, h / 2.0
        cam_dist = 4.3
        yaw = t * 0.65 + self.yaw_offset + self.cursor_look[0] * 0.35
        pitch = 0.22 + 0.08 * math.sin(t * 0.8) + self.pitch_offset + self.cursor_look[1] * 0.2
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)
        lx, ly, lz = -0.55, -0.45, -0.70

        # Sand fill fraction: synced to Pomodoro remaining fraction if available, else 20s cycle
        frac_rem = self.progress if self.progress is not None else (1.0 - ((t % 16.0) / 16.0))
        frac_rem = max(0.02, min(0.98, frac_rem))
        top_sand_cutoff = -0.95 * frac_rem  # y in [-0.95 .. 0.0]
        bot_sand_top = 0.95 - 0.90 * (1.0 - frac_rem)  # y in [0.05 .. 0.95]

        def proj(x0: float, y0: float, z0: float) -> Tuple[int, int, float]:
            x1 = x0 * cy + z0 * sy
            z1 = -x0 * sy + z0 * cy
            y2 = y0 * cp - z1 * sp
            z2 = y0 * sp + z1 * cp
            d = cam_dist - z2
            return int(half_w + (x1 / d) * scale_x * 2.1), int(half_h + (y2 / d) * scale_y * 2.1), z2

        # 1. Top and bottom wooden frame rings + vertical pillars
        for cap_y in (-1.02, 1.02):
            for ip in range(56):
                phi = ip * 2.0 * math.pi / 56.0
                for rr in (0.72, 0.82, 0.90):
                    sx, sy_p, z2 = proj(rr * math.cos(phi), cap_y, rr * math.sin(phi))
                    if 0 <= sx < w and 0 <= sy_p < h and z2 > zbuf[sy_p][sx]:
                        zbuf[sy_p][sx] = z2
                        buf[sy_p][sx] = "=" if rr > 0.84 else "-"
                        cbuf[sy_p][sx] = (175, 115, 65) if rr > 0.80 else (130, 82, 42)

        for p_idx in range(3):
            pang = p_idx * (2.0 * math.pi / 3.0) + 0.4
            px0, pz0 = 0.84 * math.cos(pang), 0.84 * math.sin(pang)
            for iy in range(28):
                y0 = -0.98 + (iy / 27.0) * 1.96
                sx, sy_p, z2 = proj(px0, y0, pz0)
                if 0 <= sx < w and 0 <= sy_p < h and z2 > zbuf[sy_p][sx]:
                    zbuf[sy_p][sx] = z2
                    buf[sy_p][sx] = "|"
                    cbuf[sy_p][sx] = (165, 110, 60)

        # 2. Outer glass shell (double cone pinched at waist)
        n_y = 32
        for iy in range(n_y + 1):
            y0 = -0.96 + (iy / n_y) * 1.92
            ay = abs(y0)
            r_glass = 0.08 + 0.72 * (ay ** 0.78)
            for ip in range(44):
                phi = ip * 2.0 * math.pi / 44.0
                x0 = r_glass * math.cos(phi)
                z0 = r_glass * math.sin(phi)
                sx, sy_p, z2 = proj(x0, y0, z0)
                if 0 <= sx < w and 0 <= sy_p < h and z2 > zbuf[sy_p][sx]:
                    nrx = math.cos(phi) * cy + math.sin(phi) * sy
                    nrz1 = -math.cos(phi) * sy + math.sin(phi) * cy
                    nrz = nrz1 * cp
                    spec = max(0.0, -(nrx * lx + nrz * lz))
                    rim = abs(z2) < 0.25 or spec > 0.82
                    if rim or (iy % 5 == 0 and ip % 3 == 0):
                        zbuf[sy_p][sx] = z2
                        buf[sy_p][sx] = "*" if spec > 0.88 else ("/" if (x0 * y0 < 0) else "\\")
                        if abs(y0) < 0.14:
                            buf[sy_p][sx] = ":"
                        cbuf[sy_p][sx] = (205, 242, 255) if spec > 0.85 else (115, 195, 230)

        # 3. Warm golden sand in top cone & bottom pile + falling stream
        for iy in range(22):
            y0 = -0.92 + (iy / 21.0) * 1.84
            in_top_sand = (y0 < 0.0) and (y0 >= top_sand_cutoff)
            in_bot_sand = (y0 > 0.04) and (y0 >= bot_sand_top)
            if not (in_top_sand or in_bot_sand):
                continue
            r_max = 0.05 + 0.64 * (abs(y0) ** 0.78)
            if in_bot_sand:
                cone_frac = (y0 - bot_sand_top) / max(0.08, 0.94 - bot_sand_top)
                r_max = min(r_max, 0.08 + cone_frac * 0.65)
            for ir in (0.35, 0.7, 1.0):
                rr = r_max * ir
                for ip in range(18):
                    phi = ip * 2.0 * math.pi / 18.0
                    sx, sy_p, z2 = proj(rr * math.cos(phi), y0, rr * math.sin(phi))
                    if 0 <= sx < w and 0 <= sy_p < h and z2 + 0.04 > zbuf[sy_p][sx]:
                        zbuf[sy_p][sx] = z2 + 0.04
                        buf[sy_p][sx] = "#" if ir < 0.6 else ("*" if ((iy + ip) % 2 == 0) else ":")
                        cbuf[sy_p][sx] = (255, 212, 105) if (iy % 2 == 0) else (235, 175, 65)

        # Falling sand grains through neck
        for gi in range(10):
            yg = ((gi / 10.0 + t * 1.8) % 1.0) * max(0.15, bot_sand_top)
            sx, sy_p, z2 = proj(math.sin(t * 9 + gi) * 0.02, yg, 0.0)
            if 0 <= sx < w and 0 <= sy_p < h:
                buf[sy_p][sx] = "." if gi % 2 else ":"
                cbuf[sy_p][sx] = (255, 232, 145)

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class CatBust3DRenderer(BaseProceduralRenderer):
    """3D Sculpted Geometric Cat Bust with ear tufts, whiskers, blinking & cursor-tracking eyes."""

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        aspect = 0.52
        scale_y = h * 0.42
        scale_x = scale_y / aspect
        if scale_x * 1.25 > w * 0.46:
            scale_x = (w * 0.46) / 1.25
            scale_y = scale_x * aspect

        buf = [[" "] * w for _ in range(h)]
        zbuf = [[-999.0] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]
        half_w, half_h = w / 2.0, h / 2.0
        cam_dist = 4.0

        yaw = math.sin(t * 0.85) * 0.42 + self.yaw_offset + self.cursor_look[0] * 0.45
        pitch = 0.10 + math.sin(t * 1.2) * 0.05 + self.pitch_offset + self.cursor_look[1] * 0.25
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)
        lx, ly, lz = -0.52, -0.50, -0.69
        ramp_max = len(CHARS_RAMP) - 1

        def plot(x0: float, y0: float, z0: float, nx0: float, ny0: float, nz0: float, kind: str) -> None:
            x1 = x0 * cy + z0 * sy
            z1 = -x0 * sy + z0 * cy
            y2 = y0 * cp - z1 * sp
            z2 = y0 * sp + z1 * cp
            d = cam_dist - z2
            if d <= 0.2:
                return
            sx = int(half_w + (x1 / d) * scale_x * 2.15)
            sy_p = int(half_h + (y2 / d) * scale_y * 2.15)
            if 0 <= sx < w and 0 <= sy_p < h and z2 > zbuf[sy_p][sx]:
                nrx = nx0 * cy + nz0 * sy
                nrz1 = -nx0 * sy + nz0 * cy
                nry = ny0 * cp - nrz1 * sp
                nrz = ny0 * sp + nrz1 * cp
                diff = max(0.14, min(1.0, -(nrx * lx + nry * ly + nrz * lz) * 0.78 + 0.28))
                zbuf[sy_p][sx] = z2
                if kind == "eye":
                    blink = (t % 4.2) > 4.0
                    buf[sy_p][sx] = "-" if blink else "O"
                    cbuf[sy_p][sx] = (255, 210, 120) if blink else (95, 255, 165)
                elif kind == "nose":
                    buf[sy_p][sx] = "v"
                    cbuf[sy_p][sx] = (255, 130, 165)
                elif kind == "ear_in":
                    buf[sy_p][sx] = "^"
                    cbuf[sy_p][sx] = (255, 155, 185)
                elif kind == "collar":
                    buf[sy_p][sx] = "="
                    cbuf[sy_p][sx] = (255, 85, 115)
                elif kind == "whisker":
                    buf[sy_p][sx] = "-" if x0 < 0 else "-"
                    cbuf[sy_p][sx] = (235, 225, 215)
                else:
                    buf[sy_p][sx] = CHARS_RAMP[max(1, int(diff * ramp_max))]
                    cbuf[sy_p][sx] = (int(245 * diff + 20), int(185 * diff + 25), int(135 * diff + 25))

        # 1. Head ellipsoid
        for iv in range(28):
            phi = -math.pi * 0.5 + (iv / 27.0) * math.pi
            for iu in range(44):
                th = iu * 2.0 * math.pi / 44.0
                cx_u, sx_u = math.cos(th), math.sin(th)
                cphi, sphi = math.cos(phi), math.sin(phi)
                x0 = 0.78 * cphi * cx_u
                y0 = -0.18 + 0.66 * sphi
                z0 = 0.70 * cphi * sx_u
                plot(x0, y0, z0, cphi * cx_u, sphi, cphi * sx_u, "fur")

        # 2. Pointed cat ears
        for side in (-1.0, 1.0):
            for ih in range(12):
                f = ih / 11.0
                r_e = 0.26 * (1.0 - f) + 0.03
                y_e = -0.70 - f * 0.48
                x_c = side * (0.46 + f * 0.14)
                for ia in range(16):
                    a = ia * 2.0 * math.pi / 16.0
                    ex = x_c + r_e * math.cos(a)
                    ez = 0.05 + r_e * math.sin(a)
                    kind = "ear_in" if (math.sin(a) < -0.35 and 0.15 < f < 0.78) else "fur"
                    plot(ex, y_e, ez, math.cos(a), -0.3, math.sin(a), kind)

        # 3. Shoulders + collar
        for iy in range(16):
            f = iy / 15.0
            y0 = 0.42 + f * 0.68
            r_s = 0.48 + f * 0.34
            for iu in range(36):
                a = iu * 2.0 * math.pi / 36.0
                kind = "collar" if iy in (1, 2) else "fur"
                plot(r_s * math.cos(a), y0, r_s * 0.72 * math.sin(a), math.cos(a), 0.1, math.sin(a), kind)

        # 4. Eyes, nose & whiskers
        lx_off = self.cursor_look[0] * 0.06
        ly_off = self.cursor_look[1] * 0.04
        for side in (-1.0, 1.0):
            plot(side * 0.28 + lx_off, -0.22 + ly_off, -0.71, 0.0, 0.0, -1.0, "eye")
            plot(side * 0.28 + lx_off, -0.25 + ly_off, -0.70, 0.0, 0.0, -1.0, "eye")
        plot(0.0, -0.05, -0.73, 0.0, 0.0, -1.0, "nose")

        for side in (-1.0, 1.0):
            for wi in range(1, 5):
                for wy in (-0.06, 0.04):
                    wx = side * (0.48 + wi * 0.14)
                    plot(wx, wy + wi * 0.015, -0.64, side * 0.5, 0.0, -0.8, "whisker")

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class OwlBust3DRenderer(BaseProceduralRenderer):
    """3D Geometric Wise Owl Bust with feathered chest, ear tufts & cursor-tracking eyes."""

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        aspect = 0.52
        scale_y = h * 0.42
        scale_x = scale_y / aspect
        if scale_x * 1.2 > w * 0.46:
            scale_x = (w * 0.46) / 1.2
            scale_y = scale_x * aspect

        buf = [[" "] * w for _ in range(h)]
        zbuf = [[-999.0] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]
        half_w, half_h = w / 2.0, h / 2.0
        cam_dist = 4.1

        yaw = math.sin(t * 0.55) * 0.35 + self.yaw_offset + self.cursor_look[0] * 0.52
        pitch = 0.08 + self.pitch_offset + self.cursor_look[1] * 0.25
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)
        lx, ly, lz = -0.5, -0.5, -0.7

        def plot(x0: float, y0: float, z0: float, nx0: float, ny0: float, nz0: float, kind: str) -> None:
            x1 = x0 * cy + z0 * sy
            z1 = -x0 * sy + z0 * cy
            y2 = y0 * cp - z1 * sp
            z2 = y0 * sp + z1 * cp
            d = cam_dist - z2
            if d <= 0.2:
                return
            sx = int(half_w + (x1 / d) * scale_x * 2.1)
            sy_p = int(half_h + (y2 / d) * scale_y * 2.1)
            if 0 <= sx < w and 0 <= sy_p < h and z2 > zbuf[sy_p][sx]:
                nrx = nx0 * cy + nz0 * sy
                nrz1 = -nx0 * sy + nz0 * cy
                nrz = ny0 * sp + nrz1 * cp
                diff = max(0.15, min(1.0, -(nrx * lx + ny0 * ly + nrz * lz) * 0.75 + 0.3))
                zbuf[sy_p][sx] = z2
                if kind == "eye_ring":
                    buf[sy_p][sx] = "O"
                    cbuf[sy_p][sx] = (255, 220, 95)
                elif kind == "pupil":
                    blink = (t % 4.8) > 4.6
                    buf[sy_p][sx] = "-" if blink else "@"
                    cbuf[sy_p][sx] = (250, 215, 110) if blink else (255, 255, 255)
                elif kind == "beak":
                    buf[sy_p][sx] = "v"
                    cbuf[sy_p][sx] = (255, 165, 45)
                elif kind == "branch":
                    buf[sy_p][sx] = "="
                    cbuf[sy_p][sx] = (140, 90, 50)
                else:
                    buf[sy_p][sx] = "v" if (y0 > 0.15 and int((x0 + y0) * 9) % 2 == 0) else CHARS_RAMP[max(1, int(diff * 8))]
                    if y0 > 0.10 and z0 < -0.15:
                        cbuf[sy_p][sx] = (int(235 * diff + 20), int(215 * diff + 20), int(185 * diff + 15))
                    else:
                        cbuf[sy_p][sx] = (int(175 * diff + 20), int(130 * diff + 15), int(95 * diff + 15))

        # Body & head combined ovoid
        for iy in range(34):
            phi = -math.pi * 0.5 + (iy / 33.0) * math.pi
            y0 = 0.05 + 0.92 * math.sin(phi)
            rx = (0.76 if y0 < -0.1 else 0.86) * math.cos(phi)
            for iu in range(44):
                a = iu * 2.0 * math.pi / 44.0
                plot(rx * math.cos(a), y0, rx * 0.82 * math.sin(a), math.cos(a), math.sin(phi), math.sin(a), "feather")

        # Ear tufts
        for side in (-1.0, 1.0):
            for k in range(8):
                f = k / 7.0
                plot(side * (0.46 + f * 0.25), -0.80 - f * 0.26, -0.05, side * 0.5, -0.5, -0.5, "feather")

        # Big golden eyes & beak
        look_x = self.cursor_look[0] * 0.06
        look_y = self.cursor_look[1] * 0.05
        for side in (-1.0, 1.0):
            ex, ey = side * 0.30, -0.34
            for ia in range(14):
                a = ia * 2.0 * math.pi / 14.0
                plot(ex + 0.16 * math.cos(a), ey + 0.16 * math.sin(a), -0.72, 0.0, 0.0, -1.0, "eye_ring")
            plot(ex + look_x, ey + look_y, -0.75, 0.0, 0.0, -1.0, "pupil")
        plot(0.0, -0.18, -0.78, 0.0, 0.0, -1.0, "beak")
        plot(0.0, -0.12, -0.76, 0.0, 0.0, -1.0, "beak")

        # Perch branch
        for ix in range(-18, 19):
            plot(ix * 0.075, 1.02, 0.0, 0.0, -1.0, 0.0, "branch")

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class VinylTurntable3DRenderer(BaseProceduralRenderer):
    """3D Tilted Lo-Fi Spinning Vinyl Turntable with tonearm and live equalizer bars."""

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        aspect = 0.52
        buf = [[" "] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]

        # Top audio spectrum equalizer strip
        eq_h = max(3, int(h * 0.24))
        for x in range(2, w - 2):
            bar = int((0.5 + 0.5 * math.sin(t * 5.2 + x * 0.45) * math.cos(t * 2.8 - x * 0.22)) * eq_h)
            for dy in range(bar):
                y = eq_h - 1 - dy
                if 0 <= y < h:
                    buf[y][x] = "#" if dy == 0 else ("=" if dy % 2 else ":")
                    ratio = dy / max(1, eq_h)
                    cbuf[y][x] = (int(90 + 165 * ratio), int(235 - 110 * ratio), 255)

        # Tilted 3D vinyl record below equalizer
        cx, cy_p = w * 0.44, h * 0.64
        rx_max = min(w * 0.38, (h - eq_h) * 0.88 / aspect)
        tilt = max(0.32, min(0.85, 0.55 + self.pitch_offset * 0.35))
        spin = t * 2.8 + self.yaw_offset

        for y in range(eq_h, h):
            for x in range(w):
                nx = (x - cx) / max(1.0, rx_max)
                ny = ((y - cy_p) / max(1.0, rx_max * aspect)) / tilt
                r = math.sqrt(nx * nx + ny * ny)
                if r <= 1.0:
                    ang = math.atan2(ny, nx)
                    if r < 0.09:
                        buf[y][x] = "@"
                        cbuf[y][x] = (235, 240, 250)
                    elif r < 0.30:
                        marker = math.cos(ang - spin) > 0.72
                        buf[y][x] = "*" if marker else "+"
                        cbuf[y][x] = (255, 235, 130) if marker else (235, 95, 145)
                    elif r > 0.94:
                        buf[y][x] = "=" if abs(nx) < 0.5 else "|"
                        cbuf[y][x] = (145, 175, 210)
                    else:
                        highlight = (math.cos(ang * 2.0 - 0.8) + 1.0) * 0.5
                        groove = (int(r * 18) % 2 == 0)
                        glint = math.cos(ang - spin) > 0.88
                        if glint:
                            buf[y][x] = "*"
                            cbuf[y][x] = (195, 245, 255)
                        elif groove:
                            buf[y][x] = "~" if highlight > 0.55 else "-"
                            v = int(65 + 95 * highlight)
                            cbuf[y][x] = (v, v + 12, v + 32)
                        else:
                            buf[y][x] = "."
                            cbuf[y][x] = (55, 62, 85)

        # Tonearm from top-right resting on groove
        arm_x0, arm_y0 = int(w * 0.84), int(eq_h + 2)
        arm_x1, arm_y1 = int(cx + rx_max * 0.45), int(cy_p + 1 + math.sin(t * 2.0) * 0.4)
        steps = max(4, max(abs(arm_x1 - arm_x0), abs(arm_y1 - arm_y0)))
        for s in range(steps + 1):
            u = s / steps
            px = int(round(arm_x0 + (arm_x1 - arm_x0) * u))
            py = int(round(arm_y0 + (arm_y1 - arm_y0) * u))
            if 0 <= px < w and 0 <= py < h:
                buf[py][px] = "@" if s == 0 else ("=" if s == steps else "/")
                cbuf[py][px] = (255, 210, 110) if s in (0, steps) else (225, 235, 245)

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class RainyWindow3DRenderer(BaseProceduralRenderer):
    """Rainy Night Study Window with city bokeh lights and sliding glass raindrops."""

    def __init__(self, width: int = 50, height: int = 24, params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(width, height, params)
        self._on_grid_resized()

    def _on_grid_resized(self) -> None:
        rng = random.Random(2025)
        self.drops = [
            (rng.randrange(2, max(4, self.width - 2)), rng.uniform(0.0, self.height), rng.uniform(1.8, 5.2))
            for _ in range(max(12, self.width // 2))
        ]
        self.bokeh = [
            (rng.randrange(3, max(5, self.width - 3)), rng.randrange(3, max(5, self.height - 3)),
             rng.choice([(255, 195, 95), (95, 215, 255), (255, 115, 165), (145, 255, 185)]))
            for _ in range(max(10, self.width // 3))
        ]

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        buf = [[" "] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]

        # Warm glowing distant night bokeh
        for bx, by, col in self.bokeh:
            if 1 <= bx < w - 1 and 1 <= by < h - 1:
                pulse = 0.55 + 0.35 * math.sin(t * 2.1 + bx)
                buf[by][bx] = "o" if pulse > 0.72 else "."
                cbuf[by][bx] = (int(col[0] * pulse * 0.75), int(col[1] * pulse * 0.75), int(col[2] * pulse * 0.75))

        # Rain streaks slanting slightly with yaw_offset/wind
        wind = self.yaw_offset * 0.4 + self.cursor_look[0] * 0.3
        for dx0, y0, spd in self.drops:
            yy = (y0 + t * spd) % max(1, h - 2)
            iy = 1 + int(yy)
            ix = 1 + int((dx0 + iy * wind) % max(1, w - 2))
            if 1 <= ix < w - 1 and 1 <= iy < h - 1:
                buf[iy][ix] = "o" if spd > 4.0 else "|"
                cbuf[iy][ix] = (175, 232, 255)
                if iy - 1 >= 1:
                    buf[iy - 1][ix] = "'"
                    cbuf[iy - 1][ix] = (110, 175, 225)
                if iy - 2 >= 1 and buf[iy - 2][ix] == " ":
                    buf[iy - 2][ix] = "."
                    cbuf[iy - 2][ix] = (75, 125, 175)

        # Crisp wooden window frame + crossbars
        mid_x, mid_y = w // 2, h // 2
        for x in range(w):
            buf[0][x] = "="
            buf[h - 1][x] = "="
            buf[mid_y][x] = "-"
            cbuf[0][x] = cbuf[h - 1][x] = (180, 125, 80)
            cbuf[mid_y][x] = (145, 98, 62)
        for y in range(h):
            buf[y][0] = "|"
            buf[y][w - 1] = "|"
            buf[y][mid_x] = "|"
            cbuf[y][0] = cbuf[y][w - 1] = (180, 125, 80)
            cbuf[y][mid_x] = (145, 98, 62)
        for cx, cy_c in ((0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1), (mid_x, mid_y)):
            buf[cy_c][cx] = "+"
            cbuf[cy_c][cx] = (220, 165, 110)

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class Lantern3DRenderer(BaseProceduralRenderer):
    """3D Swinging Japanese Paper Lantern (Chochin) with warm glowing core."""

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        aspect = 0.52
        scale_y = h * 0.42
        scale_x = scale_y / aspect
        if scale_x * 1.15 > w * 0.45:
            scale_x = (w * 0.45) / 1.15
            scale_y = scale_x * aspect

        buf = [[" "] * w for _ in range(h)]
        zbuf = [[-999.0] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]
        half_w, half_h = w / 2.0, h * 0.54
        cam_dist = 4.1

        sway = math.sin(t * 1.8) * 0.16 + self.cursor_look[0] * 0.18
        yaw = t * 0.6 + self.yaw_offset
        pitch = 0.15 + self.pitch_offset
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)
        cs, ss = math.cos(sway), math.sin(sway)

        def proj(x0: float, y0: float, z0: float) -> Tuple[int, int, float]:
            x1 = x0 * cy + z0 * sy
            z1 = -x0 * sy + z0 * cy
            # Swing pendulum around top anchor y = -1.1
            dy = y0 + 1.05
            xs = x1 * cs - dy * ss
            ys = x1 * ss + dy * cs - 1.05
            y2 = ys * cp - z1 * sp
            z2 = ys * sp + z1 * cp
            d = cam_dist - z2
            return int(half_w + (xs / d) * scale_x * 2.1), int(half_h + (y2 / d) * scale_y * 2.1), z2

        # Hanging cord
        for k in range(6):
            sx, sy_p, _ = proj(0.0, -1.25 + k * 0.06, 0.0)
            if 0 <= sx < w and 0 <= sy_p < h:
                buf[sy_p][sx] = "|"
                cbuf[sy_p][sx] = (200, 170, 120)

        # Lantern body & ribs
        flicker = 0.88 + 0.12 * math.sin(t * 7.5)
        for iv in range(28):
            f = iv / 27.0
            y0 = -0.82 + f * 1.48
            lat = (f - 0.5) * math.pi * 0.88
            rib = 1.0 + 0.05 * math.cos(iv * 3.14)
            rad = 0.72 * math.cos(lat) * rib
            is_cap = iv in (0, 1, 26, 27)
            for ip in range(44):
                a = ip * 2.0 * math.pi / 44.0
                sx, sy_p, z2 = proj(rad * math.cos(a), y0, rad * math.sin(a))
                if 0 <= sx < w and 0 <= sy_p < h and z2 > zbuf[sy_p][sx]:
                    zbuf[sy_p][sx] = z2
                    if is_cap:
                        buf[sy_p][sx] = "="
                        cbuf[sy_p][sx] = (85, 65, 55)
                    else:
                        core = math.exp(-((f - 0.5) ** 2) * 5.0) * flicker
                        buf[sy_p][sx] = "-" if (iv % 3 == 0) else ("*" if core > 0.72 else ":")
                        cbuf[sy_p][sx] = (
                            min(255, int(215 + 40 * core)),
                            min(255, int(55 + 165 * core)),
                            int(35 + 65 * core),
                        )

        # Hanging tassel at bottom
        for k in range(5):
            sx, sy_p, z2 = proj(0.03 * math.sin(t * 3 + k), 0.70 + k * 0.08, 0.0)
            if 0 <= sx < w and 0 <= sy_p < h:
                buf[sy_p][sx] = "|" if k < 4 else "*"
                cbuf[sy_p][sx] = (255, 195, 75)

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class CampTent3DRenderer(BaseProceduralRenderer):
    """3D Shaded A-Frame Tent, glowing campfire, crescent moon & starry night."""

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        aspect = 0.52
        scale_y = h * 0.40
        scale_x = scale_y / aspect
        if scale_x * 1.4 > w * 0.46:
            scale_x = (w * 0.46) / 1.4
            scale_y = scale_x * aspect

        buf = [[" "] * w for _ in range(h)]
        zbuf = [[-999.0] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]
        half_w, half_h = w * 0.44, h * 0.62
        cam_dist = 4.5

        # Night stars & crescent moon
        for y in range(max(1, int(h * 0.48))):
            for x in range(w):
                dx = (x - w * 0.80) * 0.55
                dy = y - h * 0.18
                if dx * dx + dy * dy < 3.0 and (dx + 0.7) ** 2 + (dy + 0.3) ** 2 > 1.8:
                    buf[y][x] = "C" if dx < 0 else ")"
                    cbuf[y][x] = (255, 240, 175)
                elif ((x * 53 + y * 79) % 83) == 0:
                    tw = 0.55 + 0.45 * math.sin(t * 2.3 + x)
                    buf[y][x] = "*" if x % 3 == 0 else "."
                    cbuf[y][x] = (int(175 * tw), int(205 * tw), int(255 * tw))

        yaw = 0.48 + math.sin(t * 0.4) * 0.25 + self.yaw_offset + self.cursor_look[0] * 0.35
        pitch = 0.16 + self.pitch_offset + self.cursor_look[1] * 0.18
        cy, sy = math.cos(yaw), math.sin(yaw)
        cp, sp = math.cos(pitch), math.sin(pitch)

        def plot(x0: float, y0: float, z0: float, ch: str, col: RGB) -> None:
            x1 = x0 * cy + z0 * sy
            z1 = -x0 * sy + z0 * cy
            y2 = y0 * cp - z1 * sp
            z2 = y0 * sp + z1 * cp
            d = cam_dist - z2
            if d <= 0.3:
                return
            sx = int(half_w + (x1 / d) * scale_x * 1.9)
            sy_p = int(half_h + (y2 / d) * scale_y * 1.9)
            if 0 <= sx < w and 0 <= sy_p < h and z2 > zbuf[sy_p][sx]:
                zbuf[sy_p][sx] = z2
                buf[sy_p][sx] = ch
                cbuf[sy_p][sx] = col

        # 3D A-frame tent faces
        for iz in range(24):
            z0 = -0.85 + (iz / 23.0) * 1.70
            for ih in range(20):
                f = ih / 19.0
                y0 = -0.70 + f * 1.15
                hw = f * 0.78
                for side in (-1.0, 1.0):
                    ch = "/" if (side < 0 and iz in (0, 23)) else ("\\" if (side > 0 and iz in (0, 23)) else ("#" if side < 0 else "="))
                    col = (85, 195, 155) if side < 0 else (55, 145, 120)
                    plot(side * hw, y0, z0, ch, col)
                # Warm tent doorway on front z=-0.85
                if iz == 0 and hw * 0.5 > 0.08:
                    ix_max = int(hw * 5)
                    for ix in range(-ix_max, ix_max + 1):
                        plot(ix * 0.08, y0, z0 - 0.02, ":" if y0 > -0.1 else "*", (255, 200, 95))

        # Crackling campfire on right side
        fx, fy = int(w * 0.76), int(h * 0.76)
        for dy in range(-4, 2):
            for dx in range(-3, 4):
                px, py = fx + dx, fy + dy
                if 0 <= px < w and 0 <= py < h:
                    if dy >= 0 and abs(dx) <= 2:
                        buf[py][px] = "=" if dy == 1 else "#"
                        cbuf[py][px] = (155, 92, 48)
                    elif abs(dx) <= max(0, 2 + dy):
                        fl = math.sin(t * 11.0 + dx * 2 + dy) > 0.0
                        buf[py][px] = "^" if fl else "*"
                        cbuf[py][px] = (255, 230, 95) if dy < -1 else (255, 125, 35)

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


class Fireworks3DRenderer(BaseProceduralRenderer):
    """3D Projective Fireworks Starburst Celebration Shader (used for Pomodoro celebrations)."""

    def __init__(self, width: int = 48, height: int = 20, params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(width, height, params)
        rng = random.Random(2026)
        self.bursts: List[Tuple[float, float, float, float, RGB, List[Tuple[float, float, float]]]] = []
        palettes = [
            (255, 95, 145),
            (95, 235, 255),
            (255, 220, 85),
            (155, 130, 255),
            (110, 255, 165),
        ]
        for bi in range(5):
            cx = rng.uniform(-1.1, 1.1)
            cy = rng.uniform(-0.7, 0.3)
            cz = rng.uniform(-0.4, 0.4)
            phase = bi * 0.55
            col = palettes[bi % len(palettes)]
            dirs: List[Tuple[float, float, float]] = []
            for _ in range(44):
                th = rng.uniform(0, 2.0 * math.pi)
                vz = rng.uniform(-1.0, 1.0)
                vr = math.sqrt(max(0.0, 1.0 - vz * vz)) * rng.uniform(0.65, 1.15)
                dirs.append((vr * math.cos(th), vz, vr * math.sin(th)))
            self.bursts.append((cx, cy, cz, phase, col, dirs))

    def render_at(self, t: float) -> ProceduralFrame:
        w, h = self.width, self.height
        aspect = 0.52
        scale = min(h * 0.45, w * aspect * 0.45) * 1.95
        half_w, half_h = w / 2.0, h / 2.0
        buf = [[" "] * w for _ in range(h)]
        cbuf: List[List[Optional[RGB]]] = [[None] * w for _ in range(h)]

        for cx, cy, cz, phase, col, dirs in self.bursts:
            age = (t + phase) % 2.4
            if age < 0.35:
                # Rising rocket trail
                ry = 1.2 - (age / 0.35) * (1.2 - cy)
                sx = int(half_w + cx * scale / aspect)
                sy = int(half_h + ry * scale)
                if 0 <= sx < w and 0 <= sy < h:
                    buf[sy][sx] = "^"
                    cbuf[sy][sx] = (255, 245, 190)
                continue

            b_t = age - 0.35
            fade = max(0.0, 1.0 - b_t / 1.9)
            if fade <= 0.05:
                continue
            gravity = 0.42 * b_t * b_t
            radius = b_t * 1.35
            for dx, dy, _dz in dirs:
                for tail, ch in ((1.0, "*"), (0.78, "+"), (0.56, ".")):
                    px = cx + dx * radius * tail
                    py = cy + dy * radius * tail + gravity * tail
                    sx = int(half_w + px * scale / aspect)
                    sy = int(half_h + py * scale)
                    if 0 <= sx < w and 0 <= sy < h:
                        buf[sy][sx] = "@" if (ch == "*" and fade > 0.72) else ch
                        cbuf[sy][sx] = (
                            min(255, int(col[0] * fade + 35 * fade)),
                            min(255, int(col[1] * fade + 35 * fade)),
                            min(255, int(col[2] * fade + 35 * fade)),
                        )

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


PROCEDURAL_REGISTRY = {
    "saturn_3d": (Saturn3DRenderer, 54, 24),
    "donut_3d": (Donut3DRenderer, 50, 22),
    "christmas_tree_3d": (ChristmasTree3DRenderer, 48, 26),
    "dna_helix_3d": (DNAHelix3DRenderer, 44, 24),
    "ocean_wave_3d": (OceanWave3DRenderer, 52, 22),
    "fireplace_thermal": (FireplaceThermalRenderer, 48, 22),
    "matrix_rain_hd": (MatrixRainHDRenderer, 50, 22),
    "galaxy_vortex_3d": (GalaxyVortex3DRenderer, 52, 24),
    "heart_3d": (Heart3DRenderer, 48, 22),
    "crystal_diamond_3d": (CrystalDiamond3DRenderer, 46, 22),
    "cube_3d": (Cube3DRenderer, 44, 22),
    "pyramid_3d": (Pyramid3DRenderer, 46, 22),
    "globe_earth_3d": (GlobeEarth3DRenderer, 50, 24),
    "atom_3d": (Atom3DRenderer, 48, 22),
    "coffee_3d": (Coffee3DRenderer, 44, 24),
    "snowflake_3d": (Snowflake3DRenderer, 48, 24),
    "aurora_shader": (AuroraShaderRenderer, 52, 22),
    "warp_stars_3d": (WarpStars3DRenderer, 50, 22),
    "hourglass_3d": (Hourglass3DRenderer, 44, 24),
    "cat_bust_3d": (CatBust3DRenderer, 46, 24),
    "owl_bust_3d": (OwlBust3DRenderer, 46, 24),
    "vinyl_turntable_3d": (VinylTurntable3DRenderer, 50, 22),
    "rainy_window_3d": (RainyWindow3DRenderer, 50, 24),
    "lantern_3d": (Lantern3DRenderer, 44, 24),
    "camp_tent_3d": (CampTent3DRenderer, 52, 24),
    "fireworks_3d": (Fireworks3DRenderer, 48, 22),
}


def create_procedural_renderer(
    model_id: str,
    params: Optional[Dict[str, Any]] = None,
) -> Optional[BaseProceduralRenderer]:
    entry = PROCEDURAL_REGISTRY.get(model_id)
    if not entry:
        return None
    cls, def_w, def_h = entry
    p = params or {}
    w = int(p.get("width", def_w))
    h = int(p.get("height", def_h))
    return cls(width=w, height=h, params=p)


# --- Elipsoit tabanlı 3B model motoru (kontur + öznitelik katmanı). DİKKAT: ascii_models'i doğrudan değil,
# bu modül üzerinden içe aktarın (dairesel içe aktarma sırası burada çözülür).
from src.core import ascii_animals as _ascii_animals  # noqa: E402,F401
from src.core import ascii_models as _ascii_models  # noqa: E402

PROCEDURAL_REGISTRY.update(_ascii_models.MODEL_REGISTRY)
