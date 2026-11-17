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


def _silhouette_alpha(asset, cw: int, backing: bool, monkeypatch) -> float:
    monkeypatch.setattr(H, "BACKING_MAX", H.BACKING_MAX if backing else 0.0)
    p = H.HDPlayer(asset)
    p.configure(cw, cw * 2, 1, 0.94)
    p.render(0)
    img = p.image
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    a = np.frombuffer(ptr, np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)[:, : img.width(), 3].astype(np.float32) / 255.0
    mask = np.kron((p._prev_chars != 32).astype(np.uint8), np.ones((p.ch, p.cw), np.uint8)).astype(bool)
    return float(a[mask].mean())


def test_backing_curve_zero_for_small_cells_and_monotonic():
    assert H.backing_for_cell(4) == 0.0 and H.backing_for_cell(H.BACKING_FROM_CW) == 0.0
    vals = [H.backing_for_cell(cw) for cw in range(4, 25)]
    assert all(b2 >= b1 for b1, b2 in zip(vals, vals[1:]))
    assert vals[-1] == pytest.approx(H.BACKING_MAX)


def test_small_cells_unchanged_by_backing(cat, monkeypatch):
    for cw in (4, 5, 6):
        assert _silhouette_alpha(cat, cw, True, monkeypatch) == pytest.approx(_silhouette_alpha(cat, cw, False, monkeypatch))


def _real_glyphs() -> bool:
    """Offscreen Qt (CI/Linux) sistem yazı tipi yok: glifler özdeş kutu olur; kaplama ölçümü yalnızca gerçek glifle anlamlı."""
    at = H.build_atlas(8, 16)
    return not np.array_equal(at[ord("@") - 32], at[ord(".") - 32])


def test_large_over_small_coverage_ratio_at_least_085(cat, monkeypatch):
    if not _real_glyphs():
        pytest.skip("gerçek glif yok (offscreen)")
    small = _silhouette_alpha(cat, 6, True, monkeypatch)
    for cw in (8, 10, 12, 16):
        assert _silhouette_alpha(cat, cw, True, monkeypatch) / small >= 0.85, cw


def test_backing_adds_cover_for_large_cells_and_empty_cells_stay_transparent(cat, monkeypatch):
    assert _silhouette_alpha(cat, 12, True, monkeypatch) > _silhouette_alpha(cat, 12, False, monkeypatch)
    p = H.HDPlayer(cat)
    p.configure(12, 24, 1, 0.94)
    p.render(0)
    img = p.image
    ptr = img.constBits()
    ptr.setsize(img.sizeInBytes())
    a = np.frombuffer(ptr, np.uint8).reshape(img.height(), img.bytesPerLine() // 4, 4)[:, : img.width(), 3]
    empty = np.kron((p._prev_chars == 32).astype(np.uint8), np.ones((p.ch, p.cw), np.uint8)).astype(bool)
    assert int(a[empty].max()) == 0  # boş hücreler (arka plan) tamamen saydam kalır
