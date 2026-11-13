"""Animation library scanner, fast JSON index cache, and theme loader."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.core.models import AnimationAsset


CATEGORY_ORDER = [
    "Kediler & Evcil Hayvanlar",
    "Ders & Lo-Fi Odak",
    "Doğa & Hava Durumu",
    "Uzay & Bilim Kurgu",
    "Retro & Geek",
    "Topluluk / Özel Eklenenler",
]

FOLDER_TO_CATEGORY = {
    "cats_and_pets": "Kediler & Evcil Hayvanlar",
    "study_and_lofi": "Ders & Lo-Fi Odak",
    "nature_and_weather": "Doğa & Hava Durumu",
    "space_and_3d": "Uzay & Bilim Kurgu",
    "retro_and_fun": "Retro & Geek",
    "community": "Topluluk / Özel Eklenenler",
}

INDEX_FORMAT_VERSION = 3


class ThemeLibrary:
    """Loads color presets from assets/themes.json."""

    def __init__(self, themes_path: Path | str) -> None:
        self.themes_path = Path(themes_path)
        self.themes: Dict[str, Dict[str, object]] = {}
        self.load()

    def load(self) -> None:
        if self.themes_path.exists():
            try:
                with self.themes_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                self.themes = data.get("themes", {})
            except Exception:
                self.themes = {}
        if not self.themes:
            self.themes = {
                "white": {"name": "Saf Beyaz", "primary": "#FFFFFF", "secondary": "#E2E8F0", "glow": "#94A3B8", "is_rainbow": False}
            }

    def get(self, key: str) -> Dict[str, object]:
        if key in ("auto", "auto_hd"):
            return self.themes.get(
                "auto_hd",
                {
                    "name": "HD Çok Renkli (Orijinal)",
                    "primary": "#F8FAFC",
                    "secondary": "#38BDF8",
                    "glow": "#7DD3FC",
                    "is_rainbow": False,
                },
            )
        if key.startswith("#") and len(key) in (4, 7):
            return {"name": f"Özel ({key})", "primary": key, "secondary": key, "glow": key, "is_rainbow": False}
        return self.themes.get(key, next(iter(self.themes.values())))


class AnimationLibrary:
    """Scans assets/animations/ using a fast mtime+count index cache and provides categorized access."""

    def __init__(self, animations_dir: Path | str, extra_community_dir: Optional[Path | str] = None) -> None:
        self.animations_dir = Path(animations_dir)
        self.extra_community_dir = Path(extra_community_dir) if extra_community_dir else None
        self.assets: Dict[str, AnimationAsset] = {}
        self.load_errors: List[str] = []
        self.used_index_cache: bool = False
        self.reload()

    @property
    def community_dir(self) -> Path:
        if self.extra_community_dir:
            return self.extra_community_dir
        return self.animations_dir / "community"

    @property
    def index_path(self) -> Path:
        return self.animations_dir.parent / "library_index.json"

    def _scan_dir_files(self, root: Path) -> List[Tuple[Path, str, int, int]]:
        """Returns sorted [(abs_path, rel_posix, mtime_ns, size), ...] using stat only."""
        if not root.exists():
            return []
        entries: List[Tuple[Path, str, int, int]] = []
        for p in sorted(root.rglob("*.ascii.json")):
            try:
                st = p.stat()
                rel = p.relative_to(root).as_posix()
                entries.append((p, rel, int(st.st_mtime_ns), int(st.st_size)))
            except OSError:
                continue
        return entries

    def _try_load_index(self, main_entries: List[Tuple[Path, str, int, int]]) -> Optional[Dict[str, AnimationAsset]]:
        idx_file = self.index_path
        if not idx_file.exists():
            return None
        try:
            with idx_file.open("r", encoding="utf-8") as f:
                cached = json.load(f)
            if not isinstance(cached, dict) or cached.get("version") != INDEX_FORMAT_VERSION:
                return None
            if cached.get("file_count") != len(main_entries):
                return None
            sig = [[rel, mtime, sz] for _, rel, mtime, sz in main_entries]
            if cached.get("signature") != sig:
                return None

            loaded: Dict[str, AnimationAsset] = {}
            for item in cached.get("assets", []):
                rel = item.get("_rel_path", "")
                src_path = str(self.animations_dir / rel) if rel else None
                is_comm = bool(item.get("_is_community", False))
                asset = AnimationAsset.from_dict(item, source_path=src_path, is_community=is_comm)
                loaded[asset.id] = asset
            return loaded
        except Exception:
            return None

    def _write_index(self, main_entries: List[Tuple[Path, str, int, int]], main_records: List[Dict[str, Any]]) -> None:
        idx_file = self.index_path
        try:
            payload = {
                "version": INDEX_FORMAT_VERSION,
                "file_count": len(main_entries),
                "signature": [[rel, mtime, sz] for _, rel, mtime, sz in main_entries],
                "assets": main_records,
            }
            tmp = idx_file.with_suffix(".tmp")
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
            tmp.replace(idx_file)
        except Exception:
            # Read-only bundles (e.g. frozen _MEIPASS) silently skip cache writes
            pass

    def _load_single_file(self, json_file: Path, is_comm: bool) -> Optional[Tuple[AnimationAsset, Dict[str, Any]]]:
        try:
            with json_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            if "category" not in data or not data["category"]:
                folder_name = json_file.parent.name
                data["category"] = FOLDER_TO_CATEGORY.get(folder_name, "Topluluk / Özel Eklenenler")
            if is_comm:
                data["category"] = "Topluluk / Özel Eklenenler"

            asset = AnimationAsset.from_dict(
                data,
                source_path=str(json_file),
                is_community=is_comm,
            )
            return asset, data
        except Exception as exc:
            self.load_errors.append(f"{json_file.name}: {exc}")
            return None

    def reload(self) -> None:
        self.assets.clear()
        self.load_errors.clear()
        self.used_index_cache = False

        main_entries = self._scan_dir_files(self.animations_dir)
        cached_assets = self._try_load_index(main_entries)

        if cached_assets is not None:
            self.assets.update(cached_assets)
            self.used_index_cache = True
        else:
            records: List[Dict[str, Any]] = []
            for p, rel, _mtime, _sz in main_entries:
                is_comm = "community" in p.parts
                res = self._load_single_file(p, is_comm=is_comm)
                if res is not None:
                    asset, raw_data = res
                    self.assets[asset.id] = asset
                    rec = dict(raw_data)
                    rec["_rel_path"] = rel
                    rec["_is_community"] = is_comm
                    records.append(rec)
            if not self.load_errors and main_entries:
                self._write_index(main_entries, records)

        # Scan extra external community dir (used in packaged mode where _MEIPASS != writable_dir)
        if self.extra_community_dir and self.extra_community_dir != (self.animations_dir / "community"):
            for p, _rel, _m, _s in self._scan_dir_files(self.extra_community_dir):
                res = self._load_single_file(p, is_comm=True)
                if res is not None:
                    asset, _ = res
                    self.assets[asset.id] = asset

    def all_assets(self) -> List[AnimationAsset]:
        return list(self.assets.values())

    def get(self, asset_id: str) -> Optional[AnimationAsset]:
        return self.assets.get(asset_id)

    def categories(self) -> List[str]:
        present = {a.category for a in self.assets.values()}
        ordered = [c for c in CATEGORY_ORDER if c in present or c == "Topluluk / Özel Eklenenler"]
        for c in sorted(present):
            if c not in ordered:
                ordered.append(c)
        return ordered

    def by_category(self, category: str) -> List[AnimationAsset]:
        items = [a for a in self.assets.values() if a.category == category]
        return sorted(items, key=lambda a: a.name.lower())

    def search(self, query: str) -> List[AnimationAsset]:
        q = query.strip().lower()
        if not q:
            return sorted(self.assets.values(), key=lambda a: a.name.lower())
        results = []
        for a in self.assets.values():
            haystack = " ".join([a.id, a.name, a.category, a.author, " ".join(a.tags)]).lower()
            if q in haystack:
                results.append(a)
        return sorted(results, key=lambda a: a.name.lower())
