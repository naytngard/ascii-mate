"""Persistent configuration manager for ASCII Study Companion.

Birden çok süreç (Terminal Hub + GUI host) aynı config.json'u yazabildiği için her değişiklik
"kilitle → diskten tazele → uygula → atomik yaz" (read-modify-write) düzeniyle yapılır.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from src.core.app_logging import get_logger
from src.core.models import WidgetState

log = get_logger("config")


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

_LOCK_STALE_SECONDS = 5.0
_SAVE_RETRIES = 6


def widget_state_key(asset_id: str, slot: int = 0) -> str:
    """Aynı animasyonun n. örneği için kalıcı anahtar: slot 0 → 'id', slot 1 → 'id#2', ..."""
    return asset_id if slot <= 0 else f"{asset_id}#{slot + 1}"


class _FileLock:
    """Basit, süreçler arası dosya kilidi (O_EXCL ile oluşturulan .lock dosyası; bayatlayan kilit kırılır)."""

    def __init__(self, path: Path, timeout: float = 3.0) -> None:
        self.path = path
        self.timeout = timeout
        self._fd: Optional[int] = None

    def __enter__(self) -> "_FileLock":
        deadline = time.monotonic() + self.timeout
        while True:
            try:
                self._fd = os.open(str(self.path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                return self
            except FileExistsError:
                try:
                    if time.time() - self.path.stat().st_mtime > _LOCK_STALE_SECONDS:
                        self.path.unlink()
                        continue
                except OSError:
                    pass
            except OSError:
                # Klasör yazılamıyor vb.: kilitsiz devam (veri kaybından kaçınmak için yine de yazmayı dene)
                return self
            if time.monotonic() >= deadline:
                log.warning("config kilidi zaman aşımı; kilitsiz devam ediliyor")
                return self
            time.sleep(0.02)

    def __exit__(self, *exc: object) -> None:
        if self._fd is not None:
            try:
                os.close(self._fd)
            finally:
                self._fd = None
                try:
                    self.path.unlink()
                except OSError:
                    pass


def _default_data() -> Dict[str, Any]:
    return {
        "widgets": {},
        "last_open_widgets": [],
        "favorites": [],
        "profiles": {k: copy.deepcopy(v) for k, v in DEFAULT_PROFILES.items()},
        "global": {
            "default_font_size": 16,
            "default_opacity": 0.92,
            "restore_last_session": False,
        },
    }


class ConfigManager:
    """Handles loading and saving config.json safely (multi-process safe read-modify-write)."""

    def __init__(self, config_path: Path | str) -> None:
        self.config_path = Path(config_path)
        self._lock_path = self.config_path.with_name(self.config_path.name + ".lock")
        self._data: Dict[str, Any] = _default_data()
        self.load()
        if not self.config_path.exists():
            self.save()

    # --- disk I/O ---

    def _read_disk(self) -> Optional[Dict[str, Any]]:
        """Diskten okur. Dosya yoksa None; bozuksa .bak'a taşır ve None döner."""
        if not self.config_path.exists():
            return None
        try:
            with self.config_path.open("r", encoding="utf-8") as f:
                loaded = json.load(f)
            if not isinstance(loaded, dict):
                raise ValueError("kök nesne dict değil")
            return loaded
        except (OSError, ValueError) as exc:
            log.error("config.json okunamadı (%s); .bak olarak saklanıyor", exc)
            self._quarantine_corrupt()
            return None

    def _quarantine_corrupt(self) -> None:
        bak = self.config_path.with_name(self.config_path.name + ".bak")
        try:
            if bak.exists():
                bak.unlink()
            self.config_path.replace(bak)
        except OSError:
            log.exception("bozuk config.json yeniden adlandırılamadı")

    def _merge_loaded(self, loaded: Dict[str, Any]) -> None:
        data = _default_data()
        data.update(loaded)
        if not isinstance(data.get("widgets"), dict):
            data["widgets"] = {}
        if not isinstance(data.get("last_open_widgets"), list):
            data["last_open_widgets"] = []
        if not isinstance(data.get("favorites"), list):
            data["favorites"] = []
        if not isinstance(data.get("profiles"), dict) or not data["profiles"]:
            data["profiles"] = {k: copy.deepcopy(v) for k, v in DEFAULT_PROFILES.items()}
        if not isinstance(data.get("global"), dict):
            data["global"] = {}
        self._data = data

    def load(self) -> None:
        loaded = self._read_disk()
        if loaded is not None:
            self._merge_loaded(loaded)

    def _write_atomic(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self.config_path.with_name(self.config_path.name + f".{os.getpid()}.tmp")
        last_exc: Optional[BaseException] = None
        for attempt in range(_SAVE_RETRIES):
            try:
                with tmp_path.open("w", encoding="utf-8") as f:
                    json.dump(self._data, f, ensure_ascii=False, indent=2)
                tmp_path.replace(self.config_path)
                return
            except OSError as exc:  # PermissionError (OneDrive/antivirüs kilidi) dahil
                last_exc = exc
                time.sleep(0.05 * (attempt + 1))
        log.error("config.json yazılamadı (%d deneme): %s", _SAVE_RETRIES, last_exc)
        try:
            tmp_path.unlink()
        except OSError:
            pass

    def save(self) -> None:
        """Bellekteki durumu diske yazar. Çökmez; başarısızlık loglanır."""
        try:
            with _FileLock(self._lock_path):
                self._write_atomic()
        except Exception:
            log.exception("config kaydedilemedi")

    def _mutate(self, fn: Callable[[Dict[str, Any]], None]) -> None:
        """Kilit altında diskten tazele → değişikliği uygula → yaz. Başka sürecin değişikliklerini ezmez."""
        try:
            with _FileLock(self._lock_path):
                loaded = self._read_disk()
                if loaded is not None:
                    self._merge_loaded(loaded)
                fn(self._data)
                self._write_atomic()
        except Exception:
            log.exception("config güncellenemedi")

    # --- widget state ---

    def get_widget_state(self, asset_id: str, slot: int = 0) -> WidgetState:
        raw = self._data.get("widgets", {}).get(widget_state_key(asset_id, slot))
        return WidgetState.from_dict(asset_id, raw)

    def save_widget_state(self, state: WidgetState, slot: int = 0) -> None:
        key = widget_state_key(state.asset_id, slot)
        snapshot = state.to_dict()

        def apply(d: Dict[str, Any]) -> None:
            d.setdefault("widgets", {})[key] = snapshot

        self._mutate(apply)

    def get_last_open_widgets(self) -> List[str]:
        self.load()
        return [str(x) for x in self._data.get("last_open_widgets", [])]

    def set_last_open_widgets(self, asset_ids: List[str]) -> None:
        ids = list(asset_ids)

        def apply(d: Dict[str, Any]) -> None:
            d["last_open_widgets"] = ids

        self._mutate(apply)

    # --- favorites ---

    def get_favorites(self) -> List[str]:
        self.load()
        return [str(x) for x in self._data.get("favorites", [])]

    def toggle_favorite(self, asset_id: str) -> bool:
        result = {"added": False}

        def apply(d: Dict[str, Any]) -> None:
            favs = [str(x) for x in d.get("favorites", [])]
            if asset_id in favs:
                favs = [x for x in favs if x != asset_id]
                result["added"] = False
            else:
                favs.append(asset_id)
                result["added"] = True
            d["favorites"] = favs

        self._mutate(apply)
        return result["added"]

    # --- profiles ---

    def get_profiles(self) -> Dict[str, List[Dict[str, Any]]]:
        self.load()
        profs = self._data.get("profiles", {})
        return dict(profs) if isinstance(profs, dict) else {}

    def save_profile(self, name: str, items: List[Dict[str, Any]]) -> None:
        clean = name.strip()
        if not clean:
            return

        def apply(d: Dict[str, Any]) -> None:
            d.setdefault("profiles", {})[clean] = items

        self._mutate(apply)

    def delete_profile(self, name: str) -> bool:
        result = {"ok": False}

        def apply(d: Dict[str, Any]) -> None:
            profs = d.get("profiles", {})
            if isinstance(profs, dict) and name in profs:
                del profs[name]
                result["ok"] = True

        self._mutate(apply)
        return result["ok"]

    # --- globals ---

    def get_global(self, key: str, default: Any = None) -> Any:
        return self._data.get("global", {}).get(key, default)

    def set_global(self, key: str, value: Any) -> None:
        def apply(d: Dict[str, Any]) -> None:
            d.setdefault("global", {})[key] = value

        self._mutate(apply)
