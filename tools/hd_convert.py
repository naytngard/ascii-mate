"""HD dönüştürücü: görüntü / GIF / kare klasörü / OBJ → ASCII Mate HD (schema 3.0) varlığı.

Örnekler:
    python tools/hd_convert.py foto.png --out assets/animations/community --id portre --name "Portre" --cols 180
    python tools/hd_convert.py anim.gif --out assets/animations/community --id anim --cols 160 --fps 10
    python tools/hd_convert.py kareler/ --out ... --id seri --frames 48
    python tools/hd_convert.py model.obj --out ... --id donen_model --frames 48 --rotate-y 360 --cols 150

Karakterler yalnızca ASCII'dir. Yoğunluk rampası, widget'ın kullandığı yazı tipiyle ölçülen GERÇEK mürekkep yoğunluğuna göre
sıralanır (hücre atlası üzerinden). Kenarlar Sobel ile bulunur ve | - / \\ karakterleriyle vurgulanır (--edge-boost).
Bağımlılıklar: PyQt6 (görüntü okuma + yazı ölçümü) ve NumPy.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path
from typing import List, Optional, Sequence, Tuple

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import numpy as np  # noqa: E402
from PyQt6.QtCore import Qt  # noqa: E402
from PyQt6.QtGui import QGuiApplication, QImage, QImageReader  # noqa: E402

from src.core.hd_format import write_hd  # noqa: E402
from src.gui.hd_renderer import build_atlas  # noqa: E402

IMG_EXT = {".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tga", ".tif", ".tiff"}
_APP: Optional[QGuiApplication] = None


def ensure_qt() -> None:
    global _APP
    if QGuiApplication.instance() is None:
        _APP = QGuiApplication(sys.argv[:1])


# --------------------------------------------------------------------------- ramp (gerçek mürekkep yoğunluğu)

def measure_ink() -> dict[str, float]:
    """33..126 ASCII karakterlerinin 8×16 hücrede ölçülen ortalama mürekkep yoğunluğu (0..1)."""
    ensure_qt()
    atlas = build_atlas(8, 16)
    return {chr(code): float(atlas[code - 32].mean()) / 255.0 for code in range(33, 127)}


def build_ramp(spec: str = "auto", levels: int = 22) -> List[Tuple[str, float]]:
    """[(char, ink)] — mürekkebe göre artan, boşluk (0.0) başta. 'auto': tüm ASCII'den eşit aralıklı seviyeler."""
    ink = measure_ink()
    if spec != "auto":
        chars = [c for c in dict.fromkeys(spec) if c != " " and c in ink]
        if not chars:
            raise SystemExit("--ramp geçerli ASCII karakter içermiyor")
        pairs = sorted(((c, ink[c]) for c in chars), key=lambda x: x[1])
    else:
        top = max(ink.values())
        pairs = []
        used = set()
        for k in range(1, levels + 1):
            target = top * k / levels
            best = min((c for c in ink if c not in used), key=lambda c: abs(ink[c] - target))
            used.add(best)
            pairs.append((best, ink[best]))
        pairs.sort(key=lambda x: x[1])
    return [(" ", 0.0)] + pairs


# --------------------------------------------------------------------------- görüntü → hücre ızgarası

def qimage_to_rgba(img: QImage) -> np.ndarray:
    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    arr = np.frombuffer(ptr, np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)[:, : img.width(), :]
    return arr.astype(np.float32) / 255.0  # straight alpha


