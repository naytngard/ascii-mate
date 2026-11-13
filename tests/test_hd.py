"""HD (schema 3.0) testleri: format gidiş-dönüş, doğrulayıcı, geriye uyumluluk, bellek tavanı, çizici, dönüştürücü."""

from __future__ import annotations

import json
import sys
import tracemalloc
from pathlib import Path

import numpy as np
import pytest

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "tools"))

from src.core.converter import validate_ascii_json_dict, import_file_to_community  # noqa: E402
from src.core.hd_format import CACHE_FRAMES, HDFormatError, HDReader, write_hd  # noqa: E402
from src.core.library import AnimationLibrary  # noqa: E402
from src.core.models import AnimationAsset, WidgetState  # noqa: E402

ANIM = BASE / "assets" / "animations"


def _frames(n=3, rows=6, cols=10, seed=1):
    rng = np.random.default_rng(seed)
    ch = [rng.integers(32, 127, (rows, cols), dtype=np.uint8) for _ in range(n)]
    co = [rng.integers(0, 256, (rows, cols, 3), dtype=np.uint8) for _ in range(n)]
    return ch, co


def _meta(**kw):
    d = {"schema_version": "3.0", "hd": True, "id": "t", "name": "T", "hd_file": "t.ascii.hd",
         "cols": 10, "rows": 6, "frame_count": 3, "default_fps": 10.0}
    d.update(kw)
    return d


# ------------------------------------------------------------------ format

def test_hd_roundtrip_exact(tmp_path):
    ch, co = _frames()
    write_hd(tmp_path / "a.ascii.hd", ch, co)
    rd = HDReader(tmp_path / "a.ascii.hd")
    assert (rd.cols, rd.rows, rd.frame_count) == (10, 6, 3)
    for i in range(3):
        rc, rk = rd.frame(i)
        assert np.array_equal(rc, ch[i]) and np.array_equal(rk, co[i])
    assert np.array_equal(rd.frame(4)[0], ch[1])  # indeks modüler


def test_hd_rejects_non_ascii_and_inconsistent(tmp_path):
    ch, co = _frames()
    bad = [c.copy() for c in ch]
    bad[0][0, 0] = 200
    with pytest.raises(HDFormatError):
        write_hd(tmp_path / "x.ascii.hd", bad, co)
    with pytest.raises(HDFormatError):
        write_hd(tmp_path / "x.ascii.hd", ch, co[:2])


def test_hd_reader_detects_corruption(tmp_path):
    ch, co = _frames()
    p = tmp_path / "c.ascii.hd"
    write_hd(p, ch, co)
    raw = bytearray(p.read_bytes())
    p.write_bytes(bytes(raw[:10]))  # kesik başlık
    with pytest.raises(HDFormatError):
        HDReader(p)
    raw[-5:] = b"\x00\x00\x00\x00\x00"
    p.write_bytes(bytes(raw))
    with pytest.raises(HDFormatError):
        HDReader(p).frame(2)
    p.write_bytes(b"NOPE" + b"\x00" * 40)
    with pytest.raises(HDFormatError):
        HDReader(p)


# ------------------------------------------------------------------ doğrulayıcı / model

def test_validator_accepts_and_rejects_hd_meta():
    assert validate_ascii_json_dict(_meta())[0]
    for bad in (_meta(schema_version="2.0"), _meta(hd_file="../x.ascii.hd"), _meta(hd_file="x.json"),
                _meta(cols=0), _meta(rows=10_000), _meta(frame_count=True), _meta(bg_mode="neon"), _meta(default_fps=500)):
        assert not validate_ascii_json_dict(bad)[0], bad
    d = _meta()
    del d["cols"]
    assert not validate_ascii_json_dict(d)[0]


