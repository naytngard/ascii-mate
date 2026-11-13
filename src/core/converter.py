"""Converter and normalizer for .txt and .ascii.json community animations."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.models import AnimationAsset


def normalize_frames(frames: List[str]) -> List[str]:
    """Pads all frames to identical row count and line width so widgets never jitter."""
    if not frames:
        return [""]

    split_frames = [f.replace("\r\n", "\n").replace("\r", "\n").split("\n") for f in frames]

    max_h = max(len(lines) for lines in split_frames)
    max_w = max((len(line) for lines in split_frames for line in lines), default=1)
    max_w = max(1, max_w)

    normalized: List[str] = []
    for lines in split_frames:
        padded_lines = [line.ljust(max_w) for line in lines]
        while len(padded_lines) < max_h:
            padded_lines.append(" " * max_w)
        normalized.append("\n".join(padded_lines))
    return normalized


def _trim_common_blank_margins(raw_frames: List[str]) -> List[str]:
    """Kareler arası ORTAK üst/alt boşluğu korur: yalnızca tüm karelerde boş olan baştaki/sondaki satırları atar.
    (Her kareyi ayrı kırpmak, kare başına farklı boşluk yüzünden animasyonun kaymasına yol açar.)
    """
    frames = [rf.split("\n") for rf in raw_frames]
    frames = [f for f in frames if any(l.strip() for l in f)]
    if not frames:
        return []
    top = min(next(i for i, l in enumerate(f) if l.strip()) for f in frames)
    bottom = min(next(i for i, l in enumerate(reversed(f)) if l.strip()) for f in frames)
    return ["\n".join(f[top: len(f) - bottom]) for f in frames]


def slugify(text: str) -> str:
    tr_map = str.maketrans("çğıöşüÇĞİÖŞÜ ", "cgiosucgiosu_")
    clean = text.translate(tr_map).lower()
    clean = re.sub(r"[^a-z0-9_]+", "_", clean).strip("_")
    return clean or "custom_ascii"


def txt_to_ascii_json(
    txt_content: str,
    name: str = "Özel ASCII",
    author: str = "Topluluk",
    category: str = "Topluluk / Özel Eklenenler",
    default_fps: float = 4.0,
    recommended_color: str = "cream",
    particle_type: str = "none",
) -> Dict[str, Any]:
    """Converts plain text ASCII (separated by ===FRAME=== or similar) to .ascii.json dict."""
    text = txt_content.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"\A(?:[ \t]*\n)+", "", text)  # dosya başındaki boş satırlar biçimlendirmedir, kareye ait değil

    sep_match = re.search(r"^(?:===FRAME===|---FRAME---|###FRAME###)\s*$", text, re.MULTILINE)
    if sep_match:
        raw_frames = re.split(r"^(?:===FRAME===|---FRAME---|###FRAME###)\s*$", text, flags=re.MULTILINE)
        # Ayırıcı satırının kendi satır sonu bir sonraki kareye boş satır olarak sızmasın
        raw_frames = [rf[1:] if i > 0 and rf.startswith("\n") else rf for i, rf in enumerate(raw_frames)]
    else:
        if "\n\n\n" in text:
            raw_frames = text.split("\n\n\n")
        else:
            raw_frames = [text]

    cleaned_frames = _trim_common_blank_margins(raw_frames)

    if not cleaned_frames:
        cleaned_frames = ["(Boş ASCII)"]

    norm_frames = normalize_frames(cleaned_frames)
    asset_id = slugify(name)

    return {
        "schema_version": "1.0",
        "id": asset_id,
        "name": name,
        "category": category,
        "author": author,
        "tags": ["özel", "topluluk", "txt"],
        "default_fps": float(default_fps),
        "recommended_color": recommended_color,
        "particles": {
            "enabled_by_default": particle_type != "none",
            "type": particle_type,
            "toggle_label": "Parçacık Efekti",
            "spawn_area": "bottom",
            "density": "medium",
            "chars": ["*", ".", "+"],
        },
        "frames": norm_frames,
    }


def validate_hd_meta(data: Dict[str, Any]) -> Tuple[bool, str]:
    """HD (schema 3.0) üst verisi: kareler ayrı `.ascii.hd` dosyasındadır, burada yalnızca bildirim doğrulanır."""
    for req in ("id", "name", "hd_file", "cols", "rows", "frame_count"):
        if req not in data:
            return False, f"HD zorunlu alan eksik: '{req}'"
    if str(data.get("schema_version")) != "3.0":
        return False, "HD varlıklar schema_version '3.0' olmalıdır."
    if not isinstance(data["id"], str) or not data["id"].strip() or not isinstance(data["name"], str) or not data["name"].strip():
        return False, "'id' ve 'name' boş olmayan metin olmalıdır."
    hf = data["hd_file"]
    if not isinstance(hf, str) or not hf.endswith(".ascii.hd") or "/" in hf or "\\" in hf or ".." in hf:
        return False, "'hd_file' yalnızca aynı klasördeki bir '*.ascii.hd' dosya adı olabilir."
    for k, hi in (("cols", 600), ("rows", 300), ("frame_count", 5000)):
        v = data[k]
        if isinstance(v, bool) or not isinstance(v, int) or not (1 <= v <= hi):
            return False, f"'{k}' 1..{hi} aralığında tam sayı olmalıdır."
    try:
        fps = float(data.get("default_fps", 10.0))
    except (TypeError, ValueError):
        return False, "'default_fps' sayı olmalıdır."
    if not (0.1 <= fps <= 30.0):
        return False, "'default_fps' 0.1..30 aralığında olmalıdır."
    if data.get("bg_mode", "transparent") not in ("transparent", "solid"):
        return False, "'bg_mode' 'transparent' veya 'solid' olmalıdır."
    return True, "OK"


def validate_ascii_json_dict(data: Any) -> Tuple[bool, str]:
    """Validates schema and alignment of a parsed .ascii.json payload (v1.0 & v2.0 HD)."""
    if not isinstance(data, dict):
        return False, "JSON kök nesnesi dict olmalıdır."

    if data.get("hd"):
        return validate_hd_meta(data)

    for req in ("id", "name", "frames"):
        if req not in data:
            return False, f"Zorunlu alan eksik: '{req}'"

    if not isinstance(data["id"], str) or not data["id"].strip():
        return False, "'id' boş olmayan bir metin olmalıdır."

    if not isinstance(data["name"], str) or not data["name"].strip():
        return False, "'name' boş olmayan bir metin olmalıdır."

    frames = data["frames"]
    if not isinstance(frames, list) or len(frames) == 0:
        return False, "'frames' en az 1 kare içeren bir liste olmalıdır."

    if not all(isinstance(f, str) and len(f) > 0 for f in frames):
        return False, "Tüm kareler boş olmayan string olmalıdır."

    heights = [len(f.split("\n")) for f in frames]
    if len(set(heights)) != 1:
        return False, f"Karelerin satır sayıları tutarsız: {heights}"

    widths = [len(line) for f in frames for line in f.split("\n")]
    if len(set(widths)) != 1:
        return False, f"Karelerin satır genişlikleri tutarsız (pad edilmemiş): {min(widths)}..{max(widths)}"

    frame_h = heights[0]
    frame_w = widths[0]

    if "palette_map" in data and data["palette_map"] is not None:
        if not isinstance(data["palette_map"], dict):
            return False, "'palette_map' dict olmalıdır."
        for k, v in data["palette_map"].items():
            if not isinstance(k, str) or len(k) != 1 or not isinstance(v, str):
                return False, f"'palette_map' geçersiz anahtar/renk çifti: {k!r}: {v!r}"

    if "color_frames" in data and data["color_frames"] is not None:
        cf = data["color_frames"]
        if not isinstance(cf, list) or len(cf) == 0:
            return False, "'color_frames' boş olmayan bir liste olmalıdır."
        if len(cf) not in (1, len(frames)):
            return False, f"'color_frames' uzunluğu ({len(cf)}) 1 veya frames ({len(frames)}) ile eşit olmalıdır."
        for idx, cframe in enumerate(cf):
            rows = cframe.split("\n") if isinstance(cframe, str) else cframe
            if not isinstance(rows, list) or len(rows) != frame_h:
                return False, f"color_frames[{idx}] satır sayısı frames ile uyuşmuyor."
            for r in rows:
                if not isinstance(r, str) or len(r) != frame_w:
                    return False, f"color_frames[{idx}] satır genişliği frames ({frame_w}) ile uyuşmuyor."

    return True, "OK"


def import_file_to_community(
    src_path: Path | str,
    community_dir: Path | str,
) -> Tuple[Optional[AnimationAsset], str]:
    """Imports a .ascii.json or .txt file into community_dir, returning (AnimationAsset, status_message)."""
    src = Path(src_path)
    dest_dir = Path(community_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)

    if not src.exists():
        return None, f"Dosya bulunamadı: {src}"

    try:
        raw_text = src.read_text(encoding="utf-8")
    except Exception as e:
        return None, f"Dosya okunamadı: {e}"

    if src.suffix.lower() == ".txt":
        stem_name = src.stem.replace("_", " ").replace("-", " ").title()
        data = txt_to_ascii_json(raw_text, name=stem_name)
    else:
        try:
            data = json.loads(raw_text)
        except Exception as e:
            return None, f"Geçersiz JSON formatı: {e}"
        if isinstance(data, dict) and data.get("hd"):
            return None, "HD varlıklar iki dosyadır (.ascii.json + .ascii.hd): ikisini birlikte assets/animations/community/ klasörüne kopyalayın."
        if isinstance(data, dict) and isinstance(data.get("frames"), list) and data["frames"]:
            data["frames"] = normalize_frames([str(f) for f in data["frames"]])
            data.setdefault("schema_version", "1.0")
            data.setdefault("category", "Topluluk / Özel Eklenenler")

    ok, msg = validate_ascii_json_dict(data)
    if not ok:
        return None, f"Doğrulama hatası: {msg}"

    out_name = f"{slugify(data['id'])}.ascii.json"
    out_path = dest_dir / out_name
    with out_path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    asset = AnimationAsset.from_dict(data, source_path=str(out_path), is_community=True)
    return asset, f"Başarıyla eklendi: {asset.name} ({out_path.name})"
