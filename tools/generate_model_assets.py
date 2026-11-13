"""ascii_models tabanlı 3B model asset'lerini (.ascii.json) üretir/günceller.

Kullanım: python tools/generate_model_assets.py
`frames` alanı yalnızca terminal önizlemesi/dışa aktarma içindir; canlı çizimi `procedural` shader'ı yapar.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.core.procedural_engine import PROCEDURAL_REGISTRY, create_procedural_renderer  # noqa: E402

ANIM = BASE / "assets" / "animations"
OTHER = "Topluluk / Özel Eklenenler"

# id -> (klasör, ad, etiketler, kategori, parçacık, göz kırpma)
SPECS = {
    "cat_bust_3d": ("cats_and_pets", "3B Dönen Kedi Büstü (Shader)", ["kedi", "3b", "büst", "shader", "göz kırpma"], "Kediler & Evcil Hayvanlar", ("hearts", "Mini Kalpler & Yıldızlar", "top"), True),
    "owl_bust_3d": ("cats_and_pets", "3B Bilge Baykuş (Shader)", ["baykuş", "3b", "bilge", "gece", "shader"], "Kediler & Evcil Hayvanlar", ("stars", "Gece Yıldızları", "around"), True),
    "dog_bust_3d": ("cats_and_pets", "3B Neşeli Köpek (Shader)", ["köpek", "3b", "evcil", "kuyruk", "shader"], "Kediler & Evcil Hayvanlar", ("hearts", "Mini Kalpler", "top"), True),
    "fox_bust_3d": ("cats_and_pets", "3B Sevimli Tilki (Shader)", ["tilki", "3b", "orman", "kuyruk", "shader"], "Kediler & Evcil Hayvanlar", ("sparks", "Kıvılcımlar", "around"), True),
    "knight_sitting_3d": ("retro_and_fun", "3B Çimenlerde Oturan Şövalye (Shader)", ["şövalye", "zırh", "kılıç", "çimen", "3b", "shader"], "Retro & Geek", ("none", "Parçacık Efekti", "around"), False),
    "dragon_baby_3d": ("retro_and_fun", "3B Ejderha Yavrusu (Shader)", ["ejderha", "fantezi", "kanat", "3b", "shader"], "Retro & Geek", ("sparks", "Kıvılcımlar", "top"), True),
    "sentinel_robot_3d": ("space_and_3d", "3B Nöbetçi Robot (Shader)", ["robot", "bilim kurgu", "nöbetçi", "3b", "shader"], "Uzay & Bilim Kurgu", ("none", "Parçacık Efekti", "around"), False),
    "astronaut_eva_3d": ("space_and_3d", "3B Uzay Yürüyüşü Astronotu (Shader)", ["astronot", "uzay", "yıldız", "3b", "shader"], "Uzay & Bilim Kurgu", ("stars", "Yıldız Tozu", "around"), False),
    "wizard_book_3d": ("study_and_lofi", "3B Büyücü & Büyülü Kitap (Shader)", ["büyücü", "kitap", "ders", "fantezi", "3b", "shader"], "Ders & Lo-Fi Odak", ("stars", "Büyü Tozu", "around"), False),
    "wolf_campfire_3d": ("nature_and_weather", "3B Kamp Ateşi Başında Kurt (Shader)", ["kurt", "kamp ateşi", "gece", "doğa", "3b", "shader"], "Doğa & Hava Durumu", ("sparks", "Ateş Kıvılcımları", "bottom"), True),
    "bonsai_tree_3d": ("nature_and_weather", "3B Bonsai Ağacı (Shader)", ["bonsai", "ağaç", "huzur", "doğa", "3b", "shader"], "Doğa & Hava Durumu", ("none", "Parçacık Efekti", "around"), False),
}


def main() -> int:
    for mid, (folder, name, tags, category, (ptype, plabel, parea), blink) in SPECS.items():
        if mid not in PROCEDURAL_REGISTRY:
            print(f"[ATLA] kayıtta yok: {mid}")
            continue
        r = create_procedural_renderer(mid)
        frames = ["\n".join(r.render_at(t).lines) for t in (0.0, 0.7, 1.4, 2.1)]
        path = ANIM / folder / f"{mid}.ascii.json"
        data = {
            "schema_version": "2.0",
            "id": mid,
            "name": name,
            "category": category,
            "author": "ASCII Mate",
            "tags": tags,
            "default_fps": 12.0,
            "recommended_color": "auto_hd",
            "supports_eye_blink": blink,
            "supports_sleep_zzz": False,
            "particles": {
                "enabled_by_default": False,
                "type": ptype,
                "toggle_label": plabel,
                "spawn_area": parea,
                "density": "low",
                "chars": ["*", "+", "."],
            },
            "frames": frames,
            "procedural": mid,
            "procedural_params": {"width": r.width, "height": r.height},
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[OK] {path.relative_to(BASE)}  ({r.width}x{r.height})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
