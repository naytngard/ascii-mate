"""Tüm SDF sahnelerini derler → assets/animations/**/<id>.ascii.json + .ascii.hd (+ klasik yedek kareler) ve önizlemeler.

Kullanım:
    python tools/scenes/build_assets.py              # hepsi
    python tools/scenes/build_assets.py cat_bust_3d  # yalnızca seçilenler
    python tools/scenes/build_assets.py --previews   # yalnızca önce/sonra PNG (build/previews/)
    python tools/scenes/build_assets.py --workers=8 --normal-priority   # hızlı mod (varsayılan: 3 süreç, düşük öncelik)
Kaynaklar: yalnızca bu klasördeki parametrik SDF modelleri (harici görsel/mesh yok). Çalışma anında render YOK.
"""

from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

# Her süreç tek iş parçacığı kullansın: NumPy/BLAS her süreçte ayrıca tüm çekirdekleri açarsa süreçler birbirini boğar
# (8 süreç × 16 iş parçacığı → dakikalarca ilerlemeyen derleme + tam yükte fan). NumPy içe aktarılmadan önce ayarlanmalı.
for _v in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ.setdefault(_v, "1")

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
DEFAULT_WORKERS = 3  # hafif mod: dizüstünde fanı zorlamaz; hız için --workers=N


def _low_priority() -> None:
    """Derleme arka plan işi: süreci düşük önceliğe al (Windows: BELOW_NORMAL; alt süreçler devralır)."""
    try:
        if os.name == "nt":
            import ctypes

            k = ctypes.windll.kernel32
            k.GetCurrentProcess.restype = ctypes.c_void_p  # 64 bit sözde tanıtıcı: varsayılan c_int onu kırpar
            k.SetPriorityClass.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
            k.SetPriorityClass(k.GetCurrentProcess(), 0x00004000)
        else:
            os.nice(10)
    except Exception:  # öncelik ayarlanamazsa derleme yine de çalışır
        pass

import numpy as np  # noqa: E402

import common  # noqa: E402

# id: (kurucu, klasör, ad, kategori, etiketler, kare, fps, sütun, yenilenen-eski-model-mi)
SPECS = {
    "cat_bust_3d": ("cat", "cats_and_pets", "HD Tekir Kedi (gerçekçi, göz kırpan)", "Kediler & Evcil Hayvanlar", ["kedi", "tekir", "göz kırpma"], 48, 8, 130, True),
    "owl_bust_3d": ("owl", "cats_and_pets", "HD Puhu Baykuş (dalda)", "Kediler & Evcil Hayvanlar", ["baykuş", "puhu", "gece", "göz kırpma"], 48, 8, 110, True),
    "dog_bust_3d": ("dog", "cats_and_pets", "HD Golden Retriever (soluyan)", "Kediler & Evcil Hayvanlar", ["köpek", "golden", "evcil"], 48, 8, 130, True),
    "fox_bust_3d": ("fox", "cats_and_pets", "HD Kızıl Tilki (oturan)", "Kediler & Evcil Hayvanlar", ["tilki", "orman", "kuyruk"], 48, 8, 120, True),
    "wolf_campfire_3d": ("wolf", "nature_and_weather", "HD Kamp Ateşi Başında Kurt", "Doğa & Hava Durumu", ["kurt", "kamp ateşi", "gece"], 48, 8, 150, True),
    "knight_sitting_3d": ("knight_grass", "retro_and_fun", "HD Çimenlerde Oturan Şövalye", "Retro & Geek", ["şövalye", "zırh", "kılıç", "çimen"], 48, 8, 130, True),
    "dragon_baby_3d": ("dragon", "retro_and_fun", "HD Ejderha Yavrusu", "Retro & Geek", ["ejderha", "fantezi", "kanat"], 48, 8, 120, True),
    "sentinel_robot_3d": ("robot", "space_and_3d", "HD Nöbetçi Robot", "Uzay & Bilim Kurgu", ["robot", "bilim kurgu"], 48, 8, 110, True),
    "astronaut_eva_3d": ("astronaut", "space_and_3d", "HD Uzay Yürüyüşü Astronotu", "Uzay & Bilim Kurgu", ["astronot", "uzay", "yıldız"], 48, 8, 120, True),
    "wizard_book_3d": ("wizard", "study_and_lofi", "HD Büyücü & Büyülü Kitap", "Ders & Lo-Fi Odak", ["büyücü", "kitap", "ders"], 48, 8, 110, True),
    "bonsai_tree_3d": ("bonsai", "nature_and_weather", "HD Bonsai Ağacı", "Doğa & Hava Durumu", ["bonsai", "ağaç", "huzur"], 48, 8, 120, True),
    "hd_knight_resting": ("knight_sunset", "retro_and_fun", "HD Gün Batımında Dinlenen Şövalye", "Retro & Geek", ["şövalye", "gün batımı", "kılıç"], 48, 8, 150, False),
    "hd_rider_horse": ("rider", "retro_and_fun", "HD Atlı Süvari (sepya)", "Retro & Geek", ["at", "süvari", "sepya", "kovboy"], 48, 8, 160, False),
    "hd_meadow_warrior": ("meadow_warrior", "nature_and_weather", "HD Çayırda Dinlenen Savaşçı", "Doğa & Hava Durumu", ["savaşçı", "çayır", "çiçek", "rüzgar"], 48, 8, 150, False),
    "hd_skeleton_giant": ("skeleton", "retro_and_fun", "HD Dev İskelet ve Savaşçı (kırmızı sis)", "Retro & Geek", ["iskelet", "fantezi", "sis"], 48, 8, 170, False),
}
FALLBACK_COLS = 62