def resize_rgba(arr: np.ndarray, w: int, h: int) -> np.ndarray:
    """Qt'nin alan-ortalamalı (smooth) küçültmesi; premultiplied üzerinden (kenar halesi olmasın)."""
    pm = arr.copy()
    pm[..., :3] *= pm[..., 3:4]
    u8 = np.ascontiguousarray((pm * 255.0 + 0.5).astype(np.uint8))
    img = QImage(u8.data, arr.shape[1], arr.shape[0], arr.shape[1] * 4, QImage.Format.Format_RGBA8888_Premultiplied)
    out = img.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    out = out.convertToFormat(QImage.Format.Format_RGBA8888_Premultiplied)
    p2 = out.constBits()
    p2.setsize(out.sizeInBytes())
    a = np.frombuffer(p2, np.uint8).reshape(h, out.bytesPerLine() // 4, 4)[:, :w, :].astype(np.float32) / 255.0
    alpha = a[..., 3:4]
    rgb = np.where(alpha > 1e-4, a[..., :3] / np.maximum(alpha, 1e-4), 0.0)
    return np.concatenate([np.clip(rgb, 0, 1), alpha], axis=-1)


def grid_rows(img_w: int, img_h: int, cols: int) -> int:
    """Hücre en-boy oranı 1:2 olduğundan satır = cols * (h/w) / 2."""
    return max(1, int(round(cols * (img_h / img_w) / 2.0)))


def convert_rgba(
    arr: np.ndarray,
    cols: int,
    rows: int,
    ramp: Sequence[Tuple[str, float]],
    gamma: float = 1.0,
    edge_boost: float = 1.0,
    bg_threshold: float = 0.06,
    color_bits: int = 5,
    color_lift: float = 0.5,
) -> Tuple[np.ndarray, np.ndarray]:
    """RGBA (H,W,4 float) → (chars (rows,cols) uint8, colors (rows,cols,3) uint8)."""
    big = resize_rgba(arr, cols * 2, rows * 2)  # kenar/ton için 2× örnekleme
    rgb2, a2 = big[..., :3], big[..., 3]
    lum2 = 0.2126 * rgb2[..., 0] + 0.7152 * rgb2[..., 1] + 0.0722 * rgb2[..., 2]

    def pool(x: np.ndarray) -> np.ndarray:
        return x.reshape(rows, 2, cols, 2, *x.shape[2:]).mean(axis=(1, 3))

    alpha = pool(a2)
    w = a2[..., None]
    rgb = pool(rgb2 * w) / np.maximum(pool(w), 1e-4)
    lum = pool(lum2 * a2) / np.maximum(alpha, 1e-4)
    tone = np.clip(lum, 0, 1) ** (1.0 / max(gamma, 1e-3))

    inks = np.array([r[1] for r in ramp], np.float32)
    inks = inks / max(inks.max(), 1e-6)
    ramp_chars = np.array([ord(r[0]) for r in ramp], np.uint8)
    idx = np.clip(np.round(tone * (len(ramp) - 1)).astype(int), 0, len(ramp) - 1)
    chars = ramp_chars[idx]

    # kenarlar (Sobel, 2× ızgarada) → | - / \
    if edge_boost > 0:
        p = np.pad(lum2 * a2, 1, mode="edge")
        gx = (p[:-2, 2:] + 2 * p[1:-1, 2:] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[1:-1, :-2] + p[2:, :-2])
        gy = (p[2:, :-2] + 2 * p[2:, 1:-1] + p[2:, 2:]) - (p[:-2, :-2] + 2 * p[:-2, 1:-1] + p[:-2, 2:])
        mag = pool(np.hypot(gx, gy)) / 4.0
        gxm, gym = pool(gx), pool(gy)
        theta = np.degrees(np.arctan2(gym, gxm)) % 180.0  # 0=yatay gradyan → dikey kenar
        edge_char = np.full((rows, cols), ord("|"), np.uint8)
        # görüntü koordinatları (y aşağı): gradyan (1,1) → kenar sağ-yukarı '/', gradyan (-1,1) → kenar sağ-aşağı '\\'
        edge_char[(theta >= 22.5) & (theta < 67.5)] = ord("/")
        edge_char[(theta >= 67.5) & (theta < 112.5)] = ord("-")
        edge_char[(theta >= 112.5) & (theta < 157.5)] = ord("\\")
        thr = 0.16 / edge_boost
        chars = np.where(mag > thr, edge_char, chars)

    # arka plan: düşük alfa veya çok koyu hücre → boşluk (saydam)
    bg = (alpha < 0.35) | (lum < bg_threshold)
    chars = np.where(bg, 32, chars).astype(np.uint8)

    col = np.clip(rgb ** 0.9 * 1.12, 0, 1)
    if color_lift > 0:  # koyu bölgelerde (saç, gölge) renk tonunu koru ama okunur parlaklığa çek; yoğunluğu karakter belirler
        mx = np.maximum(col.max(axis=-1, keepdims=True), 0.25)
        col = np.clip(col * (1 - color_lift) + (col / mx) * 0.85 * color_lift, 0, 1)
    colors = (col * 255.0 + 0.5).astype(np.uint8)
    if color_bits < 8:
        sh = 8 - color_bits
        colors = ((colors >> sh) << sh) | (1 << (sh - 1))
    colors = np.where(bg[..., None], 0, colors).astype(np.uint8)
    return chars, colors


# --------------------------------------------------------------------------- girdiler

def load_frames(path: Path, max_frames: Optional[int]) -> List[np.ndarray]:
    ensure_qt()
    frames: List[np.ndarray] = []
    if path.is_dir():
        files = sorted(p for p in path.iterdir() if p.suffix.lower() in IMG_EXT)
        for f in files[: max_frames or None]:
            img = QImage(str(f))
            if not img.isNull():
                frames.append(qimage_to_rgba(img))
    elif path.suffix.lower() == ".gif":
        rd = QImageReader(str(path))
        while True:
            img = rd.read()
            if img.isNull():
                break
            frames.append(qimage_to_rgba(img))
            if max_frames and len(frames) >= max_frames:
                break
    else:
        img = QImage(str(path))
        if img.isNull():
            raise SystemExit(f"Görüntü okunamadı: {path}")
        frames.append(qimage_to_rgba(img))
    if not frames:
        raise SystemExit("Hiç kare okunamadı")
    return frames


# --------------------------------------------------------------------------- OBJ döndürücü (z-buffer)

def parse_obj(path: Path) -> Tuple[np.ndarray, np.ndarray, Optional[np.ndarray]]:
    verts, cols, faces = [], [], []
    for ln in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        parts = ln.split()
        if not parts:
            continue
        if parts[0] == "v" and len(parts) >= 4:
            verts.append([float(x) for x in parts[1:4]])
            if len(parts) >= 7:
                cols.append([float(x) for x in parts[4:7]])
        elif parts[0] == "f" and len(parts) >= 4:
            idx = [int(tok.split("/")[0]) for tok in parts[1:]]
            idx = [i - 1 if i > 0 else len(verts) + i for i in idx]
            for k in range(1, len(idx) - 1):
                faces.append([idx[0], idx[k], idx[k + 1]])
    if not verts or not faces:
        raise SystemExit("OBJ'de köşe/yüz bulunamadı")
    v = np.array(verts, np.float32)
    c = np.array(cols, np.float32) if len(cols) == len(verts) else None
    return v, np.array(faces, np.int32), c


def vertex_normals(v: np.ndarray, f: np.ndarray) -> np.ndarray:
    n = np.zeros_like(v)
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    for k in range(3):
        np.add.at(n, f[:, k], fn)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    return n / np.maximum(ln, 1e-9)


def rot_y(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, 0, s], [0, 1, 0], [-s, 0, c]], np.float32)


