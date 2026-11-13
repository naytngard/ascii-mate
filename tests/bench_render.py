"""Çizim/tick maliyet ölçümü (offscreen Qt). Kullanım: python tests/bench_render.py [asset_id ...]

Her widget için ardışık tick + çizim (paintEvent'in yaptığı pixmap yeniden kurma dahil) süresini ölçer ve
widget'ın gerçek zamanlayıcı aralığına göre TAHMİNİ tek çekirdek CPU yüzdesini yazar.
(Gerçek ekran birleştirme/DWM maliyeti dahil değildir; göreli karşılaştırma içindir.)
"""

from __future__ import annotations

import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from PyQt6.QtWidgets import QApplication  # noqa: E402

from src.core.config_manager import ConfigManager  # noqa: E402
from src.core.library import AnimationLibrary, ThemeLibrary  # noqa: E402
from src.gui.companion_widget import CompanionWidget  # noqa: E402

DEFAULT_IDS = ["cat_bust_3d", "owl_bust_3d", "galaxy_vortex_3d", "rainy_window_3d", "coffee_3d", "saturn_3d"]
HD_IDS = ["hd_portrait_static", "hd_poppy_field", "hd_torus_knot_spin"]
TICKS = 120


def working_set_mb() -> float:
    """Bu sürecin çalışma kümesi (MB); yalnızca Windows, aksi halde 0."""
    if os.name != "nt":
        return 0.0
    import ctypes
    from ctypes import wintypes

    class PMC(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD), ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t), ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t), ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t), ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]

    pmc = PMC()
    pmc.cb = ctypes.sizeof(PMC)
    k32, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    k32.GetCurrentProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(PMC), wintypes.DWORD]
    psapi.GetProcessMemoryInfo(k32.GetCurrentProcess(), ctypes.byref(pmc), pmc.cb)
    return pmc.WorkingSetSize / 1048576.0


def bench_one(app, lib, themes, cfg, asset_id: str, **state_over) -> tuple[float, int]:
    asset = lib.get(asset_id)
    if asset is None:
        raise SystemExit(f"asset yok: {asset_id}")
    w = CompanionWidget(f"bench_{asset_id}", asset, lib, themes, cfg)
    for k, v in state_over.items():
        setattr(w.state, k, v)
    w._invalidate_art()
    w._update_timer_interval()
    interval_ms = w._tick_timer.interval()
    w._tick_timer.stop()
    w.show()
    app.processEvents()
    # ısınma
    for _ in range(10):
        w._on_tick()
        if w._art_dirty:
            w._rebuild_art_pixmap()
    t0 = time.process_time()
    for _ in range(TICKS):
        w._last_tick_time -= interval_ms / 1000.0  # sabit dt simüle et
        w._on_tick()
        if w._art_dirty:
            w._rebuild_art_pixmap()
    dt = time.process_time() - t0
    w._close_notified = True
    w.close()
    return dt / TICKS * 1000.0, interval_ms


def bench_hd(app, lib, themes, cfg, asset_id: str, quality: str = "medium") -> tuple[float, int, float, float]:
    """(ms/tick, aralık ms, widget'ın RAM'e eklediği MB, ortalama kare güncelleme maliyeti ms). Çizim = w.grab() (paintEvent)."""
    from PyQt6.QtGui import QPixmap

    asset = lib.get(asset_id)
    if asset is None:
        raise SystemExit(f"asset yok: {asset_id}")
    ram0 = working_set_mb()
    w = CompanionWidget(f"bench_{asset_id}", asset, lib, themes, cfg)
    w.state.hd_quality = quality
    w._recalculate_size()
    w._update_timer_interval()
    interval_ms = w._tick_timer.interval()
    w._tick_timer.stop()
    w.show()
    app.processEvents()
    for _ in range(6):
        w._last_tick_time -= interval_ms / 1000.0
        w._on_tick()
    last = w._hd._last_idx
    n = TICKS if asset.frame_count > 1 else 20
    total = 0.0
    frames_drawn = 0
    t_paint = 0.0
    for _ in range(n):
        w._last_tick_time -= interval_ms / 1000.0
        t0 = time.perf_counter()
        w._on_tick()
        total += time.perf_counter() - t0
        if w._hd._last_idx != last:
            last = w._hd._last_idx
            t1 = time.perf_counter()
            w.grab()  # paintEvent: tek drawImage
            t_paint += time.perf_counter() - t1
            frames_drawn += 1
    ram = working_set_mb() - ram0
    per_tick = (total + t_paint) / n * 1000.0
    w._close_notified = True
    w.close()
    return per_tick, interval_ms, ram, (t_paint / frames_drawn * 1000.0 if frames_drawn else 0.0)


def main() -> int:
    if len(sys.argv) > 1 and sys.argv[1] == "--hd":
        app = QApplication.instance() or QApplication([])
        lib = AnimationLibrary(BASE / "assets" / "animations")
        themes = ThemeLibrary(BASE / "assets" / "themes.json")
        cfg = ConfigManager(Path(tempfile.mkdtemp()) / "bench.json")
        print(f"{'HD senaryo':30} {'kalite':>7} {'ms/tick':>8} {'aralık':>7} {'~CPU%':>7} {'+RAM MB':>8} {'paint ms':>9}")
        for aid in HD_IDS:
            for q in ("low", "medium", "high"):
                ms, iv, ram, pm = bench_hd(app, lib, themes, cfg, aid, q)
                print(f"{aid:30} {q:>7} {ms:8.2f} {iv:6d}ms {ms / iv * 100:6.2f}% {ram:8.1f} {pm:9.2f}")
        return 0
    ids = sys.argv[1:] or DEFAULT_IDS
    app = QApplication.instance() or QApplication([])
    lib = AnimationLibrary(BASE / "assets" / "animations")
    themes = ThemeLibrary(BASE / "assets" / "themes.json")
    cfg = ConfigManager(Path(tempfile.mkdtemp()) / "bench.json")
    print(f"{'asset':24} {'ms/kare':>9} {'aralık':>7} {'~CPU%':>7}")
    total = 0.0
    for aid in ids:
        ms, iv = bench_one(app, lib, themes, cfg, aid)
        cpu = ms / iv * 100.0
        total += cpu
        print(f"{aid:24} {ms:9.2f} {iv:6d}ms {cpu:6.1f}%")
    print(f"{'TOPLAM (hepsi birlikte)':24} {'':9} {'':7} {total:6.1f}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