def _frame(args):
    builder, ph, cols, levels = args
    import animals

    s, light, cam = getattr(animals, "build_" + builder)(ph)
    # gerçekçi: kontur/öznitelik karakteri yok. ss=1 (hücre başına 2×4 örnek): ss=2 ile görsel fark yok, 4-5 kat hızlı
    ch, co, lv = common.render_cells_smooth(s, light, cam, cols, levels=levels, ss=1)
    ov = cam.get("overlay")
    if ov is not None:
        ch, co = ch.copy(), co.copy()
        ov(ch, co, ph)
    return ch, co, lv


def quantize_colors(colors: np.ndarray, chars: np.ndarray) -> np.ndarray:
    """Renkleri kanal başına 5 bite indirir (adım 8, hücre ortası). Gözle fark edilmez; ama nefes gibi çok küçük
    gölge değişimleri artık hücreyi 'değişmiş' saymaz → çizici daha az hücre yazar (CPU) ve dosya küçülür."""
    q = ((colors >> 3) << 3) | 4
    q[chars == 32] = 0
    return q.astype(np.uint8)


def build(asset_id: str, pool: ProcessPoolExecutor) -> None:
    builder, folder, name, cat, tags, n, fps, cols, renewed = SPECS[asset_id]
    t0 = time.perf_counter()
    ch0, co0, levels = _frame((builder, 0.0, cols, None))  # ortak kontrast: ilk karenin düzeyleri tüm döngüde kullanılır
    rest = list(pool.map(_frame, [(builder, i / n, cols, levels) for i in range(1, n)]))
    chars = [ch0] + [r[0] for r in rest]
    colors = [quantize_colors(c, ch) for c, ch in zip([co0] + [r[1] for r in rest], chars)]
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
    workers = DEFAULT_WORKERS
    for a in args:
        if a.startswith("--workers="):
            workers = max(1, int(a.split("=", 1)[1]))
    if "--normal-priority" not in args:
        _low_priority()
    with ProcessPoolExecutor(max_workers=workers, initializer=None if "--normal-priority" in args else _low_priority) as pool:
        for aid in ids:
            build(aid, pool)
    return 0


if __name__ == "__main__":
    sys.exit(main())
