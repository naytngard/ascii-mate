"""Validation suite for the 100+ pure classic ASCII & 3D shader library."""

from __future__ import annotations

import json
import sys
import unicodedata
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


def check_box_alignment(frames: list[str], label: str) -> tuple[bool, str]:
    """Ensure multi-row rectangular ASCII frames don't slip by 1-3 columns or vary frame height/width."""
    dims = set()
    for fi, fr in enumerate(frames):
        lines = fr.split("\n")
        dims.add((len(lines), max((len(ln) for ln in lines), default=0)))
        pipe_rows = []
        for r, ln in enumerate(lines):
            s = ln.rstrip()
            st = s.lstrip()
            if not st:
                continue
            lcol = len(s) - len(st)
            rcol = len(s) - 1
            if (st[0] in "|+" and st[-1] in "|+") or (
                st[0] in ".`'" and st[-1] in ".`'\\/" and ("---" in st or "===" in st or "___" in st)
            ):
                if rcol - lcol >= 10:
                    pipe_rows.append((r, lcol, rcol, st[:3], st[-3:]))
        if len(pipe_rows) >= 2:
            for a, b in zip(pipe_rows, pipe_rows[1:]):
                if b[0] - a[0] <= 2:
                    dl = abs(b[1] - a[1])
                    dr = abs(b[2] - a[2])
                    if (dl == 0 and dr in (1, 2, 3)) or (dr == 0 and dl in (1, 2, 3)):
                        if a[3][0] in "|+." and b[3][0] in "|+'." and a[4][-1] in "|+.'" and b[4][-1] in "|+.'":
                            return False, (
                                f"{label}#frame{fi}: Kutu/kenar hizasi kayik "
                                f"(satir {a[0]} [{a[1]}..{a[2]}] vs satir {b[0]} [{b[1]}..{b[2]}])"
                            )
    if len(dims) > 1:
        return False, f"{label}: Kare boyutlari uyusmuyor: {sorted(dims)}"
    return True, "OK"


def check_no_tabs_wide(frames: list[str], label: str) -> tuple[bool, str]:
    """Sekme karakteri ve geniş (çift hücre) / emoji karakterleri yasak: hizayı bozarlar."""
    for fi, fr in enumerate(frames):
        for r, ln in enumerate(fr.split("\n")):
            if "\t" in ln:
                return False, f"{label}#frame{fi} satır {r}: sekme (TAB) karakteri var"
            for c, ch in enumerate(ln):
                if unicodedata.east_asian_width(ch) in ("W", "F") or ord(ch) > 0x2E80:
                    return False, f"{label}#frame{fi} satır {r} sütun {c}: geniş/emoji karakter {ch!r}"
    return True, "OK"


def check_uniform_geometry(frames: list[str], label: str) -> tuple[bool, str]:
    """Tüm karelerde aynı satır sayısı ve aynı (sağa boşlukla doldurulmuş) satır genişliği."""
    heights = {len(f.split("\n")) for f in frames}
    if len(heights) != 1:
        return False, f"{label}: kare satır sayıları farklı: {sorted(heights)}"
    widths = {len(ln) for f in frames for ln in f.split("\n")}
    if len(widths) != 1:
        return False, f"{label}: satır genişlikleri farklı (sağ kenar boşluk dolgusu eksik): {sorted(widths)}"
    return True, "OK"


def _blank_margins(frame: str) -> tuple[int, int, int]:
    lines = frame.split("\n")
    filled = [i for i, ln in enumerate(lines) if ln.strip()]
    if not filled:
        return len(lines), 0, 0
    top = filled[0]
    bottom = len(lines) - 1 - filled[-1]
    left = min(len(lines[i]) - len(lines[i].lstrip()) for i in filled)
    return top, bottom, left


