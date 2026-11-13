"""Terminalde bir animasyonu önizler. Kullanım:
    python tests/preview_art.py <id> [--w 64 --h 30] [--t 1.2] [--yaw 0.4] [--color] [--frames N]
3B shader'lar için --t zamanında kare üretir; statik animasyonlarda --frame ile kare seçer.
--color ANSI 24-bit renk basar (Windows Terminal destekler).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.core.library import AnimationLibrary  # noqa: E402
from src.core.procedural_engine import PROCEDURAL_REGISTRY, create_procedural_renderer  # noqa: E402


def to_ansi(lines, colors) -> str:
    out = []
    for r, line in enumerate(lines):
        row = []
        for c, ch in enumerate(line):
            rgb = colors[r][c] if colors and r < len(colors) and c < len(colors[r]) else None
            row.append(f"\x1b[38;2;{rgb[0]};{rgb[1]};{rgb[2]}m{ch}" if rgb and ch != " " else ch)
        out.append("".join(row) + "\x1b[0m")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("asset_id")
    ap.add_argument("--w", type=int, default=0)
    ap.add_argument("--h", type=int, default=0)
    ap.add_argument("--t", type=float, default=1.0)
    ap.add_argument("--yaw", type=float, default=0.0)
    ap.add_argument("--pitch", type=float, default=0.0)
    ap.add_argument("--frame", type=int, default=0)
    ap.add_argument("--color", action="store_true")
    args = ap.parse_args()

    lib = AnimationLibrary(BASE / "assets" / "animations")
    asset = lib.get(args.asset_id)
    if asset is None and args.asset_id in PROCEDURAL_REGISTRY:
        # Henüz .ascii.json'u olmayan shader'ı doğrudan kayıttan önizle
        from types import SimpleNamespace
        asset = SimpleNamespace(id=args.asset_id, is_procedural=True, procedural=args.asset_id, procedural_params={}, frames=[])
    if asset is None:
        print(f"Bulunamadı: {args.asset_id}")
        return 1
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
    if asset.is_procedural:
        r = create_procedural_renderer(asset.procedural, asset.procedural_params)
        if args.w and args.h:
            r.set_grid_size(args.w, args.h)
        r.yaw_offset, r.pitch_offset = args.yaw, args.pitch
        pf = r.render_at(args.t)
        lines, colors = pf.lines, pf.colors
    else:
        lines, colors = asset.frames[args.frame % len(asset.frames)].split("\n"), None
    print(to_ansi(lines, colors) if args.color else "\n".join(lines))
    print(f"[{asset.id}] {len(lines[0])}x{len(lines)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
