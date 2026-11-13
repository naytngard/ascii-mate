"""Birim testleri: converter, ConfigManager, AnimationLibrary, WidgetState, IPC, 3B modeller, kütüphane doğrulayıcı."""

from __future__ import annotations

import json
import os
import threading
import uuid
from multiprocessing.connection import AuthenticationError, Client, Listener
from pathlib import Path

import pytest

from src.core import config_manager as cm
from src.core.config_manager import ConfigManager, widget_state_key
from src.core.converter import normalize_frames, slugify, txt_to_ascii_json, validate_ascii_json_dict
from src.core.library import AnimationLibrary
from src.core.models import WidgetState
from src.core.procedural_engine import PROCEDURAL_REGISTRY, create_procedural_renderer

BASE = Path(__file__).resolve().parent.parent


# ------------------------------------------------------------------ converter

def test_normalize_frames_pads_to_uniform_geometry():
    out = normalize_frames(["ab\nc", "x"])
    sizes = {(len(f.split("\n")), tuple(len(l) for l in f.split("\n"))) for f in out}
    assert len(sizes) == 1
    assert all(len(l) == 2 for f in out for l in f.split("\n"))


def test_txt_to_json_valid_and_slug():
    d = txt_to_ascii_json("A\nB\n===FRAME===\nC\nD\n", name="Çok İyi Kedi")
    assert d["id"] == slugify("Çok İyi Kedi") == "cok_iyi_kedi"
    ok, msg = validate_ascii_json_dict(d)
    assert ok, msg
    assert len(d["frames"]) == 2


def test_txt_import_file_leading_blank_lines_do_not_shift_frame0():
    d = txt_to_ascii_json("\n\n  AA\n  BB\n===FRAME===\n  AA\n  CC\n")
    f0, f1 = (f.split("\n") for f in d["frames"])
    assert f0.index("  AA") == f1.index("  AA") == 0


def test_txt_import_preserves_intentional_relative_offset():
    """Kare başına ayrı kırpma yerine ortak üst boşluk korunur: 2. karedeki bilinçli 1 satır kayma kaybolmaz."""
    d = txt_to_ascii_json("AA\nBB\n\n\n\nAA\nCC")
    f0, f1 = (f.split("\n") for f in d["frames"])
    assert f0.index("AA") == 0
    assert f1.index("AA") == 1
    assert len(f0) == len(f1)


def test_validate_rejects_inconsistent_frames():
    ok, _ = validate_ascii_json_dict({"id": "x", "name": "x", "frames": ["ab\ncd", "abc\ncd"]})
    assert not ok
    ok, _ = validate_ascii_json_dict({"id": "x", "name": "x", "frames": []})
    assert not ok


# ------------------------------------------------------------------ WidgetState

def test_widget_state_clamps_and_defaults():
    st = WidgetState.from_dict("a", {"font_size": 9999, "opacity": -3, "speed_multiplier": "abc", "custom_fps": 1e9,
                                     "x": "bad", "y": 5, "behind_text_fade": 7})
    assert st.font_size == 48
    assert st.opacity == 0.15
    assert st.speed_multiplier == 1.0
    assert st.custom_fps == 60.0
    assert st.x is None and st.y is None  # ikisi de geçerli değilse konum atılır
    assert st.behind_text_fade == 0.6
    assert st.glow_enabled is False and st.behind_text_enabled is False


def test_widget_state_nan_inf_fall_back():
    st = WidgetState.from_dict("a", {"opacity": float("nan"), "font_size": float("inf")})
    assert st.opacity == 0.94 and st.font_size == 14


# ------------------------------------------------------------------ ConfigManager

def test_config_two_managers_do_not_clobber_each_other(tmp_path):
    path = tmp_path / "config.json"
    a, b = ConfigManager(path), ConfigManager(path)
    a.toggle_favorite("x")
    b.toggle_favorite("y")  # b'nin belleği 'x'i hiç görmedi ama diskten tazeleyip birleştirmeli
    a.set_global("k", 1)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["favorites"] == ["x", "y"]
    assert data["global"]["k"] == 1


