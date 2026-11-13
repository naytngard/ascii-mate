"""Data models for ASCII Mate."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _clamp_float(value: Any, lo: float, hi: float, default: Optional[float]) -> Optional[float]:
    """Sayıya çevirir ve [lo, hi] aralığına kırpar; bozuk/NaN/sonsuz değerde default döner."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    if v != v or v in (float("inf"), float("-inf")):
        return default
    return max(lo, min(hi, v))


def _clamp_int(value: Any, lo: int, hi: int, default: int) -> int:
    v = _clamp_float(value, lo, hi, None)
    return default if v is None else int(round(v))


def _parse_blink_patterns(raw: Any) -> List[List[str]]:
    """Animasyon başına göz kırpma kalıpları: [[ara, yerine], ...] (aynı uzunlukta olmalı)."""
    out: List[List[str]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, (list, tuple)) and len(item) == 2 and all(isinstance(s, str) for s in item):
                if item[0] and len(item[0]) == len(item[1]):
                    out.append([item[0], item[1]])
    return out


@dataclass
class ParticleConfig:
    """Configuration for dynamic ASCII particle overlay effects."""

    enabled_by_default: bool = False
    type: str = "none"  # none, snow, rain, steam, hearts, sparks, stars, lightning
    toggle_label: str = "Parçacık Efekti"
    spawn_area: str = "bottom"  # bottom, top, center, around
    density: str = "medium"  # low, medium, high
    chars: List[str] = field(default_factory=lambda: ["*", ".", "'"])

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "ParticleConfig":
        if not data:
            return cls()
        return cls(
            enabled_by_default=bool(data.get("enabled_by_default", False)),
            type=str(data.get("type", "none")),
            toggle_label=str(data.get("toggle_label", "Parçacık Efekti")),
            spawn_area=str(data.get("spawn_area", "bottom")),
            density=str(data.get("density", "medium")),
            chars=[str(c) for c in data.get("chars", ["*", ".", "'"])],
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _parse_color_frames(raw_cf: Any) -> List[List[str]]:
    """Normalizes color_frames from either list[str] (newline-joined) or list[list[str]]."""
    if not isinstance(raw_cf, list):
        return []
    out: List[List[str]] = []
    for item in raw_cf:
        if isinstance(item, str):
            out.append(item.split("\n"))
        elif isinstance(item, list):
            out.append([str(r) for r in item])
    return out


def _hex_to_rgb(hex_str: str) -> Optional[Tuple[int, int, int]]:
    s = hex_str.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6:
        return None
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except ValueError:
        return None


@dataclass
class AnimationAsset:
    """Represents a single .ascii.json animation asset (static HD or live 3D procedural)."""

    id: str
    name: str
    category: str
    author: str = "ASCII Mate"
    tags: List[str] = field(default_factory=list)
    default_fps: float = 4.0
    recommended_color: str = "cream"
    frames: List[str] = field(default_factory=list)
    particles: ParticleConfig = field(default_factory=ParticleConfig)
    schema_version: str = "1.0"
    source_path: Optional[str] = None
    is_community: bool = False
    supports_eye_blink: bool = False
    supports_sleep_zzz: bool = False
    blink_patterns: List[List[str]] = field(default_factory=list)  # [[ara, yerine], ...]
    # v3.0 HD (yüksek çözünürlüklü, karakter başına renkli) varlık: kareler ayrı .ascii.hd dosyasında, tembel yüklenir
    hd: bool = False
    hd_file: Optional[str] = None
    hd_cols: int = 0
    hd_rows: int = 0
    hd_frame_count: int = 0
    bg_mode: str = "transparent"  # transparent | solid
    # v2.0 HD & Procedural 3D support
    procedural: Optional[str] = None
    procedural_params: Dict[str, Any] = field(default_factory=dict)
    palette_map: Dict[str, str] = field(default_factory=dict)
    color_frames: List[List[str]] = field(default_factory=list)
    _rgb_palette_cache: Optional[Dict[str, Tuple[int, int, int]]] = field(default=None, repr=False, compare=False)

    @property
    def frame_count(self) -> int:
        return self.hd_frame_count if self.hd else len(self.frames)

    @property
    def is_hd(self) -> bool:
        return bool(self.hd)

    def hd_path(self) -> Optional[Path]:
        """HD kare dosyasının yolu (meta JSON'un yanında)."""
        if not (self.hd and self.hd_file):
            return None
        base = Path(self.source_path).parent if self.source_path else Path(".")
        return base / self.hd_file

    @property
    def is_procedural(self) -> bool:
        return bool(self.procedural)

    @property
    def has_multicolor(self) -> bool:
        return bool(self.hd or self.procedural or (self.palette_map and self.color_frames))

    def get_rgb_palette(self) -> Dict[str, Tuple[int, int, int]]:
        if self._rgb_palette_cache is None:
            parsed: Dict[str, Tuple[int, int, int]] = {}
            for k, v in self.palette_map.items():
                rgb = _hex_to_rgb(str(v))
                if rgb is not None:
                    parsed[str(k)] = rgb
            self._rgb_palette_cache = parsed
        return self._rgb_palette_cache

    def get_frame_colors(self, frame_idx: int) -> Optional[List[List[Optional[Tuple[int, int, int]]]]]:
        """Resolves per-cell RGB tuples for a static multi-color frame, or None if monochrome."""
        if not self.palette_map or not self.color_frames:
            return None
        pal = self.get_rgb_palette()
        if not pal:
            return None
        rows = self.color_frames[frame_idx % len(self.color_frames)]
        return [[pal.get(ch) for ch in row] for row in rows]

    @property
    def dimensions(self) -> tuple[int, int]:
        """Returns (max_width, max_height) across all frames."""
        if self.hd and self.hd_cols > 0 and self.hd_rows > 0:
            return (self.hd_cols, self.hd_rows)
        if self.procedural and self.procedural_params:
            pw = self.procedural_params.get("width")
            ph = self.procedural_params.get("height")
            if isinstance(pw, int) and isinstance(ph, int) and pw > 0 and ph > 0:
                return (pw, ph)
        if not self.frames:
            return (0, 0)
        max_w = 0
        max_h = 0
        for frame in self.frames:
            lines = frame.split("\n")
            max_h = max(max_h, len(lines))
            for line in lines:
                max_w = max(max_w, len(line))
        return (max_w, max_h)

    @classmethod
    def from_dict(
        cls,
        data: Dict[str, Any],
        source_path: Optional[str] = None,
        is_community: bool = False,
    ) -> "AnimationAsset":
        raw_pal = data.get("palette_map")
        palette_map = {str(k): str(v) for k, v in raw_pal.items()} if isinstance(raw_pal, dict) else {}
        raw_cf = data.get("color_frames")
        color_frames = _parse_color_frames(raw_cf)
        # Backward convenience: support single color_map list/string
        if not color_frames and "color_map" in data:
            cm = data["color_map"]
            if isinstance(cm, str):
                color_frames = [cm.split("\n")]
            elif isinstance(cm, list):
                color_frames = [[str(r) for r in cm]]

        proc = data.get("procedural")
        proc_params = data.get("procedural_params")
        return cls(
            schema_version=str(data.get("schema_version", "1.0")),
            id=str(data["id"]),
            name=str(data["name"]),
            category=str(data.get("category", "Diğer")),
            author=str(data.get("author", "Topluluk")),
            tags=[str(t) for t in data.get("tags", [])],
            default_fps=float(data.get("default_fps", 4.0)),
            recommended_color=str(data.get("recommended_color", "cream")),
            frames=[str(f) for f in data.get("frames", [])],
            particles=ParticleConfig.from_dict(data.get("particles")),
            source_path=source_path,
            is_community=is_community,
            supports_eye_blink=bool(data.get("supports_eye_blink", False)),
            supports_sleep_zzz=bool(data.get("supports_sleep_zzz", False)),
            blink_patterns=_parse_blink_patterns(data.get("blink_patterns")),
            hd=bool(data.get("hd", False)),
            hd_file=str(data["hd_file"]) if data.get("hd_file") else None,
            hd_cols=_clamp_int(data.get("cols"), 0, 600, 0),
            hd_rows=_clamp_int(data.get("rows"), 0, 300, 0),
            hd_frame_count=_clamp_int(data.get("frame_count"), 0, 5000, 0),
            bg_mode=str(data.get("bg_mode", "transparent")) if str(data.get("bg_mode", "transparent")) in ("transparent", "solid") else "transparent",
            procedural=str(proc) if proc else None,
            procedural_params=dict(proc_params) if isinstance(proc_params, dict) else {},
            palette_map=palette_map,
            color_frames=color_frames,
        )

    def to_dict(self) -> Dict[str, Any]:
        d: Dict[str, Any] = {
            "schema_version": self.schema_version,
            "id": self.id,
            "name": self.name,
            "category": self.category,
            "author": self.author,
            "tags": self.tags,
            "default_fps": self.default_fps,
            "recommended_color": self.recommended_color,
            "particles": self.particles.to_dict(),
            "frames": self.frames,
        }
        if self.hd:
            d.update({"hd": True, "hd_file": self.hd_file, "cols": self.hd_cols, "rows": self.hd_rows,
                      "frame_count": self.hd_frame_count, "bg_mode": self.bg_mode})
        if self.procedural:
            d["procedural"] = self.procedural
        if self.procedural_params:
            d["procedural_params"] = self.procedural_params
        if self.palette_map:
            d["palette_map"] = self.palette_map
        if self.color_frames:
            d["color_frames"] = ["\n".join(rows) for rows in self.color_frames]
        return d


@dataclass
class WidgetState:
    """Persistent user preferences for a widget instance."""

    asset_id: str
    x: Optional[int] = None
    y: Optional[int] = None
    font_size: int = 14
    opacity: float = 0.94
    speed_multiplier: float = 1.0
    custom_fps: Optional[float] = None
    color_theme: str = "auto"  # theme key, "auto", or hex like #FF00AA
    glow_enabled: bool = False
    shadow_enabled: bool = True
    line_spacing: float = 0.88  # tight line height multiplier (0.75..1.15)
    particles_enabled: Optional[bool] = None
    particle_density: str = "medium"
    particle_override_type: Optional[str] = None
    flip_horizontal: bool = False
    always_on_top: bool = True
    click_through: bool = False
    duration_minutes: int = 0
    show_timer_below: bool = True
    sleep_zzz_enabled: bool = False
    eye_blink_enabled: bool = False
    # v2.1 3D & interactive features
    grid_resolution: str = "auto"  # auto, compact, standard, hd, ultra
    free_orbit_3d: bool = False
    orbit_yaw: float = 0.0
    orbit_pitch: float = 0.0
    track_cursor: bool = False
    pomodoro_break_enabled: bool = True
    # v2.2 akıllı okunabilirlik (yazıların arkasına geç)
    behind_text_enabled: bool = False
    behind_text_sensitivity: float = 0.5  # 0..1
    behind_text_fade: float = 0.2  # soluk alfa çarpanı 0.08..0.6
    # v3.0 HD kalite
    hd_quality: str = "medium"  # low | medium | high
    hd_fps_cap: Optional[float] = None  # None = kaliteye göre

    @classmethod
    def from_dict(cls, asset_id: str, data: Optional[Dict[str, Any]]) -> "WidgetState":
        if not data or not isinstance(data, dict):
            return cls(asset_id=asset_id)
        theme = str(data.get("color_theme", "auto"))
        if theme == "auto_hd":
            theme = "auto"
        res = str(data.get("grid_resolution", "auto"))
        if res not in ("auto", "compact", "standard", "hd", "ultra"):
            res = "auto"
        x, y = data.get("x"), data.get("y")
        if not (isinstance(x, int) and isinstance(y, int)) or isinstance(x, bool) or isinstance(y, bool):
            x, y = None, None
        return cls(
            asset_id=asset_id,
            x=x,
            y=y,
            font_size=_clamp_int(data.get("font_size"), 6, 48, 14),
            opacity=_clamp_float(data.get("opacity"), 0.15, 1.0, 0.94),
            speed_multiplier=_clamp_float(data.get("speed_multiplier"), 0.1, 5.0, 1.0),
            custom_fps=_clamp_float(data.get("custom_fps"), 0.5, 60.0, None),
            color_theme=theme,
            glow_enabled=bool(data.get("glow_enabled", False)),
            shadow_enabled=bool(data.get("shadow_enabled", True)),
            line_spacing=_clamp_float(data.get("line_spacing"), 0.75, 1.15, 0.88),
            particles_enabled=data.get("particles_enabled"),
            particle_density=str(data.get("particle_density", "medium")),
            particle_override_type=data.get("particle_override_type"),
            flip_horizontal=bool(data.get("flip_horizontal", False)),
            always_on_top=bool(data.get("always_on_top", True)),
            click_through=bool(data.get("click_through", False)),
            duration_minutes=_clamp_int(data.get("duration_minutes"), 0, 24 * 60, 0),
            show_timer_below=bool(data.get("show_timer_below", True)),
            sleep_zzz_enabled=bool(data.get("sleep_zzz_enabled", False)),
            eye_blink_enabled=bool(data.get("eye_blink_enabled", False)),
            grid_resolution=res,
            free_orbit_3d=bool(data.get("free_orbit_3d", False)),
            orbit_yaw=_clamp_float(data.get("orbit_yaw"), -1000.0, 1000.0, 0.0),
            orbit_pitch=_clamp_float(data.get("orbit_pitch"), -1.2, 1.2, 0.0),
            track_cursor=bool(data.get("track_cursor", False)),
            pomodoro_break_enabled=bool(data.get("pomodoro_break_enabled", True)),
            behind_text_enabled=bool(data.get("behind_text_enabled", False)),
            behind_text_sensitivity=_clamp_float(data.get("behind_text_sensitivity"), 0.0, 1.0, 0.5),
            behind_text_fade=_clamp_float(data.get("behind_text_fade"), 0.08, 0.6, 0.2),
            hd_quality=str(data.get("hd_quality")) if str(data.get("hd_quality")) in ("low", "medium", "high") else "medium",
            hd_fps_cap=_clamp_float(data.get("hd_fps_cap"), 1.0, 15.0, None),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
