"""Offline SDF ray-marcher (NumPy). HD varlıkları DERLEME anında üretmek için; çalışma anında hiç kullanılmaz.

Model: işaretli uzaklık alanları (küre, elipsoit, kapsül, yuvarlak koni, yuvarlak kutu, torus) → grup içinde yumuşak
birleşim (smin) → gruplar arası sert birleşim. Gölgeleme: anahtar ışık + yumuşak gölge, gök dolgusu, kenar (rim) ışığı,
ortam örtüşmesi (AO), isteğe bağlı speküler ve malzeme deseni. Çıktı: RGBA (zemin saydam).

Koordinatlar: x sağ, y yukarı, z izleyiciye doğru (kamera +z'de, -z'ye bakar).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, List, Optional, Sequence, Tuple

import numpy as np

Vec = Tuple[float, float, float]
SDF = Callable[[np.ndarray], np.ndarray]


# --------------------------------------------------------------------------- dönüşümler

def rot(rx: float = 0.0, ry: float = 0.0, rz: float = 0.0) -> np.ndarray:
    """Euler (derece) → 3x3; uygulama sırası: Rz · Ry · Rx (nesne yerel → dünya)."""
    a, b, c = (math.radians(v) for v in (rx, ry, rz))
    Rx = np.array([[1, 0, 0], [0, math.cos(a), -math.sin(a)], [0, math.sin(a), math.cos(a)]])
    Ry = np.array([[math.cos(b), 0, math.sin(b)], [0, 1, 0], [-math.sin(b), 0, math.cos(b)]])
    Rz = np.array([[math.cos(c), -math.sin(c), 0], [math.sin(c), math.cos(c), 0], [0, 0, 1]])
    return Rz @ Ry @ Rx


def _local(p: np.ndarray, c: Vec, R: Optional[np.ndarray]) -> np.ndarray:
    q = p - np.asarray(c, np.float64)
    return q if R is None else q @ R  # q · R == Rᵀ q (dünya → yerel)


# --------------------------------------------------------------------------- ilkel şekiller

def sphere(c: Vec, r: float) -> SDF:
    cc = np.asarray(c, np.float64)
    return lambda p: np.linalg.norm(p - cc, axis=1) - r


def ellipsoid(c: Vec, radii: Vec, R: Optional[np.ndarray] = None) -> SDF:
    rr = np.asarray(radii, np.float64)

    def f(p: np.ndarray) -> np.ndarray:
        q = _local(p, c, R)
        k0 = np.linalg.norm(q / rr, axis=1)
        k1 = np.linalg.norm(q / (rr * rr), axis=1)
        return k0 * (k0 - 1.0) / np.maximum(k1, 1e-9)

    return f


def capsule(a: Vec, b: Vec, r: float) -> SDF:
    A, B = np.asarray(a, np.float64), np.asarray(b, np.float64)
    ba = B - A
    bb = float(ba @ ba) or 1e-9

    def f(p: np.ndarray) -> np.ndarray:
        pa = p - A
        h = np.clip(pa @ ba / bb, 0.0, 1.0)
        return np.linalg.norm(pa - h[:, None] * ba, axis=1) - r

    return f


def round_cone(a: Vec, b: Vec, r1: float, r2: float) -> SDF:
    """a'da r1, b'de r2 yarıçaplı yuvarlak koni (iq)."""
    A, B = np.asarray(a, np.float64), np.asarray(b, np.float64)
    ba = B - A
    l2 = float(ba @ ba) or 1e-9
    rr = r1 - r2
    a2 = l2 - rr * rr
    il2 = 1.0 / l2

    def f(p: np.ndarray) -> np.ndarray:
        pa = p - A
        y = pa @ ba
        z = y - l2
        x2v = pa * l2 - y[:, None] * ba
        x2 = np.einsum("ij,ij->i", x2v, x2v)
        y2 = y * y * l2
        z2 = z * z * l2
        k = np.sign(rr) * rr * rr * x2
        out = (np.sqrt(x2 * a2 * il2) + y * rr) * il2 - r1
        m1 = np.sign(z) * a2 * z2 > k
        out = np.where(m1, np.sqrt(x2 + z2) * il2 - r2, out)
        m2 = np.sign(y) * a2 * y2 < k
        out = np.where(m2, np.sqrt(x2 + y2) * il2 - r1, out)
        return out

    return f


def round_box(c: Vec, half: Vec, rad: float = 0.0, R: Optional[np.ndarray] = None) -> SDF:
    hh = np.asarray(half, np.float64) - rad

    def f(p: np.ndarray) -> np.ndarray:
        q = np.abs(_local(p, c, R)) - hh
        return np.linalg.norm(np.maximum(q, 0.0), axis=1) + np.minimum(q.max(axis=1), 0.0) - rad

    return f


def torus(c: Vec, R_: float, r: float, R: Optional[np.ndarray] = None) -> SDF:
    def f(p: np.ndarray) -> np.ndarray:
        q = _local(p, c, R)
        qx = np.sqrt(q[:, 0] ** 2 + q[:, 2] ** 2) - R_
        return np.sqrt(qx * qx + q[:, 1] ** 2) - r

    return f


def displace(f: SDF, g: Callable[[np.ndarray], np.ndarray], amount: float) -> SDF:
    return lambda p: f(p) + amount * g(p)


def smin(a: np.ndarray, b: np.ndarray, k: float) -> np.ndarray:
    if k <= 0:
        return np.minimum(a, b)
    h = np.clip(0.5 + 0.5 * (b - a) / k, 0.0, 1.0)
    return b * (1 - h) + a * h - k * h * (1 - h)


# --------------------------------------------------------------------------- gürültü (doku için)

def value_noise(p: np.ndarray, scale: float = 1.0, seed: int = 0) -> np.ndarray:
    q = p * scale
    i = np.floor(q)
    f = q - i
    f = f * f * (3 - 2 * f)

    def h(ix, iy, iz):
        n = (ix * 73856093) ^ (iy * 19349663) ^ (iz * 83492791) ^ (seed * 2654435761)
        n = (n ^ (n >> 13)) * 1274126177
        return ((n & 0xFFFF) / 65535.0)

    ii = i.astype(np.int64)
    x, y, z = ii[:, 0], ii[:, 1], ii[:, 2]
    fx, fy, fz = f[:, 0], f[:, 1], f[:, 2]
    c000, c100, c010, c110 = h(x, y, z), h(x + 1, y, z), h(x, y + 1, z), h(x + 1, y + 1, z)
    c001, c101, c011, c111 = h(x, y, z + 1), h(x + 1, y, z + 1), h(x, y + 1, z + 1), h(x + 1, y + 1, z + 1)
    x00 = c000 + (c100 - c000) * fx
    x10 = c010 + (c110 - c010) * fx
    x01 = c001 + (c101 - c001) * fx
    x11 = c011 + (c111 - c011) * fx
    y0 = x00 + (x10 - x00) * fy
    y1 = x01 + (x11 - x01) * fy
    return y0 + (y1 - y0) * fz


# --------------------------------------------------------------------------- sahne

@dataclass
class Material:
    color: Vec
    spec: float = 0.0
    shine: float = 24.0
    rim: float = 0.35
    emissive: float = 0.0
    glyph: Optional[str] = None  # öznitelik malzemesi: hücreye bu karakter yazılır (göz, burun, bıyık...)
    priority: int = 0  # bir hücrede birden çok öznitelik varsa büyük olan kazanır
    glyph_min: int = 1  # hücrenin 8 alt pikselinden en az kaçı bu malzemeyse karakter yazılır
    outline: bool = True  # malzeme sınırında kontur çizilsin mi
    pattern: Optional[Callable[[np.ndarray, np.ndarray], np.ndarray]] = None  # (p, n) → renk çarpanı (N,) veya (N,3)


@dataclass
class Group:
    items: List[Tuple[SDF, int]] = field(default_factory=list)
    k: float = 0.0
    bound: Optional[Tuple[Vec, float]] = None  # (merkez, yarıçap): uzaktaysa grup değerlendirilmez


class Scene:
    def __init__(self) -> None:
        self.materials: List[Material] = []
        self.groups: List[Group] = []

    def mat(self, color: Vec, **kw) -> int:
        self.materials.append(Material(tuple(c / 255.0 if max(color) > 1.0 else c for c in color), **kw))
        return len(self.materials) - 1

    def group(self, k: float = 0.0, bound: Optional[Tuple[Vec, float]] = None) -> Group:
        g = Group(k=k, bound=bound)
        self.groups.append(g)
        return g

    def eval(self, p: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        best = np.full(p.shape[0], 1e9)
        mat = np.full(p.shape[0], -1, np.int32)
        for g in self.groups:
            if g.bound is not None:
                c, r = g.bound
                bd = np.linalg.norm(p - np.asarray(c, np.float64), axis=1) - r
                sel = np.nonzero(bd < np.minimum(best, 0.5) + 0.05)[0]
                if sel.size == 0:
                    continue
                pp = p[sel]
            else:
                sel = None
                pp = p
            gd = None
            gm = None
            for f, m in g.items:
                d = f(pp)
                if gd is None:
                    gd, gm = d, np.full(d.shape, m, np.int32)
                else:
                    gm = np.where(d < gd, m, gm)
                    gd = smin(gd, d, g.k)
            if gd is None:
                continue
            if sel is None:
                upd = gd < best
                best = np.where(upd, gd, best)
                mat = np.where(upd, gm, mat)
            else:
                sub = best[sel]
                upd = gd < sub
                best[sel] = np.where(upd, gd, sub)
                mat[sel] = np.where(upd, gm, mat[sel])
        return best, mat

    def dist(self, p: np.ndarray) -> np.ndarray:
        return self.eval(p)[0]


@dataclass
class Light:
    dir: Vec = (-0.5, 0.65, 0.55)  # ışığa doğru
    color: Vec = (1.0, 0.95, 0.85)
    sky: Vec = (0.35, 0.42, 0.55)  # yukarıdan dolgu
    rim_color: Vec = (1.0, 0.85, 0.6)
    ambient: float = 0.18
    shadow_k: float = 10.0


def render(
    scene: Scene,
    W: int,
    H: int,
    cam_pos: Vec = (0.0, 0.0, 6.0),
    target: Vec = (0.0, 0.0, 0.0),
    fov_deg: float = 30.0,
    light: Optional[Light] = None,
    steps: int = 96,
    far: float = 30.0,
    shadows: bool = True,
    ao: bool = True,
    buffers: Optional[dict] = None,
) -> np.ndarray:
    """(H, W, 4) float RGBA; ıskalanan pikseller alfa 0."""
    light = light or Light()
    cp = np.asarray(cam_pos, np.float64)
    fwd = np.asarray(target, np.float64) - cp
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0.0, 1.0, 0.0])
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    fl = 1.0 / math.tan(math.radians(fov_deg) / 2.0)
    ys, xs = np.mgrid[0:H, 0:W]
    u = ((xs + 0.5) / W * 2.0 - 1.0) * (W / H)
    v = 1.0 - (ys + 0.5) / H * 2.0
    d = u.reshape(-1, 1) * right + v.reshape(-1, 1) * up + fl * fwd
    d /= np.linalg.norm(d, axis=1, keepdims=True)
    n = d.shape[0]
    t = np.zeros(n)
    hit = np.zeros(n, bool)
    alive = np.arange(n)
    for _ in range(steps):
        if alive.size == 0:
            break
        p = cp + d[alive] * t[alive, None]
        dist = scene.dist(p)
        done = dist < 0.0015 * np.maximum(t[alive], 1.0)
        hit[alive[done]] = True
        t[alive] += dist * 0.92
        alive = alive[~done & (t[alive] < far)]
    out = np.zeros((n, 4))
    hid = np.nonzero(hit)[0]
    if hid.size == 0:
        return out.reshape(H, W, 4)
    P = cp + d[hid] * t[hid, None]
    _, M = scene.eval(P)
    e = 0.0015
    k1, k2, k3, k4 = (np.array(v, np.float64) for v in ((1, -1, -1), (-1, -1, 1), (-1, 1, -1), (1, 1, 1)))
    N = (k1 * scene.dist(P + k1 * e)[:, None] + k2 * scene.dist(P + k2 * e)[:, None]
         + k3 * scene.dist(P + k3 * e)[:, None] + k4 * scene.dist(P + k4 * e)[:, None])
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-9)
    L = np.asarray(light.dir, np.float64)
    L /= np.linalg.norm(L)
    diff = np.clip(N @ L, 0.0, 1.0)
    sh = np.ones(hid.size)
    if shadows:
        st = np.full(hid.size, 0.02)
        idx = np.arange(hid.size)
        for _ in range(28):
            if idx.size == 0:
                break
            q = P[idx] + N[idx] * 0.004 + L * st[idx, None]
            dd = scene.dist(q)
            sh[idx] = np.minimum(sh[idx], light.shadow_k * dd / st[idx])
            st[idx] += np.clip(dd, 0.02, 0.25)
            idx = idx[(dd > 0.0005) & (st[idx] < 6.0)]
        sh = np.clip(sh, 0.0, 1.0)
    occ = np.ones(hid.size)
    if ao:
        acc = np.zeros(hid.size)
        for i in range(1, 6):
            hh = 0.035 * i
            acc += (hh - scene.dist(P + N * hh)) / (2 ** i)
        occ = np.clip(1.0 - 3.0 * acc, 0.0, 1.0)
    albedo = np.zeros((hid.size, 3))
    spec_k = np.zeros(hid.size)
    shine = np.ones(hid.size)
    rim_k = np.zeros(hid.size)
    emis = np.zeros(hid.size)
    for mi, m in enumerate(scene.materials):
        sel = M == mi
        if not sel.any():
            continue
        col = np.broadcast_to(np.asarray(m.color, np.float64), (int(sel.sum()), 3)).copy()
        if m.pattern is not None:
            pat = m.pattern(P[sel], N[sel])
            col = col * (pat[:, None] if pat.ndim == 1 else pat)
        albedo[sel] = col
        spec_k[sel], shine[sel], rim_k[sel], emis[sel] = m.spec, m.shine, m.rim, m.emissive
    V = -d[hid]
    Hh = L + V
    Hh /= np.maximum(np.linalg.norm(Hh, axis=1, keepdims=True), 1e-9)
    spec = spec_k * np.clip(np.einsum("ij,ij->i", N, Hh), 0, 1) ** shine * sh
    fres = (1.0 - np.clip(np.einsum("ij,ij->i", N, V), 0, 1)) ** 3
    skyw = 0.5 + 0.5 * N[:, 1]
    lit = (albedo * (np.asarray(light.color) * (diff * sh)[:, None] + np.asarray(light.sky) * (skyw * occ)[:, None]
                     + light.ambient * occ[:, None])
           + spec[:, None] * np.asarray(light.color)
           + (rim_k * fres * (0.4 + 0.6 * occ))[:, None] * np.asarray(light.rim_color)
           + albedo * emis[:, None])
    out[hid, :3] = np.clip(lit, 0.0, 1.0)
    out[hid, 3] = 1.0
    if buffers is not None:  # kontur/öznitelik katmanı için malzeme kimliği, derinlik ve normal tamponları
        mat_buf = np.full(n, -1, np.int32)
        mat_buf[hid] = M
        depth = np.full(n, np.inf)
        depth[hid] = t[hid]
        nbuf = np.zeros((n, 3))
        nbuf[hid] = N
        buffers["mat"] = mat_buf.reshape(H, W)
        buffers["depth"] = depth.reshape(H, W)
        buffers["normal"] = nbuf.reshape(H, W, 3)
    return out.reshape(H, W, 4)
