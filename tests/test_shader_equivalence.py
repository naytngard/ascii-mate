"""NumPy'a vektörleştirilen shader'ların orijinal saf-Python sürümle BİREBİR aynı çıktı verdiğini kanıtlar."""

from __future__ import annotations

import random

import pytest

from src.core.procedural_engine import create_procedural_renderer

VECTORIZED = ["saturn_3d", "donut_3d", "heart_3d"]


@pytest.mark.parametrize("pid", VECTORIZED)
def test_vectorized_shader_identical_to_reference(pid):
    rng = random.Random(1234 + len(pid))
    r = create_procedural_renderer(pid)
    for _ in range(120):
        r.set_grid_size(rng.choice([24, 38, 46, 52, 64, 74, 88]), rng.choice([14, 18, 22, 24, 30, 34, 40]))
        r.yaw_offset, r.pitch_offset = rng.uniform(-3.0, 3.0), rng.uniform(-1.2, 1.2)
        r.cursor_look = (rng.uniform(-1.0, 1.0), rng.uniform(-1.0, 1.0))
        t = rng.uniform(0.0, 600.0)
        fast, ref = r.render_at(t), r._render_at_reference(t)
        assert fast.lines == ref.lines
        assert fast.colors == ref.colors
