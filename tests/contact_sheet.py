"""Tüm statik animasyonların ilk karesini tek bir metin sayfasında gösterir (gözle kontrol için).
Kullanım: python tests/contact_sheet.py [çıktı.txt]   (varsayılan: stdout ve tests/contact_sheet.txt)
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.core.library import AnimationLibrary  # noqa: E402


def build_sheet(lib: AnimationLibrary) -> str:
    out = []
    for asset in sorted(lib.all_assets(), key=lambda a: (a.category, a.id)):
        if asset.is_procedural or not asset.frames:
            continue
        lines = asset.frames[0].split("\n")
        w = max(len(l) for l in lines)
        out.append("=" * 72)
        out.append(f"{asset.id}  |  {asset.name}  |  {asset.category}  |  {w}x{len(lines)}  kare:{len(asset.frames)}")
        out.append("+" + "-" * w + "+")
        out.extend("|" + l.ljust(w) + "|" for l in lines)
        out.append("+" + "-" * w + "+")
    return "\n".join(out) + "\n"


def main() -> int:
    lib = AnimationLibrary(BASE / "assets" / "animations")
    sheet = build_sheet(lib)
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else BASE / "tests" / "contact_sheet.txt"
    dest.write_text(sheet, encoding="utf-8")
    print(sheet)
    print(f"[contact_sheet] {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
