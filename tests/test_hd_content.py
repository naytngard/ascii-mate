"""HD içerik görevi testleri: yenilenen modeller, yeni sahneler, klasik yedek, telif koruması, yerel dönüştürücü."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "tools"))

from src.core.converter import validate_ascii_json_dict  # noqa: E402
from src.core.hd_format import HDReader  # noqa: E402
from src.core.library import AnimationLibrary  # noqa: E402

ANIM = BASE / "assets" / "animations"
RENEWED = ["cat_bust_3d", "owl_bust_3d", "dog_bust_3d", "fox_bust_3d", "wolf_campfire_3d", "knight_sitting_3d",
           "dragon_baby_3d", "sentinel_robot_3d", "astronaut_eva_3d", "wizard_book_3d", "bonsai_tree_3d"]
NEW_SCENES = ["hd_knight_resting", "hd_rider_horse", "hd_meadow_warrior", "hd_skeleton_giant"]
# Repoda izin verilen HD varlıkların tamamı (kaynakları bu depodaki betiklerde): bilinmeyen kaynaklı HD dosyası olmamalı
KNOWN_HD = set(RENEWED + NEW_SCENES + ["hd_torus_knot_spin", "hd_poppy_field"])
REFERENCE_NAMES = ["belyukin", "fantasy world", "indir", "pinterest", "local_"]


@pytest.fixture(scope="module")
def lib():
    return AnimationLibrary(ANIM)


@pytest.mark.parametrize("aid", RENEWED + NEW_SCENES)
def test_hd_asset_with_classic_fallback(lib, aid):
    a = lib.get(aid)
    assert a is not None and a.is_hd, aid
    rd = HDReader(a.hd_path())
    assert rd.cols >= 100 and rd.frame_count >= 12  # gerçekten yüksek çözünürlük + hafif hareket
    c0, _ = rd.frame(0)
    assert any((rd.frame(i)[0] != c0).any() for i in range(1, rd.frame_count))  # canlılık (nefes/kırpma/kuyruk...)
    # HD kapalıyken açılacak klasik yedek: 50-70 sütun, palet ve renk haritası geçerli
    assert a.frames, "klasik yedek kare yok"
    lines = a.frames[0].split("\n")
    assert 50 <= len(lines[0]) <= 70 and len(lines) >= 12
    data = json.loads(Path(a.source_path).read_text(encoding="utf-8"))
    assert validate_ascii_json_dict(data)[0]
    assert a.get_frame_colors(0) is not None


def test_renewed_ids_keep_profiles_working(lib):
    from src.core.config_manager import DEFAULT_PROFILES

    for items in DEFAULT_PROFILES.values():
        for it in items:
            assert lib.get(it["asset_id"]) is not None, it["asset_id"]


def test_hd_meta_fallback_validation_rejects_bad_frames():
    meta = json.loads((ANIM / "cats_and_pets" / "cat_bust_3d.ascii.json").read_text(encoding="utf-8"))
    bad = dict(meta, frames=[meta["frames"][0] + "x"])
    assert not validate_ascii_json_dict(bad)[0]


# ------------------------------------------------------------------ telif koruması

def test_no_unknown_hd_assets_in_repo():
    found = {p.name[: -len(".ascii.hd")] for p in ANIM.rglob("*.ascii.hd")}
    assert found <= KNOWN_HD, f"bilinmeyen kaynaklı HD dosyası: {sorted(found - KNOWN_HD)}"


def test_no_reference_derived_files_tracked_by_git():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=BASE, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git yok")
    tracked = out.lower().splitlines()
    for name in REFERENCE_NAMES:
        hits = [f for f in tracked if name in Path(f).name and f.startswith(("assets/", "tests/", "tools/samples"))]
        assert not hits, f"referans kaynaklı olabilecek dosya izleniyor: {hits}"
    assert not any(f.endswith((".jpg", ".jpeg", ".webp")) for f in tracked), "repoda fotoğraf/resim dosyası olmamalı"


def test_scene_assets_declare_own_source():
    for aid in RENEWED + NEW_SCENES:
        p = next(ANIM.rglob(f"{aid}.ascii.json"))
        d = json.loads(p.read_text(encoding="utf-8"))
        assert "tools/scenes" in d.get("source", ""), aid


# Hazır 3B modelden üretilen sahneler: model repoda YOK, yalnız üretilen HD kareler + künye (yazar, URL, lisans)
MESH_SCENES = ["knight_sitting_3d", "hd_knight_resting", "sentinel_robot_3d", "astronaut_eva_3d", "dragon_baby_3d"]
ALLOWED_MODEL_LICENSES = {"CC0", "CC0 1.0", "Public Domain"}


@pytest.mark.parametrize("aid", MESH_SCENES)
def test_mesh_scenes_declare_model_credit_and_cc0(aid):
    d = json.loads(next(ANIM.rglob(f"{aid}.ascii.json")).read_text(encoding="utf-8"))
    cr = d.get("model_credit") or {}
    assert cr.get("license") in ALLOWED_MODEL_LICENSES, aid
    assert cr.get("author") and cr.get("url", "").startswith("https://"), aid
    assert "mesh_scenes.py" in d.get("source", "") and cr["license"] in d["source"], aid
    third = (BASE / "THIRD_PARTY.md").read_text(encoding="utf-8")
    assert cr["url"] in third, aid  # her model THIRD_PARTY.md'de listeli


def test_no_3d_model_files_tracked_by_git():
    try:
        out = subprocess.run(["git", "ls-files"], cwd=BASE, capture_output=True, text=True, check=True).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git yok")
    bad = [f for f in out.splitlines() if f.lower().endswith((".obj", ".fbx", ".blend", ".glb", ".gltf", ".mtl", ".3ds"))
           or "models_cache" in f]
    assert not bad, f"3B model/doku dosyası izleniyor (repoya girmemeli): {bad}"


# ------------------------------------------------------------------ yerel dönüştürücü

def test_import_local_art_refuses_repo_and_writes_outside(tmp_path):
    import import_local_art as ila
    from PyQt6.QtGui import QColor, QImage

    import hd_convert as hc

    hc.ensure_qt()
    img = QImage(80, 60, QImage.Format.Format_RGB32)
    img.fill(QColor(200, 220, 255))  # açık "gökyüzü"
    for x in range(30, 50):
        for y in range(15, 60):
            img.setPixelColor(x, y, QColor(60, 40, 30))  # koyu özne
    src = tmp_path / "ornek.png"
    img.save(str(src))
    with pytest.raises(SystemExit):
        ila.main([str(src), "--out", str(ANIM / "community"), "--cols", "40", "--no-preview"])
    out = tmp_path / "yerel"
    assert ila.main([str(src), "--out", str(out), "--cols", "40", "--bg", "auto", "--anim", "wind", "--frames", "6",
                     "--no-preview"]) == 0
    meta = json.loads((out / "local_ornek.ascii.json").read_text(encoding="utf-8"))
    assert validate_ascii_json_dict(meta)[0] and meta["frame_count"] == 6
    rd = HDReader(out / "local_ornek.ascii.hd")
    ch, _ = rd.frame(0)
    assert (ch[:3] == 32).mean() > 0.9  # üst gökyüzü arka plan olarak ayrıldı (saydam)
    assert (ch[ch.shape[0] // 2:, 16:24] != 32).any()  # özne korundu


def test_wind_animation_changes_only_bottom_region():
    import import_local_art as ila

    rng = np.random.default_rng(0)
    ch = rng.integers(33, 127, (20, 30), dtype=np.uint8)
    co = rng.integers(0, 256, (20, 30, 3), dtype=np.uint8)
    frames, _ = ila.animate(ch, co, ["wind"], 8, region=0.3)
    for f in frames:
        assert (f[:14] == ch[:14]).all()  # üst %70 hiç değişmez → çizici yalnızca alt hücreleri yazar
    assert any((f[14:] != ch[14:]).any() for f in frames)


def test_user_art_dir_is_scanned_by_library(tmp_path):
    import hd_convert as hc

    user = tmp_path / "community"
    rng = np.random.default_rng(1)
    hc.write_asset(user, "local_test", "Yerel", "Topluluk / Özel Eklenenler",
                   [rng.integers(33, 127, (6, 12), dtype=np.uint8)], [rng.integers(0, 256, (6, 12, 3), dtype=np.uint8)], 1.0)
    lib = AnimationLibrary(ANIM, user_art_dir=user)
    a = lib.get("local_test")
    assert a is not None and a.is_hd and a.is_community


def test_widget_uses_classic_fallback_when_forced(tmp_path):
    from PyQt6.QtWidgets import QApplication

    from src.core.config_manager import ConfigManager
    from src.core.library import ThemeLibrary
    from src.gui.companion_widget import CompanionWidget

    app = QApplication.instance() or QApplication([])  # noqa: F841
    lib = AnimationLibrary(ANIM)
    cfg = ConfigManager(tmp_path / "c.json")
    th = ThemeLibrary(BASE / "assets" / "themes.json")
    hd = CompanionWidget("a", lib.get("cat_bust_3d"), lib, th, cfg)
    classic = CompanionWidget("b", lib.get("cat_bust_3d"), lib, th, cfg, force_classic=True)
    assert hd._hd is not None and classic._hd is None
    assert 50 <= len(classic._current_lines[0]) <= 70
    assert classic._tick_timer.interval() >= 250  # tek kareli yedek: neredeyse hiç iş yok
    for w in (hd, classic):
        w._close_notified = True
        w.close()


# ------------------------------------------------------------------ denetim düzeltmeleri (parlaklık, yerel dönüştürücü)

@pytest.mark.parametrize("aid", RENEWED + NEW_SCENES)
def test_hd_assets_bright_enough_for_desktop(aid):
    """Koyu sahneler masaüstünde kaybolmasın: dolu hücrelerin ortalama renk parlaklığı >= 125 (0..255)."""
    import hd_brightness

    p = next(ANIM.rglob(f"{aid}.ascii.hd"))
    assert hd_brightness.mean_brightness(p) >= 125.0, aid


def test_clahe_raises_local_contrast_and_stays_in_range():
    import import_local_art as ila

    y, x = np.mgrid[0:120, 0:160]
    lum = 0.15 + 0.05 * np.sin(x / 6.0) + 0.6 * (x > 80)  # sol yarı: düşük kontrastlı koyu doku
    out = ila.clahe(lum, tiles=4, clip=2.5)
    assert out.min() >= 0.0 and out.max() <= 1.0
    assert out[:, :70].std() > lum[:, :70].std() * 2  # koyu bölgedeki doku belirginleşti


def test_min_brightness_lifts_dark_colors():
    import hd_convert as hc

    arr = np.zeros((40, 80, 4), np.float32)
    arr[..., :3] = (0.12, 0.08, 0.06)  # çok koyu zırh rengi
    arr[..., 3] = 1.0
    ramp = hc.build_ramp("auto")
    _, dark = hc.convert_rgba(arr, 40, 10, ramp, bg_threshold=0.0)
    _, lifted = hc.convert_rgba(arr, 40, 10, ramp, bg_threshold=0.0, min_brightness=0.5)
    assert lifted.max(axis=-1).mean() >= 120 > dark.max(axis=-1).mean()


def test_tinted_bg_mode_validates_and_renders(tmp_path):
    import hd_convert as hc
    from src.core.models import AnimationAsset
    from src.gui.hd_renderer import HDPlayer

    rng = np.random.default_rng(3)
    ch = [rng.integers(32, 127, (8, 12), dtype=np.uint8) for _ in range(2)]
    co = [rng.integers(0, 256, (8, 12, 3), dtype=np.uint8) for _ in range(2)]
    jp, _ = hc.write_asset(tmp_path, "tinted_t", "T", "Topluluk / Özel Eklenenler", ch, co, 5.0, bg_mode="tinted")
    meta = json.loads(jp.read_text(encoding="utf-8"))
    assert validate_ascii_json_dict(meta)[0]
    a = AnimationAsset.from_dict(meta, source_path=str(jp))
    assert a.bg_mode == "tinted"
    pl = HDPlayer(a)
    pl.configure(4, 8, 1, 1.0)
    assert pl.render(0) and pl.render(1)
    assert (pl._buf[..., 3] > 0).all()  # tinted: her piksel koyu renkli zemin taşır (boşluk yok)


def test_mesh_motion_loops_and_is_small():
    """Mesh sahneleri: kamera/yön sabit, köşe deformasyonu faza bağlı, faz 0 = faz 1 (kesintisiz döngü), hareket küçük."""
    sys.path.insert(0, str(BASE / "tools" / "scenes"))
    import mesh_scenes as ms

    assert ms.breath_curve(0.0) == pytest.approx(ms.breath_curve(1.0)) and 0.0 <= ms.breath_curve(0.2) <= 1.0
    assert ms.breath_curve(0.2) > 0.95 and ms.breath_curve(0.0) == 0.0  # tepe %40'ta
    for b in ("knight_grass", "knight_sunset", "robot", "astronaut", "dragon"):
        if not (ms.CACHE / ms.BUILDERS[b]["obj"]).exists():  # modeller repoda yok (tools/models_cache, git-ignore): CI'da atlanır
            continue
        v, _f, c, _n = ms.load(ms.BUILDERS[b]["obj"])
        v0, c0 = ms.deform(b, 0.0, v, c)
        v1, _ = ms.deform(b, 1.0, v, c)
        assert np.allclose(v0, v1, atol=1e-5), b
        vm, _ = ms.deform(b, 0.2, v, c)
        size = float(np.linalg.norm(v.max(axis=0) - v.min(axis=0)))
        assert 0.0 < float(np.abs(vm - v0).max()) < 0.06 * size, b  # görünür ama küçük (<%6)