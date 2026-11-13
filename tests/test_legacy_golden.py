"""Eski çizimlerin (klasik ASCII + matematiksel shader'lar) birebir aynı kaldığını kanıtlar.

Altın özetler `tests/make_golden.py` ile commit 6a64039'da (HD içerik görevinden ÖNCE) üretildi.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

import make_golden as mg

GOLDEN = json.loads((Path(__file__).parent / "golden_legacy.json").read_text(encoding="utf-8"))


def test_golden_covers_classic_set():
    assert len(GOLDEN["files"]) >= 120
    for pid in ("saturn_3d", "heart_3d", "donut_3d", "christmas_tree_3d", "galaxy_vortex_3d", "dna_helix_3d",
                "matrix_rain_hd", "atom_3d", "warp_stars_3d", "ocean_wave_3d", "aurora_shader"):
        assert pid in GOLDEN["shaders"]


@pytest.mark.parametrize("rel", sorted(GOLDEN["files"]))
def test_legacy_json_unchanged(rel):
    p = mg.BASE / rel
    assert p.exists(), f"silinmiş: {rel}"
    assert mg.file_digest(p) == GOLDEN["files"][rel], f"değişmiş: {rel}"


@pytest.mark.parametrize("pid", sorted(GOLDEN["shaders"]))
def test_legacy_shader_output_unchanged(pid):
    assert mg.shader_digest(pid) == GOLDEN["shaders"][pid], f"shader çıktısı değişmiş: {pid}"