def rot_x(a: float) -> np.ndarray:
    c, s = math.cos(a), math.sin(a)
    return np.array([[1, 0, 0], [0, c, -s], [0, s, c]], np.float32)


def render_mesh(
    v: np.ndarray, f: np.ndarray, vcol: Optional[np.ndarray], n: np.ndarray, angle: float, tilt: float,
    W: int, H: int, base: Tuple[float, float, float],
) -> np.ndarray:
    """Ortografik, Lambert + hafif speküler + kenar ışığı; z-buffer; saydam zemin. RGBA float döner."""
    R = rot_x(tilt) @ rot_y(angle)
    pv = v @ R.T
    pn = n @ R.T
    ext = float(np.abs(pv[:, :2]).max()) or 1.0
    scale = 0.46 * min(W, H) / ext
    sx = pv[:, 0] * scale + W / 2.0
    sy = -pv[:, 1] * scale + H / 2.0
    sz = pv[:, 2]
    L = np.array([-0.45, 0.6, 0.65], np.float32)
    L /= np.linalg.norm(L)
    zbuf = np.full((H, W), -1e9, np.float32)
    img = np.zeros((H, W, 4), np.float32)
    for tri in f:
        a, b, c = tri
        # arka yüz eleme (ekran-uzayı yönü)
        ax, ay, bx, by, cx, cy = sx[a], sy[a], sx[b], sy[b], sx[c], sy[c]
        area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if area >= 0:
            continue
        x0, x1 = int(max(0, math.floor(min(ax, bx, cx)))), int(min(W - 1, math.ceil(max(ax, bx, cx))))
        y0, y1 = int(max(0, math.floor(min(ay, by, cy)))), int(min(H - 1, math.ceil(max(ay, by, cy))))
        if x1 < x0 or y1 < y0:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        w0 = ((bx - xs) * (cy - ys) - (cx - xs) * (by - ys)) / area
        w1 = ((cx - xs) * (ay - ys) - (ax - xs) * (cy - ys)) / area
        w2 = 1.0 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        z = w0 * sz[a] + w1 * sz[b] + w2 * sz[c]
        sub = zbuf[y0 : y1 + 1, x0 : x1 + 1]
        upd = inside & (z > sub)
        if not upd.any():
            continue
        nn = w0[..., None] * pn[a] + w1[..., None] * pn[b] + w2[..., None] * pn[c]
        nn /= np.maximum(np.linalg.norm(nn, axis=-1, keepdims=True), 1e-9)
        diff = np.clip(nn @ L, 0, 1)
        spec = np.clip(nn[..., 2], 0, 1) ** 24 * 0.35  # bakışa dönük parlama
        rim = (1.0 - np.clip(nn[..., 2], 0, 1)) ** 3 * 0.35
        if vcol is not None:
            bc = w0[..., None] * vcol[a] + w1[..., None] * vcol[b] + w2[..., None] * vcol[c]
        else:
            bc = np.broadcast_to(np.array(base, np.float32), nn.shape)
        shade = (0.22 + 0.78 * diff + rim)[..., None]
        rgb = np.clip(bc * shade + spec[..., None], 0, 1)
        patch = img[y0 : y1 + 1, x0 : x1 + 1]
        patch[upd, :3] = rgb[upd]
        patch[upd, 3] = 1.0
        sub[upd] = z[upd]
    return img