def test_asset_from_dict_hd_fields():
    a = AnimationAsset.from_dict(_meta(bg_mode="solid"), source_path=str(Path("C:/x/t.ascii.json")))
    assert a.is_hd and a.frame_count == 3 and a.dimensions == (10, 6) and a.has_multicolor
    assert a.bg_mode == "solid" and a.hd_path().name == "t.ascii.hd"
    assert AnimationAsset.from_dict(a.to_dict()).hd_cols == 10


def test_widget_state_hd_fields_clamped():
    s = WidgetState.from_dict("a", {"hd_quality": "ultra", "hd_fps_cap": 999})
    assert s.hd_quality == "medium" and s.hd_fps_cap == 15.0


def test_hd_import_via_dragdrop_is_rejected_with_hint(tmp_path):
    src = tmp_path / "t.ascii.json"
    src.write_text(json.dumps(_meta()), encoding="utf-8")
    asset, msg = import_file_to_community(src, tmp_path / "community")
    assert asset is None and "iki dosya" in msg


# ------------------------------------------------------------------ geriye uyumluluk

def test_legacy_assets_load_unchanged():
    lib = AnimationLibrary(ANIM)
    legacy = [a for a in lib.all_assets() if not a.is_hd]
    assert len(legacy) >= 134
    for a in legacy:
        assert not a.hd and a.hd_file is None and a.hd_frame_count == 0
        assert a.frames or a.procedural
        assert a.schema_version in ("1.0", "2.0")
    for aid in ("saturn_3d", "heart_3d", "donut_3d", "christmas_tree_3d", "cat_bust_3d"):
        assert lib.get(aid) is not None and lib.get(aid).is_procedural


