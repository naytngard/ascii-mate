"""HD varlıkların ortalama renk parlaklığı (boş olmayan hücreler, ilk kare, 0..255). Koyu sahneleri yakalamak için."""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

import numpy as np  # noqa: E402

from src.core.hd_format import HDReader  # noqa: E402


def mean_brightness(path: Path) -> float:
    ch, co = HDReader(path).frame(0)
    m = ch != 32
    if not m.any():
        return 0.0
    c = co[m].astype(np.float32)
    return float((0.2126 * c[:, 0] + 0.7152 * c[:, 1] + 0.0722 * c[:, 2]).mean())


if __name__ == "__main__":
    roots = [Path(a) for a in sys.argv[1:]] or [BASE / "assets" / "animations"]
    for root in roots:
        for p in sorted(root.rglob("*.ascii.hd")):
            print(f"{mean_brightness(p):6.1f}  {p.name}")