def check_frame_jump(frames: list[str], label: str, max_row_delta: int = 2, max_col_delta: int = 3) -> tuple[bool, str]:
    """Kareler arası 'zıplama': baştaki/sondaki boş satır ve soldaki boşluk sayıları kareler arasında tutarlı olmalı."""
    if len(frames) < 2:
        return True, "OK"
    margins = [_blank_margins(f) for f in frames]
    tops = [m[0] for m in margins]
    bots = [m[1] for m in margins]
    lefts = [m[2] for m in margins]
    if max(tops) - min(tops) > max_row_delta or max(bots) - min(bots) > max_row_delta:
        return False, f"{label}: kareler arası dikey zıplama (üst boş satır {tops}, alt boş satır {bots})"
    if max(lefts) - min(lefts) > max_col_delta:
        return False, f"{label}: kareler arası yatay zıplama (sol boşluk {lefts})"
    return True, "OK"


def check_hd_asset(json_path: Path, data: dict) -> tuple[bool, str]:
    """HD (3.0): .ascii.hd var, başlık meta ile uyumlu, her kare çözülür, yalnızca ASCII 32..126, renkler geçerli."""
    from src.core.hd_format import HDFormatError, HDReader

    hd_file = json_path.parent / str(data["hd_file"])
    if not hd_file.exists():
        return False, f"HD dosyası yok: {hd_file.name}"
    try:
        rd = HDReader(hd_file)
        if (rd.cols, rd.rows, rd.frame_count) != (data["cols"], data["rows"], data["frame_count"]):
            return False, f"meta ile dosya başlığı uyuşmuyor: {(data['cols'], data['rows'], data['frame_count'])} vs {(rd.cols, rd.rows, rd.frame_count)}"
        for i in range(rd.frame_count):
            ch, co = rd.frame(i)
            if ch.min() < 32 or ch.max() > 126:
                return False, f"kare {i}: ASCII dışı karakter kodu"
            if co.shape != (rd.rows, rd.cols, 3):
                return False, f"kare {i}: renk dizisi boyutu hatalı"
        if rd.frame_count > 1:
            c0, _ = rd.frame(0)
            if not any((rd.frame(i)[0] != c0).any() for i in range(1, rd.frame_count)):
                return False, "çok kareli HD varlıkta tüm kareler aynı"
    except HDFormatError as exc:
        return False, str(exc)
    return True, "OK"


def main() -> int:
    anim_dir = BASE_DIR / "assets" / "animations"
    json_files = sorted(anim_dir.rglob("*.ascii.json"))

    if not json_files:
        print("[FAIL] Hiç .ascii.json dosyası bulunamadı!")
        return 1

    passed = 0
    failed = 0
    hd_count = 0
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

        if data.get("hd"):
            hd_ok, hd_msg = check_hd_asset(path, data)
            if not hd_ok:
                print(f"[FAIL] {rel}: {hd_msg}")
                failed += 1
                continue
            if data["id"] in seen_ids:
                print(f"[FAIL] {rel}: Çakışan ID '{data['id']}' (ilk görülen: {seen_ids[data['id']]})")
                failed += 1
                continue
            seen_ids[data["id"]] = str(rel)
            passed += 1
            hd_count += 1
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
            align_ok, align_msg = check_box_alignment(data["frames"], str(rel))
            if not align_ok:
                print(f"[FAIL] {align_msg}")
                failed += 1
                continue
            static_ok = True
            for chk in (check_no_tabs_wide, check_uniform_geometry, check_frame_jump):
                c_ok, c_msg = chk(data["frames"], str(rel))
                if not c_ok:
                    print(f"[FAIL] {c_msg}")
                    failed += 1
                    static_ok = False
                    break
            if not static_ok:
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
    print(f"HD (3.0) varlıklar      : {hd_count} adet (doğrulandı)")
    print(f"Kütüphane Yüklenen      : {len(lib.assets)}")
    for cat in lib.categories():
        print(f"  • {cat}: {len(lib.by_category(cat))} adet")
    print("-" * 60)
    print(f"SONUÇ: {passed} / {total} PASS")

    for w in lib.warnings:
        print(f"[UYARI] {w}")

    if failed > 0 or passed < 100:
        if passed < 100:
            print(f"[FAIL] En az 100 animasyon bekleniyordu, şu an {passed} adet var.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
