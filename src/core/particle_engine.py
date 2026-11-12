"""2D ASCII grid particle simulator for companion widgets."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import List, Optional, Tuple

from src.core.models import ParticleConfig


@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    char: str
    life: float
    max_life: float
    phase: float


class ParticleEngine:
    """Simulates ASCII particles (snow, rain, steam, hearts, sparks, stars, zzz, lightning) on a 2D character grid."""

    DENSITY_COUNTS = {
        "low": 6,
        "medium": 14,
        "high": 24,
    }

    DEFAULT_CHARS = {
        "snow": ["*", ".", "'", "+"],
        "rain": ["|", "/", "'", "."],
        "steam": ["~", "(", ")", "'", "."],
        "hearts": ["v", "V", "*", "+"],
        "sparks": ["*", "+", ".", "'", "^"],
        "stars": ["*", "+", ".", "'"],
        "zzz": ["z", "Z"],
        "lightning": ["/", "\\", "|", "*"],
    }

    def __init__(self) -> None:
        self.particles: List[Particle] = []
        self._tick: int = 0
        self._lightning_flash_ticks: int = 0

    def clear(self) -> None:
        self.particles.clear()
        self._lightning_flash_ticks = 0

    @staticmethod
    def compute_padding(ptype: str, sleep_zzz: bool = False) -> Tuple[int, int, int, int]:
        """Returns (pad_top, pad_bottom, pad_left, pad_right) matching step()."""
        if ptype == "none" and not sleep_zzz:
            return (0, 0, 0, 0)
        pad_top = 3 if ptype in ("steam", "hearts", "sparks", "stars") or sleep_zzz else 1
        pad_bottom = 5 if ptype in ("snow", "rain", "lightning") else 1
        pad_left = 2
        pad_right = 3 if sleep_zzz else 2
        return (pad_top, pad_bottom, pad_left, pad_right)

    def step(
        self,
        base_lines: List[str],
        config: ParticleConfig,
        override_type: Optional[str] = None,
        density_override: Optional[str] = None,
        sleep_zzz: bool = False,
        dt: float = 0.08,
    ) -> Tuple[List[str], bool]:
        """
        Advances particle physics and composites particles onto a padded ASCII grid.
        Returns (composited_lines, is_lightning_flash).
        """
        self._tick += 1
        ptype = override_type if override_type else config.type
        density = density_override if density_override else config.density
        if not config.enabled_by_default and override_type is None and not sleep_zzz:
            # Caller decides whether enabled; if step is called, we assume enabled unless ptype == 'none'
            pass

        if ptype == "none" and not sleep_zzz:
            return base_lines, False

        base_h = len(base_lines)
        base_w = max((len(l) for l in base_lines), default=1)

        pad_top, pad_bottom, pad_left, pad_right = self.compute_padding(ptype, sleep_zzz)

        total_w = base_w + pad_left + pad_right
        total_h = base_h + pad_top + pad_bottom

        # Build grid with base lines
        grid: List[List[str]] = [[" "] * total_w for _ in range(total_h)]
        occupied = set()
        for r_idx, line in enumerate(base_lines):
            y = pad_top + r_idx
            for c_idx, ch in enumerate(line):
                x = pad_left + c_idx
                if ch != " ":
                    grid[y][x] = ch
                    occupied.add((x, y))

        # Handle lightning flash effect
        is_flash = False
        if ptype == "lightning":
            if self._lightning_flash_ticks > 0:
                self._lightning_flash_ticks -= 1
                is_flash = True
            elif random.random() < 0.025:
                self._lightning_flash_ticks = 3
                is_flash = True
                # Spawn bolt under cloud
                bx = pad_left + random.randint(max(1, base_w // 4), max(2, (3 * base_w) // 4))
                for step_i in range(pad_bottom):
                    by = pad_top + base_h + step_i
                    if 0 <= by < total_h and 0 <= bx < total_w:
                        ch = "*" if step_i == 1 else ("/" if step_i % 2 == 0 else "\\")
                        grid[by][bx] = ch
                        bx = max(0, min(total_w - 1, bx + random.choice([-1, 0, 1])))

        target_count = self.DENSITY_COUNTS.get(density, 14)

        # Spawn primary particles
        if ptype != "none":
            chars = config.chars if config.chars else self.DEFAULT_CHARS.get(ptype, ["*"])
            if override_type and override_type in self.DEFAULT_CHARS:
                chars = self.DEFAULT_CHARS[override_type]

            while len(self.particles) < target_count:
                self.particles.append(
                    self._spawn_particle(
                        ptype=ptype,
                        chars=chars,
                        base_w=base_w,
                        base_h=base_h,
                        pad_left=pad_left,
                        pad_top=pad_top,
                        total_w=total_w,
                        total_h=total_h,
                        spawn_area=config.spawn_area,
                    )
                )

        # Spawn optional Zzz bubbles
        if sleep_zzz and self._tick % 8 == 0 and len(self.particles) < target_count + 4:
            self.particles.append(
                Particle(
                    x=float(pad_left + max(1, base_w - 2)),
                    y=float(pad_top),
                    vx=0.35,
                    vy=-0.55,
                    char=random.choice(["z", "Z"]),
                    life=0.0,
                    max_life=random.uniform(3.0, 5.0),
                    phase=random.uniform(0, 6.28),
                )
            )

        # Update physics
        alive: List[Particle] = []
        for p in self.particles:
            p.life += dt * 4.0
            if ptype == "snow":
                p.x += (p.vx + math.sin(self._tick * 0.25 + p.phase) * 0.25) * dt * 4.0
                p.y += p.vy * dt * 4.0
            elif ptype == "rain" or ptype == "lightning":
                p.x += p.vx * dt * 5.0
                p.y += p.vy * dt * 6.0
            elif ptype in ("steam", "hearts", "sparks"):
                p.x += (p.vx + math.sin(self._tick * 0.3 + p.phase) * 0.22) * dt * 4.0
                p.y += p.vy * dt * 4.0
            else:
                p.x += p.vx * dt * 3.0
                p.y += p.vy * dt * 3.0

            ix, iy = int(round(p.x)), int(round(p.y))
            if p.life < p.max_life and 0 <= ix < total_w and 0 <= iy < total_h:
                alive.append(p)
                # Don't overwrite solid character foreground unless it's stars/hearts/steam rising cleanly
                if (ix, iy) not in occupied:
                    grid[iy][ix] = p.char

        self.particles = alive
        return ["".join(row) for row in grid], is_flash

    def _spawn_particle(
        self,
        ptype: str,
        chars: List[str],
        base_w: int,
        base_h: int,
        pad_left: int,
        pad_top: int,
        total_w: int,
        total_h: int,
        spawn_area: str,
    ) -> Particle:
        ch = random.choice(chars)
        phase = random.uniform(0, 6.28)

        if ptype == "snow":
            x = random.uniform(pad_left, pad_left + max(1, base_w - 1))
            y = float(pad_top + base_h - 1) if spawn_area == "bottom" else random.uniform(0, pad_top + 1)
            return Particle(x=x, y=y, vx=random.uniform(-0.1, 0.1), vy=random.uniform(0.35, 0.7), char=ch, life=0.0, max_life=random.uniform(4.0, 9.0), phase=phase)

        if ptype in ("rain", "lightning"):
            x = random.uniform(pad_left, pad_left + max(1, base_w - 1))
            y = float(pad_top + base_h - 1) if spawn_area == "bottom" else 0.0
            return Particle(x=x, y=y, vx=-0.12, vy=random.uniform(0.9, 1.5), char=ch, life=0.0, max_life=random.uniform(2.5, 5.5), phase=phase)

        if ptype in ("steam", "hearts", "sparks"):
            x = random.uniform(pad_left + 1, max(pad_left + 2, pad_left + base_w - 2))
            y = float(pad_top + random.randint(0, 1))
            return Particle(x=x, y=y, vx=random.uniform(-0.08, 0.08), vy=random.uniform(-0.65, -0.35), char=ch, life=0.0, max_life=random.uniform(2.5, 5.0), phase=phase)

        # stars / around
        x = random.uniform(0, total_w - 1)
        y = random.uniform(0, total_h - 1)
        return Particle(x=x, y=y, vx=0.0, vy=0.0, char=ch, life=0.0, max_life=random.uniform(1.5, 4.0), phase=phase)
