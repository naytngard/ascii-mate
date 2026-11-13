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

        # Enforce pure ASCII inside particles.chars
        p_chars = (data.get("particles") or {}).get("chars") or []
        p_char_ok, p_char_msg = check_pure_ascii_lines(["".join(str(x) for x in p_chars)], f"{rel}#particles")
        if not p_char_ok:
            print(f"[FAIL] {p_char_msg}")
            failed += 1
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
        else:
            # Enforce detailed static artwork minimum height >= 12 and >= 8 non-blank lines
            first_lines = data["frames"][0].split("\n")
            non_blank_rows = sum(1 for ln in first_lines if ln.strip())
            if len(first_lines) < 12 or non_blank_rows < 8:
                print(
                    f"[FAIL] {rel}: Statik model cok kucuk ({len(first_lines)} satir, {non_blank_rows} dolu satir). "
                    f"Minimum 12 satir ve 8 dolu satir gerekli."
                )
                failed += 1
                continue

        seen_ids[aid] = str(rel)
        passed += 1

    # Explicitly verify ALL procedural shaders in PROCEDURAL_REGISTRY (dynamic grid + orbit + cursor + hourglass progress)
    proc_passed = 0
    for proc_id in sorted(PROCEDURAL_REGISTRY):
        renderer = create_procedural_renderer(proc_id)
        if renderer is None:
            print(f"[FAIL] PROCEDURAL_REGISTRY '{proc_id}' başlatılamadı")
            failed += 1
            continue
        ok_all = True
        for step_i in range(2):
            pf = renderer.step(0.15)
            p_ok, p_msg = check_pure_ascii_lines(pf.lines, f"shader:{proc_id}@step{step_i}")
            if not p_ok:
                print(f"[FAIL] {p_msg}")
                failed += 1
                ok_all = False
                break

        if ok_all:
            renderer.set_grid_size(64, 30)
            renderer.yaw_offset = 0.45
            renderer.pitch_offset = -0.25
            renderer.cursor_look = (0.7, -0.4)
            if proc_id == "hourglass_3d":
                renderer.progress = 0.35
            pf_hd = renderer.render_at(1.2)
            if len(pf_hd.lines) != 30 or len(pf_hd.lines[0]) != 64:
                print(
                    f"[FAIL] shader:{proc_id}: set_grid_size(64, 30) beklenen boyutu vermedi "
                    f"({len(pf_hd.lines[0]) if pf_hd.lines else 0}x{len(pf_hd.lines)})"
                )
                failed += 1
                ok_all = False
            else:
                p_ok, p_msg = check_pure_ascii_lines(pf_hd.lines, f"shader:{proc_id}@64x30")
                if not p_ok:
                    print(f"[FAIL] {p_msg}")
                    failed += 1
                    ok_all = False

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
