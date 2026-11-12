"""Validation suite for the 100+ pure classic ASCII & 3D shader library."""

from __future__ import annotations

import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from src.core.converter import validate_ascii_json_dict
from src.core.library import AnimationLibrary
from src.core.procedural_engine import PROCEDURAL_REGISTRY, create_procedural_renderer

FORBIDDEN_PIXEL_BLOCKS = set("▀▄█░▒▓▌▐▛▜▙▟■□▪▫▬")


def check_pure_ascii_lines(lines: list[str], label: str) -> tuple[bool, str]:
    for r_i, line in enumerate(lines):
        for ch in line:
            if ch in FORBIDDEN_PIXEL_BLOCKS:
                return False, f"{label} satır {r_i}: Yasaklı pixel-art blok karakteri bulundu: {ch!r}"
            if not (32 <= ord(ch) <= 126):
                return False, f"{label} satır {r_i}: Klasik ASCII dışı karakter bulundu: {ch!r} (U+{ord(ch):04X})"
    return True, "OK"


def main() -> int:
    anim_dir = BASE_DIR / "assets" / "animations"
    json_files = sorted(anim_dir.rglob("*.ascii.json"))

    if not json_files:
        print("[FAIL] Hiç .ascii.json dosyası bulunamadı!")
        return 1

    passed = 0
    failed = 0
    seen_ids = {}

    for path in json_files:
        rel = path.relative_to(BASE_DIR)
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[FAIL] {rel}: JSON okunamadı ({e})")
            failed += 1
            continue

        ok, msg = validate_ascii_json_dict(data)
        if not ok:
            print(f"[FAIL] {rel}: {msg}")
            failed += 1
            continue

        # Check pure classic ASCII + zero pixel-art blocks in all frames
        frame_ok = True
        for fi, frame_str in enumerate(data["frames"]):
            c_ok, c_msg = check_pure_ascii_lines(frame_str.split("\n"), f"{rel}#frame{fi}")
            if not c_ok:
                print(f"[FAIL] {c_msg}")
                failed += 1
                frame_ok = False
                break
        if not frame_ok:
            continue

        aid = data["id"]
        if aid in seen_ids:
            print(f"[FAIL] {rel}: Çakışan ID '{aid}' (ilk görülen: {seen_ids[aid]})")
            failed += 1
            continue

        proc_id = data.get("procedural")
        if proc_id:
            renderer = create_procedural_renderer(str(proc_id), data.get("procedural_params"))
            if renderer is None:
                print(f"[FAIL] {rel}: Bilinmeyen prosedürel motor '{proc_id}'")
                failed += 1
                continue
            pf = renderer.step(0.033)
            if not pf.lines or not pf.colors:
                print(f"[FAIL] {rel}: Prosedürel motor '{proc_id}' boş kare üretti")
                failed += 1
                continue
            p_ok, p_msg = check_pure_ascii_lines(pf.lines, f"{rel}[{proc_id}]")
            if not p_ok:
                print(f"[FAIL] {p_msg}")
                failed += 1
                continue

        seen_ids[aid] = str(rel)
        passed += 1

    # Explicitly verify ALL procedural shaders in PROCEDURAL_REGISTRY
    proc_passed = 0
    for proc_id in sorted(PROCEDURAL_REGISTRY):
        renderer = create_procedural_renderer(proc_id)
        if renderer is None:
            print(f"[FAIL] PROCEDURAL_REGISTRY '{proc_id}' başlatılamadı")
            failed += 1
            continue
        ok_all = True
        for step_i in range(3):
            pf = renderer.step(0.15)
            p_ok, p_msg = check_pure_ascii_lines(pf.lines, f"shader:{proc_id}@step{step_i}")
            if not p_ok:
                print(f"[FAIL] {p_msg}")
                failed += 1
                ok_all = False
                break
        if ok_all:
            proc_passed += 1

    # Also test AnimationLibrary loader
    lib = AnimationLibrary(anim_dir)
    if lib.load_errors:
        for err in lib.load_errors:
            print(f"[FAIL] Library load error: {err}")
            failed += 1

    total = passed + failed
    print("-" * 60)
    print(f"Doğrulanan Toplam Dosya : {total}")
    print(f"Saf Klasik ASCII Kontrolü: TUMU TEMIZ (0 pixel-art blok)" if failed == 0 else f"Hata Sayısı: {failed}")
    print(f"Canlı 3B/Shader Motorları: {proc_passed} / {len(PROCEDURAL_REGISTRY)} PASS")
    print(f"Kütüphane Yüklenen      : {len(lib.assets)}")
    for cat in lib.categories():
        print(f"  • {cat}: {len(lib.by_category(cat))} adet")
    print("-" * 60)
    print(f"SONUÇ: {passed} / {total} PASS")

    if failed > 0 or passed < 100:
        if passed < 100:
            print(f"[FAIL] En az 100 animasyon bekleniyordu, şu an {passed} adet var.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
