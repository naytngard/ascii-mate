"""Data models for ASCII Mate."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Tuple


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
    # v2.0 HD & Procedural 3D support
    procedural: Optional[str] = None
    procedural_params: Dict[str, Any] = field(default_factory=dict)
    palette_map: Dict[str, str] = field(default_factory=dict)
    color_frames: List[List[str]] = field(default_factory=list)
    _rgb_palette_cache: Optional[Dict[str, Tuple[int, int, int]]] = field(default=None, repr=False, compare=False)

    @property
    def frame_count(self) -> int:
        return len(self.frames)

    @property
    def is_procedural(self) -> bool:
        return bool(self.procedural)

    @property
    def has_multicolor(self) -> bool:
        return bool(self.procedural or (self.palette_map and self.color_frames))

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
    glow_enabled: bool = True
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

    @classmethod
    def from_dict(cls, asset_id: str, data: Optional[Dict[str, Any]]) -> "WidgetState":
        if not data:
            return cls(asset_id=asset_id)
        ls = float(data.get("line_spacing", 0.88))
        ls = max(0.75, min(1.15, ls))
        theme = str(data.get("color_theme", "auto"))
        if theme == "auto_hd":
            theme = "auto"
        res = str(data.get("grid_resolution", "auto"))
        if res not in ("auto", "compact", "standard", "hd", "ultra"):
            res = "auto"
        return cls(
            asset_id=asset_id,
            x=data.get("x"),
            y=data.get("y"),
            font_size=int(data.get("font_size", 14)),
            opacity=float(data.get("opacity", 0.94)),
            speed_multiplier=float(data.get("speed_multiplier", 1.0)),
            custom_fps=data.get("custom_fps"),
            color_theme=theme,
            glow_enabled=bool(data.get("glow_enabled", True)),
            shadow_enabled=bool(data.get("shadow_enabled", True)),
            line_spacing=ls,
            particles_enabled=data.get("particles_enabled"),
            particle_density=str(data.get("particle_density", "medium")),
            particle_override_type=data.get("particle_override_type"),
            flip_horizontal=bool(data.get("flip_horizontal", False)),
            always_on_top=bool(data.get("always_on_top", True)),
            click_through=bool(data.get("click_through", False)),
            duration_minutes=int(data.get("duration_minutes", 0)),
            show_timer_below=bool(data.get("show_timer_below", True)),
            sleep_zzz_enabled=bool(data.get("sleep_zzz_enabled", False)),
            eye_blink_enabled=bool(data.get("eye_blink_enabled", False)),
            grid_resolution=res,
            free_orbit_3d=bool(data.get("free_orbit_3d", False)),
            orbit_yaw=float(data.get("orbit_yaw", 0.0)),
            orbit_pitch=max(-1.2, min(1.2, float(data.get("orbit_pitch", 0.0)))),
            track_cursor=bool(data.get("track_cursor", False)),
            pomodoro_break_enabled=bool(data.get("pomodoro_break_enabled", True)),
        )

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
