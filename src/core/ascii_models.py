"""Sabit hatlı 3B ASCII model motoru: elipsoit birleşimleri, analitik ışın-kesişimi, kontur + öznitelik katmanı.

Eski "nokta serpme" (splat) yaklaşımı yerine her hücre için gerçek elipsoit yüzeyi çözülür:
  * dolu, boşluksuz gövde (silüet net),
  * derinlik/komşuluk farkından kontur karakterleri  / \\ | _ ( ) -
  * göz, burun, ağız, bıyık gibi öznitelikler modele bağlı sabit noktalara/primitiflere yazılır (yöne göre döner),
  * gövde 4 kademeli (. : + #) sade gölgelendirme ile doldurulur.

Koordinat sistemi: x sağ, y YUKARI, z izleyiciye doğru (büyük z = yakın). Birim ~ model yarıçapı.
Hepsi saf klasik ASCII (0x20..0x7E) üretir.
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.core.procedural_engine import BaseProceduralRenderer, ProceduralFrame

RGB = Tuple[int, int, int]
Vec = Tuple[float, float, float]
Mat = Tuple[Vec, Vec, Vec]

SHADE_CHARS = ".:+#"
EMPTY = -1e9


# --------------------------------------------------------------------------- matematik

def rot_x(a: float) -> Mat:
    c, s = math.cos(a), math.sin(a)
    return ((1, 0, 0), (0, c, -s), (0, s, c))


def rot_y(a: float) -> Mat:
    c, s = math.cos(a), math.sin(a)
    return ((c, 0, s), (0, 1, 0), (-s, 0, c))


def rot_z(a: float) -> Mat:
    c, s = math.cos(a), math.sin(a)
    return ((c, -s, 0), (s, c, 0), (0, 0, 1))


def mmul(a: Mat, b: Mat) -> Mat:
    return tuple(  # type: ignore[return-value]
        tuple(a[i][0] * b[0][j] + a[i][1] * b[1][j] + a[i][2] * b[2][j] for j in range(3)) for i in range(3)
    )


def mT(a: Mat) -> Mat:
    return ((a[0][0], a[1][0], a[2][0]), (a[0][1], a[1][1], a[2][1]), (a[0][2], a[1][2], a[2][2]))


def mv(a: Mat, v: Vec) -> Vec:
    return (
        a[0][0] * v[0] + a[0][1] * v[1] + a[0][2] * v[2],
        a[1][0] * v[0] + a[1][1] * v[1] + a[1][2] * v[2],
        a[2][0] * v[0] + a[2][1] * v[1] + a[2][2] * v[2],
    )


IDENT: Mat = ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))


def euler(rx: float = 0.0, ry: float = 0.0, rz: float = 0.0) -> Mat:
    return mmul(rot_z(rz), mmul(rot_y(ry), rot_x(rx)))


def _mix(a: RGB, b: RGB, k: float) -> RGB:
    return (int(a[0] + (b[0] - a[0]) * k), int(a[1] + (b[1] - a[1]) * k), int(a[2] + (b[2] - a[2]) * k))


def _scale(c: RGB, k: float) -> RGB:
    return (max(0, min(255, int(c[0] * k))), max(0, min(255, int(c[1] * k))), max(0, min(255, int(c[2] * k))))


# --------------------------------------------------------------------------- sahne öğeleri

class Ell:
    """Elipsoit primitifi. `chars` verilirse gölgeleme yerine yüzün baktığı yöne göre öznitelik karakteri yazar:
    chars = (kenar, orta, merkez) → n_z < 0.55 kenar, < 0.85 orta, aksi merkez karakteri."""

    __slots__ = ("c", "r", "rot", "color", "group", "chars", "S", "M", "flat", "outline", "visible")

    def __init__(
        self,
        c: Vec,
        r: Vec,
        color: RGB,
        rot: Vec = (0.0, 0.0, 0.0),
        group: int = 0,
        chars: Optional[Tuple[str, str, str]] = None,
        flat: bool = False,
        outline: bool = True,
    ) -> None:
        self.c = c
        self.r = r
        self.rot = rot
        self.color = color
        self.group = group
        self.chars = chars
        self.flat = flat  # True: gölgeleme yok, düz renk
        self.outline = outline
        self.visible = True
        self.S: Mat = IDENT
        self.M: Mat = IDENT
        self.update()

    def update(self) -> None:
        """c/r/rot değiştikten sonra çağır (S = R diag(r²) Rᵀ, M = R diag(1/r²) Rᵀ)."""
        R = euler(*self.rot)
        rx, ry, rz = (max(1e-4, abs(v)) for v in self.r)
        D2 = ((rx * rx, 0.0, 0.0), (0.0, ry * ry, 0.0), (0.0, 0.0, rz * rz))
        Di = ((1.0 / (rx * rx), 0.0, 0.0), (0.0, 1.0 / (ry * ry), 0.0), (0.0, 0.0, 1.0 / (rz * rz)))
        Rt = mT(R)
        self.S = mmul(R, mmul(D2, Rt))
        self.M = mmul(R, mmul(Di, Rt))


class Marker:
    """Modele bağlı tek karakter (yüzey önündeyse görünür). Dinamik: .char değiştirilebilir."""

    __slots__ = ("p", "char", "color", "group", "visible")

    def __init__(self, p: Vec, char: str, color: RGB, group: int = 0) -> None:
        self.p, self.char, self.color, self.group, self.visible = p, char, color, group, True


class Stroke:
    """Modele bağlı çizgi parçası (bıyık, kılıç, ip...). char=None → eğime göre - | / \\ seçilir."""

    __slots__ = ("a", "b", "char", "color", "group", "visible")

    def __init__(self, a: Vec, b: Vec, color: RGB, char: Optional[str] = None, group: int = 0) -> None:
        self.a, self.b, self.char, self.color, self.group, self.visible = a, b, char, color, group, True


# --------------------------------------------------------------------------- motor

class ModelRenderer(BaseProceduralRenderer):
    """Alt sınıflar `build()` içinde self.prims / self.markers / self.strokes doldurur, `pose(t)` ile canlandırır."""

    extent: Tuple[float, float] = (1.0, 1.0)  # model yarı genişlik / yarı yükseklik (kamera sığdırma)
    center: Tuple[float, float] = (0.0, 0.0)
    sway: float = 0.35  # kendiliğinden yaw salınımı (rad)
    sway_speed: float = 0.8
    base_pitch: float = 0.06
    light: Vec = (-0.45, 0.62, 0.65)

    def __init__(self, width: int = 52, height: int = 24, params: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(width, height, params)
        self.prims: List[Ell] = []
        self.markers: List[Marker] = []
        self.strokes: List[Stroke] = []
        self.groups: Dict[int, Tuple[Vec, Mat]] = {}
        n = math.sqrt(sum(v * v for v in self.light))
        self.L = tuple(v / n for v in self.light)
        self.build()
        self.pose(0.0)

    # --- alt sınıf kancaları
    def build(self) -> None:
        raise NotImplementedError

    def pose(self, t: float) -> None:
        """Animasyon: group dönüşleri (set_group), prim/marker parametreleri, göz kırpma vb."""

    def set_group(self, gid: int, pivot: Vec, rx: float = 0.0, ry: float = 0.0, rz: float = 0.0) -> None:
        self.groups[gid] = (pivot, euler(rx, ry, rz))

    # --- yardımcılar
    def add(self, *args: Any, **kw: Any) -> Ell:
        e = Ell(*args, **kw)
        self.prims.append(e)
        return e

    def mark(self, *args: Any, **kw: Any) -> Marker:
        m = Marker(*args, **kw)
        self.markers.append(m)
        return m

    def stroke(self, *args: Any, **kw: Any) -> Stroke:
        s = Stroke(*args, **kw)
        self.strokes.append(s)
        return s

    def _gt(self, gid: int) -> Tuple[Vec, Mat]:
        return self.groups.get(gid, ((0.0, 0.0, 0.0), IDENT))

    def _tx_point(self, p: Vec, gid: int, V: Mat) -> Vec:
        piv, G = self._gt(gid)
        q = mv(G, (p[0] - piv[0], p[1] - piv[1], p[2] - piv[2]))
        return mv(V, (q[0] + piv[0], q[1] + piv[1], q[2] + piv[2]))

    # --- çizim
    def render_at(self, t: float) -> ProceduralFrame:
        self.pose(t)
        W, H = self.width, self.height
        yaw = math.sin(t * self.sway_speed) * self.sway + self.yaw_offset + self.cursor_look[0] * 0.5
        pitch = self.base_pitch + self.pitch_offset + self.cursor_look[1] * 0.28
        V = mmul(rot_x(pitch), rot_y(yaw))
        Vt = mT(V)

        ew, eh = self.extent
        sx = max(ew / (0.47 * W), eh / (0.94 * H))  # hücre genişliği (dünya birimi)
        sy = sx * 2.0  # hücre yüksekliği (≈ 2× genişlik)
        cwx, cwy = self.center
        # merkezi dünyaya yerleştir: ekran merkezi = model merkezi (görünüm uzayında)
        vcx, vcy, _ = mv(V, (cwx, cwy, 0.0))
        half_w, half_h = W / 2.0, H / 2.0

        zbuf = [[EMPTY] * W for _ in range(H)]
        pid = [[-1] * W for _ in range(H)]
        info: List[Optional[Tuple[Vec, Mat]]] = []

        for idx, e in enumerate(self.prims):
            if not e.visible:
                info.append(None)
                continue
            piv, G = self._gt(e.group)
            cc = mv(G, (e.c[0] - piv[0], e.c[1] - piv[1], e.c[2] - piv[2]))
            cv = mv(V, (cc[0] + piv[0], cc[1] + piv[1], cc[2] + piv[2]))
            Q = mmul(V, G)
            Qt = mT(Q)
            Mv = mmul(Q, mmul(e.M, Qt))
            Sv = mmul(Q, mmul(e.S, Qt))
            info.append((cv, Mv))

            hy = math.sqrt(max(Sv[1][1], 1e-12))
            j0 = max(0, int(math.floor(half_h - (cv[1] - vcy + hy) / sy)))
            j1 = min(H - 1, int(math.ceil(half_h - (cv[1] - vcy - hy) / sy)))
            a = Mv[2][2]
            inv2a = 0.5 / a
            Mxx, Mxy, Mxz, Myy, Myz = Mv[0][0], Mv[0][1], Mv[0][2], Mv[1][1], Mv[1][2]
            cvx, cvy, cvz = cv[0] - vcx, cv[1] - vcy, cv[2]
            B1 = 2.0 * Mxz
            for j in range(j0, j1 + 1):
                dy = (half_h - (j + 0.5)) * sy - cvy
                B0 = 2.0 * Myz * dy
                C1 = 2.0 * Mxy * dy
                C0 = Myy * dy * dy - 1.0
                A2 = B1 * B1 - 4.0 * a * Mxx
                A1 = 2.0 * B1 * B0 - 4.0 * a * C1
                A0 = B0 * B0 - 4.0 * a * C0
                if A2 >= -1e-12:
                    continue
                Dd = A1 * A1 - 4.0 * A2 * A0
                if Dd <= 0.0:
                    continue
                sq = math.sqrt(Dd)
                r1 = (-A1 + sq) / (2.0 * A2)
                r2 = (-A1 - sq) / (2.0 * A2)
                lo, hi = (r1, r2) if r1 < r2 else (r2, r1)
                i0 = max(0, int(math.ceil((cvx + lo) / sx + half_w - 0.5)))
                i1 = min(W - 1, int(math.floor((cvx + hi) / sx + half_w - 0.5)))
                zrow = zbuf[j]
                prow = pid[j]
                for i in range(i0, i1 + 1):
                    dx = (i + 0.5 - half_w) * sx - cvx
                    d = (A2 * dx + A1) * dx + A0
                    if d < 0.0:
                        d = 0.0
                    z = cvz + (-(B1 * dx + B0) + math.sqrt(d)) * inv2a
                    if z > zrow[i]:
                        zrow[i] = z
                        prow[i] = idx

        # --- ikinci geçiş: gölgeleme / öznitelik karakteri
        buf = [[" "] * W for _ in range(H)]
        cbuf: List[List[Optional[RGB]]] = [[None] * W for _ in range(H)]
        nzbuf = [[0.0] * W for _ in range(H)]
        Lx, Ly, Lz = self.L
        for j in range(H):
            prow = pid[j]
            zrow = zbuf[j]
            y_w = (half_h - (j + 0.5)) * sy
            for i in range(W):
                p = prow[i]
                if p < 0:
                    continue
                e = self.prims[p]
                cv, Mv = info[p]  # type: ignore[misc]
                dx = (i + 0.5 - half_w) * sx - (cv[0] - vcx)
                dy = y_w - (cv[1] - vcy)
                dz = zrow[i] - cv[2]
                nx = Mv[0][0] * dx + Mv[0][1] * dy + Mv[0][2] * dz
                ny = Mv[1][0] * dx + Mv[1][1] * dy + Mv[1][2] * dz
                nz = Mv[2][0] * dx + Mv[2][1] * dy + Mv[2][2] * dz
                ln = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                nx, ny, nz = nx / ln, ny / ln, nz / ln
                nzbuf[j][i] = nz
                diff = nx * Lx + ny * Ly + nz * Lz
                inten = 0.30 + 0.70 * (diff if diff > 0.0 else 0.0)
                if e.chars is not None:
                    buf[j][i] = e.chars[0] if nz < 0.55 else (e.chars[1] if nz < 0.85 else e.chars[2])
                    cbuf[j][i] = e.color if e.flat else _scale(e.color, 0.55 + 0.45 * inten)
                elif e.flat:
                    buf[j][i] = SHADE_CHARS[2]
                    cbuf[j][i] = e.color
                else:
                    lvl = 0 if inten < 0.42 else (1 if inten < 0.62 else (2 if inten < 0.82 else 3))
                    buf[j][i] = SHADE_CHARS[lvl]
                    cbuf[j][i] = _scale(e.color, 0.45 + 0.75 * inten)

        # --- konturlar: boşluğa bakan kenarlar + belirgin derinlik basamağı
        edge_cells: List[Tuple[int, int, str, RGB]] = []
        for j in range(H):
            prow = pid[j]
            for i in range(W):
                p = prow[i]
                if p < 0 or not self.prims[p].outline:
                    continue
                up = j == 0 or pid[j - 1][i] < 0
                dn = j == H - 1 or pid[j + 1][i] < 0
                lf = i == 0 or prow[i - 1] < 0
                rt = i == W - 1 or prow[i + 1] < 0
                z0 = zbuf[j][i]
                if not (up or dn or lf or rt):
                    # iç kontur: komşu belirgin biçimde daha yakınsa bu hücre "arkada kalan kenar"
                    thr = 0.20
                    up = pid[j - 1][i] >= 0 and zbuf[j - 1][i] - z0 > thr and pid[j - 1][i] != p
                    dn = pid[j + 1][i] >= 0 and zbuf[j + 1][i] - z0 > thr and pid[j + 1][i] != p
                    lf = prow[i - 1] >= 0 and zrow_get(zbuf, j, i - 1) - z0 > thr and prow[i - 1] != p
                    rt = prow[i + 1] >= 0 and zrow_get(zbuf, j, i + 1) - z0 > thr and prow[i + 1] != p
                    if not (up or dn or lf or rt):
                        continue
                    inner = True
                else:
                    inner = False
                ch = _edge_char(up, dn, lf, rt)
                base = self.prims[p].color
                col = _mix(base, (255, 255, 255), 0.30) if not inner else _scale(base, 0.62)
                edge_cells.append((j, i, ch, col))
        for j, i, ch, col in edge_cells:
            if self.prims[pid[j][i]].chars is None:
                buf[j][i] = ch
                cbuf[j][i] = col

        # --- işaretçiler ve çizgiler (derinlik testli)
        def proj(p: Vec, gid: int) -> Tuple[int, int, float]:
            q = self._tx_point(p, gid, V)
            return (
                int(math.floor(half_w + (q[0] - vcx) / sx)),
                int(math.floor(half_h - (q[1] - vcy) / sy)),
                q[2],
            )

        for s in self.strokes:
            if not s.visible:
                continue
            i0, j0_, z0_ = proj(s.a, s.group)
            i1, j1_, z1_ = proj(s.b, s.group)
            n = max(abs(i1 - i0), abs(j1_ - j0_), 1)
            if s.char is None:
                di, dj = i1 - i0, j1_ - j0_
                slope = (dj * 2.0) / di if di else 99.0
                ch = "-" if abs(slope) < 0.55 else ("|" if abs(slope) > 2.6 else ("\\" if slope > 0 else "/"))
            else:
                ch = s.char
            for k in range(n + 1):
                u = k / n
                ii = int(round(i0 + (i1 - i0) * u))
                jj = int(round(j0_ + (j1_ - j0_) * u))
                zz = z0_ + (z1_ - z0_) * u
                if 0 <= ii < W and 0 <= jj < H and zz >= zbuf[jj][ii] - 0.06:
                    buf[jj][ii] = ch
                    cbuf[jj][ii] = s.color
        for m in self.markers:
            if not m.visible:
                continue
            ii, jj, zz = proj(m.p, m.group)
            if 0 <= ii < W and 0 <= jj < H and zz >= zbuf[jj][ii] - 0.08:
                buf[jj][ii] = m.char
                cbuf[jj][ii] = m.color

        return ProceduralFrame(lines=["".join(r) for r in buf], colors=cbuf)


def zrow_get(zbuf: List[List[float]], j: int, i: int) -> float:
    return zbuf[j][i]


def _edge_char(up: bool, dn: bool, lf: bool, rt: bool) -> str:
    if up and lf and not (dn or rt):
        return "/"
    if up and rt and not (dn or lf):
        return "\\"
    if dn and lf and not (up or rt):
        return "\\"
    if dn and rt and not (up or lf):
        return "/"
    if up and dn:
        return "-"
    if lf and rt:
        return "|"
    if lf:
        return "("
    if rt:
        return ")"
    if up:
        return "_" if False else "-"
    if dn:
        return "-"
    return "."


# --------------------------------------------------------------------------- modeller (kayıt: MODEL_REGISTRY)

MODEL_REGISTRY: Dict[str, Tuple[type, int, int]] = {}


def register(model_id: str, width: int, height: int):
    def deco(cls):
        MODEL_REGISTRY[model_id] = (cls, width, height)
        return cls

    return deco
