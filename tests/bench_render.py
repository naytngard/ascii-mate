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
TICKS = 120


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


def main() -> int:
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