def test_legacy_json_files_have_no_hd_keys():
    for p in ANIM.rglob("*.ascii.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        if d.get("hd"):
            continue
        assert str(d.get("schema_version", "1.0")) in ("1.0", "2.0"), p.name
        assert "hd_file" not in d, p.name


def test_hd_samples_present_and_valid():
    lib = AnimationLibrary(ANIM)
    hd = [a for a in lib.all_assets() if a.is_hd]
    assert {a.id for a in hd} >= {"hd_torus_knot_spin", "hd_poppy_field", "hd_portrait_static"}
    for a in hd:
        rd = HDReader(a.hd_path())
        assert (rd.cols, rd.rows, rd.frame_count) == (a.hd_cols, a.hd_rows, a.hd_frame_count)
        assert a.hd_cols >= 100  # gerçekten yüksek çözünürlük


# ------------------------------------------------------------------ bellek tavanı

def test_hd_memory_ceiling_lazy_and_bounded():
    a = AnimationLibrary(ANIM).get("hd_torus_knot_spin")
    tracemalloc.start()
    rd = HDReader(a.hd_path())
    after_open = tracemalloc.get_traced_memory()[0]
    assert rd.cached_frames() == 0 and after_open < 1_000_000  # açılışta hiç kare çözülmez
    for i in range(rd.frame_count * 2):
        rd.frame(i)
        assert rd.cached_frames() <= CACHE_FRAMES
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert peak < 8_000_000  # 48 karenin tamamı dolaşıldı; tepe bellek <8 MB (ham 48 kare ≈ 4 MB değil, yalnızca önbellek)
    raw = rd.rows * rd.cols * 4 * rd.frame_count
    assert rd.compressed_bytes() < raw * 0.6  # sıkıştırma gerçekten çalışıyor


# ------------------------------------------------------------------ çizici

@pytest.fixture(scope="module")
def qapp():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def _player(tmp_path, qapp, ch, co, **meta):
    from src.gui.hd_renderer import HDPlayer

    p = tmp_path / "t.ascii.hd"
    write_hd(p, ch, co)
    a = AnimationAsset.from_dict(_meta(cols=ch[0].shape[1], rows=ch[0].shape[0], frame_count=len(ch), **meta),
                                 source_path=str(tmp_path / "t.ascii.json"))
    pl = HDPlayer(a)
    pl.configure(4, 8, 1, 1.0)
    return pl


def test_incremental_render_equals_full_render(tmp_path, qapp):
    ch, co = _frames(n=2, rows=8, cols=12)
    ch[1][:4] = ch[0][:4]  # kısmi değişim
    co[1][:4] = co[0][:4]
    a = _player(tmp_path, qapp, ch, co)
    a.render(0)
    a.render(1)  # artımlı
    b = _player(tmp_path, qapp, ch, co)
    b.render(1)  # sıfırdan
    assert np.array_equal(a._buf, b._buf)
    assert a.render(1) is False  # değişmeyen kare: hiç çizim yok


def test_static_and_space_cells_are_transparent(tmp_path, qapp):
    ch, co = _frames(n=1, rows=4, cols=6)
    ch[0][:] = 32
    ch[0][1, 1] = ord("#")
    pl = _player(tmp_path, qapp, ch, co)
    pl.render(0)
    alpha = pl._buf[..., 3]
    cell = alpha.reshape(4, 8, 6, 4)  # (satır, ch, sütun, cw)
    assert cell[1, :, 1, :].max() > 0
    assert alpha.sum() == cell[1, :, 1, :].sum()  # yalnızca '#' hücresi opak; zemin saydam


def test_mask_fades_and_restores(tmp_path, qapp):
    ch, co = _frames(n=1, rows=4, cols=6)
    ch[0][:] = ord("@")
    pl = _player(tmp_path, qapp, ch, co)
    pl.render(0)
    full = int(pl._buf[..., 3].sum())
    lv = np.full((4, 6), 3, np.int8)
    pl.set_mask(lv, np.zeros((4, 6), bool), 0.2)
    pl.render(0)
    faded = int(pl._buf[..., 3].sum())
    assert faded < full * 0.35
    pl.set_mask(None, None, 0.2)
    pl.invalidate()
    pl.render(0)
    assert int(pl._buf[..., 3].sum()) == full


def test_decimation_halves_grid(tmp_path, qapp):
    ch, co = _frames(n=1, rows=8, cols=12)
    pl = _player(tmp_path, qapp, ch, co)
    pl.configure(4, 8, 2, 1.0)
    assert (pl.dcols, pl.drows) == (6, 4)
    assert pl.pixel_size == (6 * 8, 4 * 16)  # fiziksel boyut korunur
    assert pl.render(0)


# ------------------------------------------------------------------ dönüştürücü

def test_ramp_is_sorted_by_measured_ink(qapp):
    import hd_convert as hc

    ramp = hc.build_ramp("auto")
    inks = [r[1] for r in ramp]
    assert ramp[0] == (" ", 0.0) and inks == sorted(inks) and len(ramp) >= 15
    assert all(32 <= ord(c) <= 126 for c, _ in ramp)


def test_convert_rgba_background_is_space_and_ascii_only(qapp):
    import hd_convert as hc

    arr = np.zeros((40, 80, 4), np.float32)
    arr[10:30, 20:60, :3] = (1.0, 0.4, 0.1)
    arr[10:30, 20:60, 3] = 1.0
    ramp = hc.build_ramp("auto")
    ch, co = hc.convert_rgba(arr, 40, 10, ramp)
    assert ch.shape == (10, 40) and co.shape == (10, 40, 3)
    assert ch[0, 0] == 32 and ch[5, 20] != 32
    assert ch.min() >= 32 and ch.max() <= 126
    assert (co[ch == 32] == 0).all()


def test_obj_pipeline_produces_valid_asset(tmp_path, qapp):
    import hd_convert as hc

    obj = tmp_path / "tri.obj"
    obj.write_text("v -1 -1 0\nv 1 -1 0\nv 0 1 0\nv 0 0 1\nf 1 2 3\nf 1 2 4\nf 2 3 4\nf 1 3 4\n", encoding="utf-8")
    rc = hc.main([str(obj), "--out", str(tmp_path), "--id", "tri", "--cols", "40", "--frames", "4", "--fps", "8"])
    assert rc == 0
    meta = json.loads((tmp_path / "tri.ascii.json").read_text(encoding="utf-8"))
    assert validate_ascii_json_dict(meta)[0] and meta["frame_count"] == 4 and meta["schema_version"] == "3.0"
    rd = HDReader(tmp_path / "tri.ascii.hd")
    assert rd.frame(0)[0].max() > 32


# ------------------------------------------------------------------ tepsi: HD sınırı ve onay

def _manager(tmp_path, qapp):
    from src.core.config_manager import ConfigManager
    from src.core.library import ThemeLibrary
    from src.gui.tray_manager import WidgetHostManager

    cfg = ConfigManager(tmp_path / "cfg.json")
    return WidgetHostManager(qapp, BASE, AnimationLibrary(ANIM), ThemeLibrary(BASE / "assets" / "themes.json"), cfg, enable_ipc=False), cfg


def test_hd_confirmation_required_then_remembered(tmp_path, qapp, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    m, cfg = _manager(tmp_path, qapp)
    asked = []
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: asked.append(a[2]) or QMessageBox.StandardButton.No))
    assert m.spawn_widget("hd_portrait_static") is None  # onay reddedildi → açılmaz
    assert asked and "DAHA FAZLA CPU" in asked[0]
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: QMessageBox.StandardButton.Yes))
    w = m.spawn_widget("hd_portrait_static")
    assert w is not None and cfg.get_global("hd_enabled") is True
    monkeypatch.setattr(QMessageBox, "question", staticmethod(lambda *a, **k: (_ for _ in ()).throw(AssertionError("tekrar sorulmamalı"))))
    w2 = m.spawn_widget("hd_portrait_static")
    assert w2 is not None
    for x in list(m.widgets.values()):
        x.close_widget()


