"""Tüm SDF sahnelerini derler → assets/animations/**/<id>.ascii.json + .ascii.hd (+ klasik yedek kareler) ve önizlemeler.

Kullanım:
    python tools/scenes/build_assets.py              # hepsi
    python tools/scenes/build_assets.py cat_bust_3d  # yalnızca seçilenler
    python tools/scenes/build_assets.py --previews   # yalnızca önce/sonra PNG (build/previews/)
Kaynaklar: yalnızca bu klasördeki parametrik SDF modelleri (harici görsel/mesh yok). Çalışma anında render YOK.
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import numpy as np  # noqa: E402

import common  # noqa: E402

# id: (kurucu, klasör, ad, kategori, etiketler, kare, fps, sütun, yenilenen-eski-model-mi)
SPECS = {
    "cat_bust_3d": ("cat", "cats_and_pets", "HD Kedi Büstü (göz kırpan, bıyıklı)", "Kediler & Evcil Hayvanlar", ["kedi", "büst", "göz kırpma"], 24, 8, 120, True),
    "owl_bust_3d": ("owl", "cats_and_pets", "HD Bilge Baykuş", "Kediler & Evcil Hayvanlar", ["baykuş", "gece", "göz kırpma"], 24, 8, 110, True),
    "dog_bust_3d": ("dog", "cats_and_pets", "HD Neşeli Köpek (dil çıkaran)", "Kediler & Evcil Hayvanlar", ["köpek", "evcil"], 24, 8, 110, True),
    "fox_bust_3d": ("fox", "cats_and_pets", "HD Sevimli Tilki", "Kediler & Evcil Hayvanlar", ["tilki", "orman", "kuyruk"], 24, 8, 110, True),
    "wolf_campfire_3d": ("wolf", "nature_and_weather", "HD Kamp Ateşi Başında Kurt", "Doğa & Hava Durumu", ["kurt", "kamp ateşi", "gece"], 24, 8, 150, True),
    "knight_sitting_3d": ("knight_grass", "retro_and_fun", "HD Çimenlerde Oturan Şövalye", "Retro & Geek", ["şövalye", "zırh", "kılıç", "çimen"], 24, 8, 130, True),
    "dragon_baby_3d": ("dragon", "retro_and_fun", "HD Ejderha Yavrusu", "Retro & Geek", ["ejderha", "fantezi", "kanat"], 24, 8, 120, True),
    "sentinel_robot_3d": ("robot", "space_and_3d", "HD Nöbetçi Robot", "Uzay & Bilim Kurgu", ["robot", "bilim kurgu"], 24, 8, 110, True),
    "astronaut_eva_3d": ("astronaut", "space_and_3d", "HD Uzay Yürüyüşü Astronotu", "Uzay & Bilim Kurgu", ["astronot", "uzay", "yıldız"], 24, 8, 120, True),
    "wizard_book_3d": ("wizard", "study_and_lofi", "HD Büyücü & Büyülü Kitap", "Ders & Lo-Fi Odak", ["büyücü", "kitap", "ders"], 24, 8, 110, True),
    "bonsai_tree_3d": ("bonsai", "nature_and_weather", "HD Bonsai Ağacı", "Doğa & Hava Durumu", ["bonsai", "ağaç", "huzur"], 24, 8, 120, True),
    "hd_knight_resting": ("knight_sunset", "retro_and_fun", "HD Gün Batımında Dinlenen Şövalye", "Retro & Geek", ["şövalye", "gün batımı", "kılıç"], 24, 8, 150, False),
    "hd_rider_horse": ("rider", "retro_and_fun", "HD Atlı Süvari (sepya)", "Retro & Geek", ["at", "süvari", "sepya", "kovboy"], 24, 8, 160, False),
    "hd_meadow_warrior": ("meadow_warrior", "nature_and_weather", "HD Çayırda Dinlenen Savaşçı", "Doğa & Hava Durumu", ["savaşçı", "çayır", "çiçek", "rüzgar"], 24, 8, 150, False),
    "hd_skeleton_giant": ("skeleton", "retro_and_fun", "HD Dev İskelet ve Savaşçı (kırmızı sis)", "Retro & Geek", ["iskelet", "fantezi", "sis"], 24, 8, 170, False),
}
FALLBACK_COLS = 62


def _frame(args):
    builder, ph, cols, levels = args
    import animals

    s, light, cam = getattr(animals, "build_" + builder)(ph)
    ch, co, lv = common.render_cells(s, light, cam, cols, levels=levels)
    ov = cam.get("overlay")
    if ov is not None:
        ch, co = ch.copy(), co.copy()
        ov(ch, co, ph)
    return ch, co, lv


def build(asset_id: str, pool: ProcessPoolExecutor) -> None:
    builder, folder, name, cat, tags, n, fps, cols, renewed = SPECS[asset_id]
    t0 = time.perf_counter()
    ch0, co0, levels = _frame((builder, 0.0, cols, None))  # ortak kontrast: ilk karenin düzeyleri tüm döngüde kullanılır
    rest = list(pool.map(_frame, [(builder, i / n, cols, levels) for i in range(1, n)]))
    chars = [ch0] + [r[0] for r in rest]
    colors = [co0] + [r[1] for r in rest]
    fb = [_frame((builder, 0.0, FALLBACK_COLS, None))]  # tek kare: yedek tamamen durağan (sıfır CPU)
    fallback = common.palette_frames([f[0] for f in fb], [f[1] for f in fb])
    extra = {"supports_eye_blink": False, "fallback_note": "HD kapalıysa/sınır dolduysa klasik yedek kareler kullanılır"}
    jp = common.write_scene_asset(folder, asset_id, name, cat, chars, colors, fps, tags, fallback=fallback, extra=extra)
    prev = common.PREVIEW_DIR
    common.preview_png(chars[0], colors[0], prev / f"{asset_id}_after.png", cw=6, ch=12)
    common.preview_png(fb[0][0], fb[0][1], prev / f"{asset_id}_fallback.png", cw=8, ch=16)
    if renewed:
        before_png(asset_id, prev / f"{asset_id}_before.png")
    print(f"[OK] {jp.relative_to(common.BASE)}  {cols}x{chars[0].shape[0]}  {n} kare  {time.perf_counter() - t0:.0f} sn", flush=True)


def before_png(asset_id: str, path: Path) -> None:
    """Eski elipsoit sürümün (değiştirilmeden önceki) görüntüsü: aynı id'li prosedürel renderer."""
    sys.path.insert(0, str(common.BASE))
    from src.core.procedural_engine import create_procedural_renderer

    r = create_procedural_renderer(asset_id)
    if r is None:
        return
    pf = r.render_at(1.0)
    rows, cols = len(pf.lines), max(len(l) for l in pf.lines)
    ch = np.array([[ord(c) for c in l.ljust(cols)] for l in pf.lines], np.uint8)
    co = np.zeros((rows, cols, 3), np.uint8)
    for i, row in enumerate(pf.colors):
        for j, c in enumerate(row[:cols]):
            if c is not None:
                co[i, j] = c
    common.preview_png(ch, co, path, cw=8, ch=16)


def main(argv=None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])
    ids = [a for a in args if not a.startswith("--")] or list(SPECS)
    if "--previews" in args:
        for aid in ids:
            if SPECS[aid][8]:
                before_png(aid, common.PREVIEW_DIR / f"{aid}_before.png")
        return 0
    with ProcessPoolExecutor(max_workers=8) as pool:
        for aid in ids:
            build(aid, pool)
    return 0


if __name__ == "__main__":
    sys.exit(main())
