"""HD görünürlük: widget büyüyünce (hücre boyutu artınca) soluklaşma telafisi ("backing") ve küçük boyutta değişmezlik."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from src.core.library import AnimationLibrary
from src.gui import hd_renderer as H

ANIM = Path(__file__).resolve().parent.parent / "assets" / "animations"


@pytest.fixture(scope="module")
def cat():
    return AnimationLibrary(ANIM).get("cat_bust_3d")


def _silhouette_alpha(asset, cw: int, mode: str) -> float:
    p = H.HDPlayer(asset)
    p.configure(cw, cw * 2, 1, 0.94, mode)
    p.render(0)
    img = p.composite()
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    a = np.frombuffer(ptr, np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)[:, : img.width(), 3].astype(np.float32) / 255.0
    mask = np.kron((p._prev_chars != 32).astype(np.uint8), np.ones((p.ch, p.cw), np.uint8)).astype(bool)
    return float(a[mask].mean())


def test_backing_curve_zero_for_small_cells_and_monotonic():
    assert H.backing_for_cell(4) == 0.0 and H.backing_for_cell(H.BACKING_FROM_CW) == 0.0
    vals = [H.backing_for_cell(cw) for cw in range(4, 25)]
    assert all(b2 >= b1 for b1, b2 in zip(vals, vals[1:]))
    assert vals[-1] == pytest.approx(H.BACKING_MAX) and 0.45 <= H.BACKING_MAX <= 0.55
    assert H.backing_for_cell(12, "off") == 0.0 and H.backing_for_cell(12, "strong") > H.backing_for_cell(12, "auto")


def test_small_cells_unchanged_by_backing(cat):
    for cw in (4, 5, 6):
        assert _silhouette_alpha(cat, cw, "auto") == pytest.approx(_silhouette_alpha(cat, cw, "off"))


def _real_glyphs() -> bool:
    """Offscreen Qt (CI/Linux) sistem yazı tipi yok: glifler özdeş kutu olur; kaplama ölçümü yalnızca gerçek glifle anlamlı."""
    at = H.build_atlas(8, 16)
    return not np.array_equal(at[ord("@") - 32], at[ord(".") - 32])


def test_large_over_small_coverage_ratio_at_least_085(cat):
    if not _real_glyphs():
        pytest.skip("gerçek glif yok (offscreen)")
    small = _silhouette_alpha(cat, 6, "auto")
    for cw in (8, 10, 12, 16):
        assert _silhouette_alpha(cat, cw, "auto") / small >= 0.85, cw


def test_backing_adds_cover_for_large_cells_and_far_empty_cells_stay_transparent(cat):
    assert _silhouette_alpha(cat, 12, "auto") > _silhouette_alpha(cat, 12, "off")
    p = H.HDPlayer(cat)
    p.configure(12, 24, 1, 0.94)
    p.render(0)
    img = p.composite()
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    a = np.frombuffer(ptr, np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)[:, : img.width(), 3]
    filled = p._prev_chars != 32
    far = (~filled) & (H._neighbour_occupancy(filled) == 0)  # hiçbir komşusu dolu olmayan hücreler
    far_px = np.kron(far.astype(np.uint8), np.ones((p.ch, p.cw), np.uint8)).astype(bool)
    assert far.any() and int(a[far_px].max()) == 0  # uzaktaki boş hücreler (arka plan) tamamen saydam kalır; zemin en fazla 1 hücre taşar


def test_strong_denser_than_auto_and_state_persists(cat, tmp_path):
    assert _silhouette_alpha(cat, 12, "strong") > _silhouette_alpha(cat, 12, "auto") > _silhouette_alpha(cat, 12, "off")
    from src.core.models import WidgetState

    s = WidgetState.from_dict("x", {"hd_backing": "strong"})
    assert s.hd_backing == "strong" and WidgetState.from_dict("x", s.to_dict()).hd_backing == "strong"
    assert WidgetState.from_dict("x", {"hd_backing": "bogus"}).hd_backing == "auto"
    assert WidgetState.from_dict("x", None).hd_backing == "auto"  # varsayılan Auto


def test_soft_edge_backing_lighter_on_silhouette_border(cat):
    """Siluet kenarındaki hücrelerde zemin, iç hücrelere göre belirgin daha seyrek (kutu görünümü yok)."""
    p = H.HDPlayer(cat)
    p.configure(12, 24, 1, 0.94, "auto")
    p.render(0)
    img = p.composite()
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    a = np.frombuffer(ptr, np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)[:, : img.width(), 3].astype(np.float32)
    cell_a = a.reshape(p.drows, p.ch, p.dcols, p.cw).mean(axis=(1, 3))
    filled = p._prev_chars != 32
    occ = H._neighbour_occupancy(filled)
    inner = filled & (occ > 0.99)
    border = filled & (occ < 0.6)
    assert inner.any() and border.any()
    assert cell_a[border].mean() < cell_a[inner].mean() * 0.85


def test_hd_background_menu_en_and_tr(tmp_path):
    from PyQt6.QtWidgets import QApplication

    from src.core import i18n
    from src.core.config_manager import ConfigManager
    from src.core.library import ThemeLibrary
    from src.gui.companion_widget import CompanionWidget
    from src.gui.context_menu import build_context_menu

    lib = AnimationLibrary(ANIM)
    w = CompanionWidget("t", lib.get("hd_poppy_field"), lib, ThemeLibrary(ANIM.parent / "themes.json"), ConfigManager(tmp_path / "c.json"))
    try:
        def texts(m):
            out = []
            for act in m.actions():
                out.append(act.text())
                if act.menu() is not None:
                    out += texts(act.menu())
            return out

        i18n.set_language("en")
        en = texts(build_context_menu(w))
        assert any("HD Background (Auto)" in t for t in en) and "Strong" in en and "Off" in en
        w.set_hd_backing("strong")
        assert w.state.hd_backing == "strong" and w._hd.backing >= 0.0
        assert any("HD Background (Strong)" in t for t in texts(build_context_menu(w)))
        i18n.set_language("tr")
        assert any("HD Zemin (Güçlü)" in t for t in texts(build_context_menu(w)))
    finally:
        w.close_widget()