def test_at_most_two_hd_widgets(tmp_path, qapp, monkeypatch):
    from PyQt6.QtWidgets import QMessageBox

    m, cfg = _manager(tmp_path, qapp)
    cfg.set_global("hd_enabled", True)
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", staticmethod(lambda *a, **k: warned.append(a[2])))
    a = m.spawn_widget("hd_portrait_static")
    b = m.spawn_widget("hd_portrait_static")
    assert a is not None and b is not None
    assert m.spawn_widget("hd_poppy_field") is None and warned and "en fazla 2" in warned[0]
    assert m.spawn_widget("cat_bust_3d") is not None  # HD olmayanlar etkilenmez
    a.close_widget()
    assert m.spawn_widget("hd_poppy_field") is not None  # bir yer açılınca yine açılır
    for x in list(m.widgets.values()):
        x.close_widget()


def test_hd_widget_ticks_pause_and_rate_limits(tmp_path, qapp):
    from src.core.config_manager import ConfigManager
    from src.core.library import ThemeLibrary
    from src.gui.companion_widget import CompanionWidget

    lib = AnimationLibrary(ANIM)
    cfg = ConfigManager(tmp_path / "c.json")
    th = ThemeLibrary(BASE / "assets" / "themes.json")
    spin = CompanionWidget("t", lib.get("hd_torus_knot_spin"), lib, th, cfg)
    assert spin._hd_fps() <= 15.0  # dönen HD en fazla 15 FPS
    spin.state.custom_fps = 30.0
    assert spin._hd_fps() <= 15.0
    spin.set_hd_quality("low")
    assert spin._hd_fps() <= 8.0 and spin._hd.decim == 2
    still = CompanionWidget("t2", lib.get("hd_portrait_static"), lib, th, cfg)
    assert still._tick_timer.interval() >= 500  # durağan HD seyrek uyanır
    spin._suspended = True
    before = spin._hd_frame
    spin._on_tick()
    assert spin._hd_frame == before  # duraklatılmışken ilerlemez
    for w in (spin, still):
        w._close_notified = True
        w.close()