def test_config_corrupt_file_is_backed_up(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{bozuk", encoding="utf-8")
    c = ConfigManager(path)
    assert (tmp_path / "config.json.bak").read_text(encoding="utf-8") == "{bozuk"
    assert c.get_favorites() == []
    assert json.loads(path.read_text(encoding="utf-8"))["favorites"] == []


def test_config_save_survives_permission_errors(tmp_path, monkeypatch):
    path = tmp_path / "config.json"
    c = ConfigManager(path)
    real_replace = Path.replace
    calls = {"n": 0}

    def flaky(self, target):
        calls["n"] += 1
        if calls["n"] <= 3:
            raise PermissionError("OneDrive kilidi")
        return real_replace(self, target)

    monkeypatch.setattr(Path, "replace", flaky)
    monkeypatch.setattr(cm.time, "sleep", lambda *_: None)
    c.toggle_favorite("kalici")  # istisna fırlatmamalı
    assert "kalici" in json.loads(path.read_text(encoding="utf-8"))["favorites"]


def test_config_save_never_raises_when_unwritable(tmp_path, monkeypatch):
    c = ConfigManager(tmp_path / "config.json")
    monkeypatch.setattr(Path, "replace", lambda self, t: (_ for _ in ()).throw(PermissionError("kilit")))
    monkeypatch.setattr(cm.time, "sleep", lambda *_: None)
    c.toggle_favorite("x")  # çökmemeli


def test_second_instance_has_its_own_state_key(tmp_path):
    c = ConfigManager(tmp_path / "config.json")
    s0 = c.get_widget_state("cat", 0)
    s0.font_size = 20
    c.save_widget_state(s0, 0)
    s1 = c.get_widget_state("cat", 1)
    assert s1.font_size == 14  # ikinci kopya birinciyle ayar paylaşmaz
    s1.font_size = 30
    c.save_widget_state(s1, 1)
    assert c.get_widget_state("cat", 0).font_size == 20
    assert widget_state_key("cat", 1) == "cat#2"


# ------------------------------------------------------------------ AnimationLibrary

def _asset(aid: str, name: str = "T") -> dict:
    return {"id": aid, "name": name, "frames": ["a\nb"] * 1, "category": "Diğer"}


def test_library_duplicate_id_builtin_wins_over_community(tmp_path):
    anim = tmp_path / "animations"
    (anim / "cats_and_pets").mkdir(parents=True)
    (anim / "community").mkdir(parents=True)
    (anim / "cats_and_pets" / "a.ascii.json").write_text(json.dumps(_asset("dup", "YERLESIK")), encoding="utf-8")
    (anim / "community" / "z.ascii.json").write_text(json.dumps(_asset("dup", "TOPLULUK")), encoding="utf-8")
    lib = AnimationLibrary(anim)
    assert lib.get("dup").name == "YERLESIK"
    assert lib.warnings and "dup" in lib.warnings[0]
    assert not lib.load_errors


def test_library_duplicate_id_first_builtin_kept(tmp_path):
    anim = tmp_path / "animations"
    anim.mkdir()
    (anim / "a.ascii.json").write_text(json.dumps(_asset("dup", "ILK")), encoding="utf-8")
    (anim / "b.ascii.json").write_text(json.dumps(_asset("dup", "IKINCI")), encoding="utf-8")
    lib = AnimationLibrary(anim)
    assert lib.get("dup").name == "ILK"
    assert len(lib.warnings) == 1


# ------------------------------------------------------------------ IPC (authkey)

def test_ipc_rejects_wrong_authkey():
    addr = rf"\\.\pipe\ascii_mate_test_{uuid.uuid4().hex}" if os.name == "nt" else f"/tmp/ascii_mate_test_{uuid.uuid4().hex}.sock"
    key = b"dogru-anahtar-" + uuid.uuid4().hex.encode()
    got = {}

    def serve():
        with Listener(addr, authkey=key) as lst:
            for _ in range(2):  # 1. yanlış anahtar (reddedilir), 2. doğru
                try:
                    conn = lst.accept()
                except AuthenticationError:
                    got["rejected"] = True
                    continue
                got["msg"] = conn.recv()
                conn.send({"ok": True})
                conn.close()

    th = threading.Thread(target=serve, daemon=True)
    th.start()
    import time

    time.sleep(0.2)
    with pytest.raises(Exception):
        Client(addr, authkey=b"yanlis-anahtar").close()
    with Client(addr, authkey=key) as c:
        c.send({"cmd": "ping"})
        assert c.recv() == {"ok": True}
    th.join(timeout=3)
    assert got.get("rejected") and got.get("msg") == {"cmd": "ping"}


def test_pipe_exists_probe_does_not_consume_pipe():
    from src.core.ipc import pipe_exists

    if os.name != "nt":
        pytest.skip("Windows named pipe")
    addr = rf"\\.\pipe\ascii_mate_probe_{uuid.uuid4().hex}"
    assert not pipe_exists(addr)
    with Listener(addr, authkey=b"k" * 16):
        assert pipe_exists(addr)
        assert pipe_exists(addr)  # tekrar yoklama pipe'ı tüketmez


# ------------------------------------------------------------------ 3B modeller ve doğrulayıcı

NEW_MODELS = [
    "cat_bust_3d", "owl_bust_3d", "dog_bust_3d", "fox_bust_3d", "knight_sitting_3d", "dragon_baby_3d",
    "sentinel_robot_3d", "astronaut_eva_3d", "wizard_book_3d", "wolf_campfire_3d", "bonsai_tree_3d",
]


@pytest.mark.parametrize("mid", NEW_MODELS)
def test_model_renders_scaled_pure_ascii_with_content(mid):
    r = create_procedural_renderer(mid)
    assert r is not None and mid in PROCEDURAL_REGISTRY
    for gw, gh in ((38, 18), (52, 24), (74, 34)):
        r.set_grid_size(gw, gh)
        pf = r.render_at(1.3)
        assert len(pf.lines) == gh and all(len(l) == gw for l in pf.lines)
        assert all(32 <= ord(c) <= 126 for l in pf.lines for c in l)
        filled = sum(1 for l in pf.lines for c in l if c != " ")
        assert filled > gw * gh * 0.08  # silüet dolu
    r.yaw_offset, r.pitch_offset, r.cursor_look = 0.6, -0.3, (0.8, -0.5)
    assert r.render_at(2.0).lines


@pytest.mark.parametrize("mid", ["cat_bust_3d", "owl_bust_3d", "dog_bust_3d", "fox_bust_3d"])
def test_animal_models_have_outline_and_face_markers(mid):
    r = create_procedural_renderer(mid)
    r.set_grid_size(64, 30)
    text = "\n".join(r.render_at(0.0).lines)
    assert any(ch in text for ch in "/\\()")  # kontur
    assert any(ch in text for ch in "oO@v")  # göz/burun öznitelikleri


def test_validate_library_script_passes():
    import validate_library

    assert validate_library.main() == 0


def test_config_tolerates_utf8_bom(tmp_path):
    path = tmp_path / "config.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"favorites": ["a"], "global": {"x": 1}}).encode("utf-8"))
    c = ConfigManager(path)
    assert c.get_favorites() == ["a"] and c.get_global("x") == 1
    assert not (tmp_path / "config.json.bak").exists()