# --------------------------------------------------------------------------- çıktı

def write_asset(
    out_dir: Path, asset_id: str, name: str, category: str, chars: List[np.ndarray], colors: List[np.ndarray],
    fps: float, bg_mode: str = "transparent", tags: Optional[List[str]] = None, author: str = "ASCII Mate",
    description: str = "",
) -> Tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    hd_path = out_dir / f"{asset_id}.ascii.hd"
    write_hd(hd_path, chars, colors)
    rows, cols = chars[0].shape
    meta = {
        "schema_version": "3.0", "hd": True, "id": asset_id, "name": name, "category": category, "author": author,
        "tags": (tags or []) + ["hd"], "default_fps": float(fps), "recommended_color": "auto_hd",
        "hd_file": hd_path.name, "cols": int(cols), "rows": int(rows), "frame_count": len(chars), "bg_mode": bg_mode,
        "frames": [],
    }
    if description:
        meta["description"] = description
    json_path = out_dir / f"{asset_id}.ascii.json"
    json_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return json_path, hd_path


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("input", help="PNG/JPG, GIF, kare klasörü veya .obj")
    ap.add_argument("--out", required=True, help="çıktı klasörü")
    ap.add_argument("--id", required=True)
    ap.add_argument("--name", default=None)
    ap.add_argument("--category", default="Topluluk / Özel Eklenenler")
    ap.add_argument("--cols", type=int, default=160)
    ap.add_argument("--ramp", default="auto", help="'auto' ya da kullanılacak karakterler")
    ap.add_argument("--gamma", type=float, default=1.0, help=">1 gölgeleri açar")
    ap.add_argument("--edge-boost", type=float, default=1.0, help="0 = kenar karakteri yok")
    ap.add_argument("--bg-threshold", type=float, default=0.06, help="bu parlaklığın altı saydam (boşluk)")
    ap.add_argument("--color-lift", type=float, default=0.5, help="koyu renkleri okunur parlaklığa çeker (0..1)")
    ap.add_argument("--fps", type=float, default=10.0)
    ap.add_argument("--frames", type=int, default=None, help="en çok kare (OBJ'de üretilecek kare sayısı)")
    ap.add_argument("--aspect", type=float, default=1.0, help="OBJ tuvali en/boy")
    ap.add_argument("--rotate-y", type=float, default=360.0, help="OBJ: toplam Y dönüşü (derece)")
    ap.add_argument("--tilt", type=float, default=15.0, help="OBJ: X eğimi (derece)")
    ap.add_argument("--obj-color", default="#d8b45a")
    ap.add_argument("--bg-mode", choices=("transparent", "solid"), default="transparent")
    args = ap.parse_args(argv)

    src = Path(args.input)
    ramp = build_ramp(args.ramp)
    frames_rgba: List[np.ndarray] = []
    if src.suffix.lower() == ".obj":
        ensure_qt()
        v, f, vc = parse_obj(src)
        n = vertex_normals(v, f)
        rows = max(1, int(round(args.cols / args.aspect / 2.0)))
        W, H = args.cols * 4, rows * 8
        h = args.obj_color.lstrip("#")
        base = tuple(int(h[i : i + 2], 16) / 255.0 for i in (0, 2, 4))
        nfr = args.frames or 48
        for k in range(nfr):
            ang = math.radians(args.rotate_y) * k / nfr
            frames_rgba.append(render_mesh(v, f, vc, n, ang, math.radians(args.tilt), W, H, base))  # type: ignore[arg-type]
    else:
        frames_rgba = load_frames(src, args.frames)

    h0, w0 = frames_rgba[0].shape[:2]
    rows = grid_rows(w0, h0, args.cols)
    chars, colors = [], []
    for arr in frames_rgba:
        c, k = convert_rgba(arr, args.cols, rows, ramp, args.gamma, args.edge_boost, args.bg_threshold, color_lift=args.color_lift)
        chars.append(c)
        colors.append(k)
    jp, hp = write_asset(Path(args.out), args.id, args.name or args.id, args.category, chars, colors, args.fps, args.bg_mode)
    print(f"[OK] {jp}  +  {hp}  ({args.cols}x{rows}, {len(chars)} kare, {hp.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
