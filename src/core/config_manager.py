"""Persistent configuration manager for ASCII Study Companion."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from src.core.models import WidgetState


def get_runtime_signature(base_dir: Path) -> str:
    """Computes a lightweight mtime signature for source/frozen executable freshness."""
    if getattr(sys, "frozen", False):
        try:
            st = Path(sys.executable).stat()
            return f"frozen:{st.st_mtime_ns}:{st.st_size}"
        except OSError:
            return "frozen"
    latest = 0
    for sub in ("src/gui", "src/core", "src/cli"):
        folder = base_dir / sub
        if folder.exists():
            for py_file in folder.glob("*.py"):
                try:
                    latest = max(latest, py_file.stat().st_mtime_ns)
                except OSError:
                    pass
    return f"src:{latest}"


DEFAULT_PROFILES: Dict[str, List[Dict[str, Any]]] = {
    "Ders Çalışma Düzeni": [
        {"asset_id": "cat_bust_3d", "color_theme": "auto", "font_size": 12, "opacity": 0.92},
        {"asset_id": "coffee_3d", "color_theme": "auto", "font_size": 12, "opacity": 0.92},
        {"asset_id": "hourglass_3d", "color_theme": "auto", "font_size": 12, "opacity": 0.92, "duration_minutes": 25},
    ],
    "Gece Lo-Fi Düzeni": [
        {"asset_id": "rainy_window_3d", "color_theme": "auto", "font_size": 12, "opacity": 0.90},
        {"asset_id": "vinyl_turntable_3d", "color_theme": "auto", "font_size": 12, "opacity": 0.92},
        {"asset_id": "lantern_3d", "color_theme": "auto", "font_size": 12, "opacity": 0.92},
    ],
    "Odak & Kozmos": [
        {"asset_id": "saturn_3d", "color_theme": "auto", "font_size": 13, "opacity": 0.94},
        {"asset_id": "galaxy_vortex_3d", "color_theme": "auto", "font_size": 12, "opacity": 0.88},
        {"asset_id": "dna_helix_3d", "color_theme": "auto", "font_size": 12, "opacity": 0.92},
    ],
}


class ConfigManager:
    """Handles loading and saving config.json safely."""

    def __init__(self, config_path: Path | str) -> None:
        self.config_path = Path(config_path)
        self._data: Dict[str, Any] = {
            "widgets": {},
            "last_open_widgets": [],
            "favorites": [],
            "profiles": {k: list(v) for k, v in DEFAULT_PROFILES.items()},
            "global": {
                "default_font_size": 16,
                "default_opacity": 0.92,
                "restore_last_session": False,
            },
        }
        self.load()

    def load(self) -> None:
        if not self.config_path.exists():
            self.save()
            return
        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self._data.update(loaded)
                self._data.setdefault("widgets", {})
                self._data.setdefault("last_open_widgets", [])
                self._data.setdefault("favorites", [])
                if not isinstance(self._data.get("profiles"), dict) or not self._data["profiles"]:
                    self._data["profiles"] = {k: list(v) for k, v in DEFAULT_PROFILES.items()}
                self._data.setdefault("global", {})
        except Exception:
            # Keep defaults if corrupted
            pass

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.config_path.with_suffix(".tmp")
        with tmp_path.open("w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        tmp_path.replace(self.config_path)

    def get_widget_state(self, asset_id: str) -> WidgetState:
        raw = self._data.get("widgets", {}).get(asset_id)
        return WidgetState.from_dict(asset_id, raw)

    def save_widget_state(self, state: WidgetState) -> None:
        self._data.setdefault("widgets", {})[state.asset_id] = state.to_dict()
        self.save()

    def get_last_open_widgets(self) -> List[str]:
        return list(self._data.get("last_open_widgets", []))

    def set_last_open_widgets(self, asset_ids: List[str]) -> None:
        self._data["last_open_widgets"] = list(dict.fromkeys(asset_ids))
        self.save()

    def get_favorites(self) -> List[str]:
        return [str(x) for x in self._data.get("favorites", [])]

    def toggle_favorite(self, asset_id: str) -> bool:
        favs = self.get_favorites()
        if asset_id in favs:
            favs = [x for x in favs if x != asset_id]
            added = False
        else:
            favs.append(asset_id)
            added = True
        self._data["favorites"] = favs
        self.save()
        return added

    def get_profiles(self) -> Dict[str, List[Dict[str, Any]]]:
        profs = self._data.get("profiles", {})
        return dict(profs) if isinstance(profs, dict) else {}

    def save_profile(self, name: str, items: List[Dict[str, Any]]) -> None:
        clean = name.strip()
        if not clean:
            return
        self._data.setdefault("profiles", {})[clean] = items
        self.save()

    def delete_profile(self, name: str) -> bool:
        profs = self._data.get("profiles", {})
        if isinstance(profs, dict) and name in profs:
            del profs[name]
            self.save()
            return True
        return False

    def get_global(self, key: str, default: Any = None) -> Any:
        return self._data.get("global", {}).get(key, default)

    def set_global(self, key: str, value: Any) -> None:
        self._data.setdefault("global", {})[key] = value
        self.save()
