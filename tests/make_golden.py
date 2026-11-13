"""Eski (dokunulmaması gereken) çizimlerin altın özetlerini üretir: tests/golden_legacy.json.

Yalnızca bilinçli bir değişiklikten sonra yeniden çalıştırın. Kapsam:
  * assets/animations altındaki tüm klasik/shader .ascii.json dosyaları (yenilenen elipsoit modelleri ve HD'ler hariç)
  * PROCEDURAL_REGISTRY'deki matematiksel shader'ların (Satürn, kalp, simit, yılbaşı ağacı, ...) 52x24 ve 64x30
    ızgarada t=0.0/1.0/2.7 karelerinin (satırlar + renkler) özeti.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

# Elipsoit motoruyla (src/core/ascii_models.py + ascii_animals.py) yapılmış ve bilinçli olarak HD'ye yenilenen modeller.
RENEWED_IDS = {
    "cat_bust_3d", "owl_bust_3d", "dog_bust_3d", "fox_bust_3d", "wolf_campfire_3d", "knight_sitting_3d",
    "dragon_baby_3d", "sentinel_robot_3d", "astronaut_eva_3d", "wizard_book_3d", "bonsai_tree_3d",
}


def file_digest(p: Path) -> str:
    return hashlib.sha256(p.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def shader_digest(pid: str) -> str:
    from src.core.procedural_engine import create_procedural_renderer

    h = hashlib.sha256()
    for w, hgt in ((52, 24), (64, 30)):
        r = create_procedural_renderer(pid)
        r.set_grid_size(w, hgt)
        for t in (0.0, 1.0, 2.7):
            pf = r.render_at(t)
            h.update("\n".join(pf.lines).encode("ascii"))
            h.update(repr(pf.colors).encode("ascii"))
    return h.hexdigest()


def legacy_files() -> list[Path]:
    out = []
    for p in sorted((BASE / "assets" / "animations").rglob("*.ascii.json")):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("hd") or d.get("id") in RENEWED_IDS:
            continue
        out.append(p)
    return out


def legacy_shaders() -> list[str]:
    from src.core.procedural_engine import PROCEDURAL_REGISTRY  # önce bu (dairesel içe aktarma sırası)
    from src.core.ascii_models import MODEL_REGISTRY

    return sorted(k for k in PROCEDURAL_REGISTRY if k not in MODEL_REGISTRY)


def build() -> dict:
    return {
        "files": {p.relative_to(BASE).as_posix(): file_digest(p) for p in legacy_files()},
        "shaders": {pid: shader_digest(pid) for pid in legacy_shaders()},
    }


if __name__ == "__main__":
    data = build()
    (BASE / "tests" / "golden_legacy.json").write_text(json.dumps(data, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"{len(data['files'])} dosya, {len(data['shaders'])} shader özeti yazıldı")
