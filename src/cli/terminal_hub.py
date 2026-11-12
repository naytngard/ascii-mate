"""Interactive Rich Terminal Hub for ASCII Mate — clean menu.py spirit + live portrait preview."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from multiprocessing.connection import Client
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from rich import box
from rich.align import Align
from rich.console import Console, Group
from rich.layout import Layout
from rich.live import Live
from rich.markup import escape
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from src.core.config_manager import get_runtime_signature
from src.core.converter import import_file_to_community
from src.core.library import CATEGORY_ORDER, AnimationLibrary, ThemeLibrary
from src.core.models import AnimationAsset
from src.core.procedural_engine import BaseProceduralRenderer, create_procedural_renderer
from src.gui.tray_manager import PIPE_ADDRESS

try:
    import msvcrt
    WINDOWS = True
except ImportError:
    WINDOWS = False


CATEGORY_SHORT = {
    "Kediler & Evcil Hayvanlar": "Kediler",
    "Ders & Lo-Fi Odak": "Ders & Lo-Fi",
    "Doğa & Hava Durumu": "Doğa",
    "Uzay & Bilim Kurgu": "Uzay & 3B",
    "Retro & Geek": "Retro",
    "Topluluk / Özel Eklenenler": "Topluluk",
}

BANNER_WIDE_SEGMENTS: List[List[Tuple[str, str]]] = [
    [
        ("   \\ ", "bold cyan"), ("o", "bold yellow"), (" /  ", "bold cyan"), ("*", "bold yellow"), ("     ", ""),
        ("   _    ____   ____ ___ ___  ", "bold cyan"),
        (" __  __    _  _____ _____ ", "bold magenta"),
    ],
    [
        ("    \\|/", "bold cyan"), ("  /", "bold yellow"), ("      ", ""),
        ("  / \\  / ___| / ___|_ _|_ _| ", "bold cyan"),
        ("|  \\/  |  / \\|_   _| ____|", "bold magenta"),
    ],
    [
        ("     |  ", "bold cyan"), ("/", "bold yellow"), ("      ", ""),
        (" / _ \\ \\___ \\| |    | | | |  ", "bold blue"),
        ("| |\\/| | / _ \\ | | |  _|  ", "bold bright_magenta"),
    ],
    [
        ("   _/ \\_       ", "bold cyan"),
        ("/ ___ \\ ___) | |___ | | | |  ", "bold blue"),
        ("| |  | |/ ___ \\| | | |___ ", "bold bright_magenta"),
    ],
    [
        ("               ", ""),
        ("/_/   \\_\\____/ \\____|___|___| ", "bold bright_blue"),
        ("|_|  |_/_/   \\_\\_| |_____|", "bold yellow"),
    ],
    [
        ("              ", ""),
        ("ASCII Mate  --  Yuzen Masaustu Arkadasin  *  Saf Klasik ASCII & 3B", "bold white"),
    ],
]

BANNER_COMPACT_SEGMENTS: List[List[Tuple[str, str]]] = [
    [("  \\o/ ", "bold cyan"), ("*", "bold yellow"), ("   ASCII MATE", "bold magenta")],
    [("   |   ", "bold cyan"), ("  Yuzen Masaustu Arkadasin", "bold white")],
    [("  / \\  ", "bold cyan"), ("  Saf Klasik ASCII & Canli 3B", "dim cyan")],
]

NAV_SHORTCUTS: List[Tuple[str, str]] = [
    ("[↑/↓]", "Seç"),
    ("[←/→]", "Kategori"),
    ("[Enter]", "Masaüstüne Koy"),
    ("[/]", "Ara"),
    ("[W]", "Aktifler"),
    ("[I]", "İçe Aktar"),
    ("[R]", "Yenile"),
    ("[Q]", "Çıkış"),
]

DEFAULT_STATUS = "Bir karakter seçip Enter ile masaüstüne bırakın."


def build_banner_text(width: int) -> Tuple[Text, int]:
    """Builds pure classic ASCII stickman + ASCII Mate banner sized cleanly to terminal width."""
    rows = BANNER_WIDE_SEGMENTS if width >= 86 else BANNER_COMPACT_SEGMENTS
    txt = Text()
    for i, segs in enumerate(rows):
        if i > 0:
            txt.append("\n")
        for s_text, s_style in segs:
            txt.append(s_text, style=s_style)
    return txt, len(rows)


def build_footer_panel(term_w: int, active_cnt: int, status_msg: str) -> Tuple[Panel, int]:
    """Builds status + non-clipping wrapped shortcut help bar and returns (panel, exact_height)."""
    inner_w = max(36, term_w - 6)

    # Line 1: Active count + concise status
    status_line = Text()
    status_line.append(f"Aktif Widget: {active_cnt}", style="bold green")
    status_line.append("  •  ", style="dim")
    max_status = max(16, inner_w - len(f"Aktif Widget: {active_cnt}  •  "))
    trimmed_status = status_msg if len(status_msg) <= max_status else (status_msg[: max_status - 3] + "...")
    status_line.append(trimmed_status, style="white")

    # Wrapped shortcut lines (never clipped)
    shortcut_lines: List[Text] = []
    cur_line = Text()
    cur_len = 0
    sep = "  •  "
    for key_lbl, desc_lbl in NAV_SHORTCUTS:
        item_len = len(key_lbl) + 1 + len(desc_lbl)
        needed = item_len if cur_len == 0 else len(sep) + item_len
        if cur_len > 0 and cur_len + needed > inner_w:
            shortcut_lines.append(cur_line)
            cur_line = Text()
            cur_len = 0
        if cur_len > 0:
            cur_line.append(sep, style="dim")
            cur_len += len(sep)
        cur_line.append(key_lbl, style="bold cyan")
        cur_line.append(" ", style="")
        cur_line.append(desc_lbl, style="bright_white")
        cur_len += item_len
    if cur_len > 0:
        shortcut_lines.append(cur_line)

    group = Group(status_line, *[Align.center(ln) for ln in shortcut_lines])
    total_lines = 1 + len(shortcut_lines)
    panel_h = total_lines + 2
    panel = Panel(group, border_style="bright_black", box=box.ROUNDED, padding=(0, 1))
    return panel, panel_h


def is_ipc_available() -> bool:
    """Checks whether the GUI Host IPC named pipe / socket exists without raising exceptions."""
    try:
        return os.path.exists(PIPE_ADDRESS)
    except Exception:
        return False


def send_ipc(payload: dict, timeout: float = 2.0) -> Optional[dict]:
    """Sends a command to the background GUI Host daemon if its IPC pipe exists."""
    if not is_ipc_available():
        return None
    try:
        with Client(PIPE_ADDRESS) as conn:
            conn.send(payload)
            if conn.poll(timeout):
                return conn.recv()
            return {"ok": True}
    except Exception:
        return None


def _spawn_host_process(base_dir: Path) -> None:
    creation_flags = 0
    if os.name == "nt":
        creation_flags = (
            subprocess.DETACHED_PROCESS
            | subprocess.CREATE_NEW_PROCESS_GROUP
            | subprocess.CREATE_NO_WINDOW
        )
    if getattr(sys, "frozen", False):
        subprocess.Popen([sys.executable, "--host"], creationflags=creation_flags)
    else:
        main_py = base_dir / "main.py"
        subprocess.Popen(
            [sys.executable, str(main_py), "--host"],
            cwd=str(base_dir),
            creationflags=creation_flags,
        )


def _shutdown_stale_host_if_needed(base_dir: Path) -> bool:
    """Returns True if an up-to-date GUI Host is already running, else shuts down stale host."""
    ping_res = send_ipc({"cmd": "ping"}, timeout=0.4)
    if ping_res is None:
        return False
    expected_sig = get_runtime_signature(base_dir)
    if ping_res.get("host_sig") == expected_sig:
        return True
    send_ipc({"cmd": "shutdown"}, timeout=0.6)
    deadline = time.monotonic() + 1.5
    while time.monotonic() < deadline:
        if not is_ipc_available():
            break
        time.sleep(0.08)
    return False


def prewarm_gui_host(base_dir: Path) -> None:
    """Silently starts the background GUI Host if not running (or refreshes stale host)."""
    try:
        if is_ipc_available() and _shutdown_stale_host_if_needed(base_dir):
            return
        _spawn_host_process(base_dir)
    except Exception:
        pass


def ensure_gui_host_running(base_dir: Path) -> bool:
    """Starts the PyQt6 Tray/Widget Host daemon in the background if not already running."""
    if _shutdown_stale_host_if_needed(base_dir):
        return True

    _spawn_host_process(base_dir)

    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if send_ipc({"cmd": "ping"}, timeout=0.3) is not None:
            return True
        time.sleep(0.12)
    return False


def spawn_asset_via_host(base_dir: Path, asset_id: str) -> tuple[bool, str]:
    if not ensure_gui_host_running(base_dir):
        return False, "GUI Host başlatılamadı!"
    res = send_ipc({"cmd": "spawn", "asset_id": asset_id})
    if res and res.get("ok"):
        return True, f"Masaüstüne bırakıldı: {res.get('name', asset_id)}"
    return False, (res or {}).get("error", "Bilinmeyen hata")


def _build_rich_multicolor_text(
    lines: List[str],
    colors: Optional[List[List[Optional[Tuple[int, int, int]]]]],
    fallback_style: str,
) -> Text:
    """Builds a Rich Text object with run-batched RGB colors for terminal preview."""
    if not colors:
        return Text("\n".join(lines), style=fallback_style)

    txt = Text()
    for r_idx, line in enumerate(lines):
        if r_idx > 0:
            txt.append("\n")
        c_row = colors[r_idx] if r_idx < len(colors) else []
        c_len = len(c_row)
        n = len(line)
        i = 0
        while i < n:
            col = c_row[i] if i < c_len else None
            j = i + 1
            while j < n:
                ncol = c_row[j] if j < c_len else None
                if ncol != col:
                    break
                j += 1
            seg = line[i:j]
            if col is not None:
                txt.append(seg, style=f"#{col[0]:02x}{col[1]:02x}{col[2]:02x}")
            else:
                txt.append(seg, style=fallback_style)
            i = j
    return txt


class TerminalHub:
    """Interactive Terminal Launcher for ASCII Mate with clean layout & live preview."""

    def __init__(
        self,
        base_dir: Path,
        library: AnimationLibrary,
        theme_lib: ThemeLibrary,
        prewarm: bool = True,
    ) -> None:
        self.base_dir = base_dir
        self.library = library
        self.theme_lib = theme_lib
        self.prewarm = prewarm
        self.console = Console()

        self.categories = list(CATEGORY_ORDER)
        self.cat_idx: int = 0
        self.item_idx: int = 0
        self.search_query: str = ""
        self.status_msg: str = DEFAULT_STATUS
        self._preview_frame: int = 0
        self._last_anim_time: float = time.monotonic()
        self._active_widgets_cache: List[dict] = []
        self._last_ipc_poll: float = 0.0

        self._proc_asset_id: Optional[str] = None
        self._proc_size: Optional[Tuple[int, int]] = None
        self._proc_renderer: Optional[BaseProceduralRenderer] = None

        self._layout: Optional[Layout] = None
        self._cached_layout_key: Optional[Tuple[int, int, int, int]] = None
        self._cached_header_width: Optional[int] = None
        self._cached_header_node: Optional[Group] = None
        self._cached_cats_key: Optional[Tuple[int, str, int]] = None
        self._cached_cats_node: Optional[Align] = None
        self._cached_list_key: Optional[Tuple[int, int, str, int, int]] = None
        self._cached_list_panel: Optional[Panel] = None
        self._cached_footer_key: Optional[Tuple[int, str, int]] = None
        self._cached_footer_panel: Optional[Panel] = None
        self._cached_footer_h: int = 4

    def _current_items(self) -> List[AnimationAsset]:
        if self.search_query:
            return self.library.search(self.search_query)
        cat = self.categories[self.cat_idx]
        return self.library.by_category(cat)

    def _poll_active_widgets(self, force: bool = False) -> bool:
        now = time.monotonic()
        if not force and (now - self._last_ipc_poll < 2.0):
            return False
        self._last_ipc_poll = now
        if not is_ipc_available():
            if self._active_widgets_cache:
                self._active_widgets_cache = []
                return True
            return False
        res = send_ipc({"cmd": "list"}, timeout=0.2)
        if res and res.get("ok"):
            new_widgets = res.get("widgets", [])
            if new_widgets != self._active_widgets_cache:
                self._active_widgets_cache = new_widgets
                return True
        return False

    def _invalidate_panel_caches(self) -> None:
        self._cached_cats_key = None
        self._cached_list_key = None
        self._cached_footer_key = None

    def _ensure_layout(self, term_w: int, term_h: int, footer_h: int) -> Tuple[Layout, int]:
        banner_txt, banner_lines = build_banner_text(term_w)
        header_h = banner_lines + 1  # banner + thin divider rule
        cats_h = 2                   # clean tab row + spacing
        body_h = max(8, term_h - header_h - cats_h - footer_h)

        layout_key = (term_w, term_h, header_h, footer_h)
        if self._layout is None or self._cached_layout_key != layout_key:
            layout = Layout()
            layout.split_column(
                Layout(name="header", size=header_h),
                Layout(name="cats", size=cats_h),
                Layout(name="body", ratio=1),
                Layout(name="footer", size=footer_h),
            )
            layout["body"].split_row(
                Layout(name="list_panel", ratio=5),
                Layout(name="preview_panel", ratio=6),
            )
            self._layout = layout
            self._cached_layout_key = layout_key
            self._cached_header_width = None
            self._cached_list_key = None

        is_wide = 1 if term_w >= 86 else 0
        if self._cached_header_width != is_wide or self._cached_header_node is None:
            self._cached_header_node = Group(
                Align.center(banner_txt),
                Rule(style="dim cyan"),
            )
            self._cached_header_width = is_wide
            self._layout["header"].update(self._cached_header_node)

        return self._layout, body_h

    def _get_preview_renderer(
        self,
        selected: AnimationAsset,
        box_w: int,
        box_h: int,
    ) -> Optional[BaseProceduralRenderer]:
        if not selected.procedural:
            self._proc_asset_id = None
            self._proc_size = None
            self._proc_renderer = None
            return None
        target_h = max(14, min(24, box_h))
        target_w = max(28, min(52, box_w))
        if (
            self._proc_asset_id != selected.id
            or self._proc_size != (target_w, target_h)
            or self._proc_renderer is None
        ):
            self._proc_asset_id = selected.id
            self._proc_size = (target_w, target_h)
            params = dict(selected.procedural_params or {})
            params["width"] = target_w
            params["height"] = target_h
            self._proc_renderer = create_procedural_renderer(selected.procedural, params)
        return self._proc_renderer

    def _preview_fps(self, selected: Optional[AnimationAsset]) -> float:
        if not selected:
            return 0.0
        if selected.procedural:
            return min(16.0, max(6.0, selected.default_fps * 0.5))
        if selected.frame_count > 1:
            return max(1.0, selected.default_fps)
        return 0.0

    def _build_layout(self, dt_anim: float = 0.0) -> Layout:
        items = self._current_items()
        if items:
            self.item_idx = max(0, min(self.item_idx, len(items) - 1))
        else:
            self.item_idx = 0

        selected: Optional[AnimationAsset] = items[self.item_idx] if items else None
        term_w = self.console.size.width
        term_h = self.console.size.height

        # Build / cache Footer first so its dynamic height drives body_h cleanly
        active_cnt = len(self._active_widgets_cache)
        footer_key = (active_cnt, self.status_msg, term_w)
        if self._cached_footer_key != footer_key or self._cached_footer_panel is None:
            self._cached_footer_panel, self._cached_footer_h = build_footer_panel(term_w, active_cnt, self.status_msg)
            self._cached_footer_key = footer_key

        layout, body_h = self._ensure_layout(term_w, term_h, self._cached_footer_h)
        layout["footer"].update(self._cached_footer_panel)

        # Categories strip (clean, no nested border)
        cats_key = (self.cat_idx, self.search_query, term_w)
        if self._cached_cats_key != cats_key or self._cached_cats_node is None:
            if self.search_query:
                cat_txt = Text.from_markup(
                    f"Arama: [bold yellow]{escape(self.search_query)}[/bold yellow]  [dim](Temizlemek için Esc)[/dim]"
                )
            else:
                cat_txt = Text()
                for idx, cat in enumerate(self.categories):
                    if idx > 0:
                        cat_txt.append("   ")
                    short_name = CATEGORY_SHORT.get(cat, cat)
                    label = f"{idx + 1}.{short_name}"
                    if idx == self.cat_idx:
                        cat_txt.append(f" {label} ", style="bold black on cyan")
                    else:
                        cat_txt.append(label, style="dim white")
            self._cached_cats_node = Align.center(cat_txt)
            self._cached_cats_key = cats_key
            layout["cats"].update(self._cached_cats_node)

        # Clean Left Selection List (menu.py spirit: clean numbered items, no table borders)
        list_key = (self.cat_idx, self.item_idx, self.search_query, body_h, len(items))
        if self._cached_list_key != list_key or self._cached_list_panel is None:
            visible_rows = max(4, body_h - 4)
            start = max(0, self.item_idx - visible_rows // 2)
            end = min(len(items), start + visible_rows)
            if end - start < visible_rows:
                start = max(0, end - visible_rows)

            list_lines: List[Text] = []
            left_inner_w = max(24, int(term_w * 0.42) - 4)
            for idx in range(start, end):
                a = items[idx]
                is_sel = idx == self.item_idx
                tag = "[3B]" if a.is_procedural else ""
                num_str = f"[{idx + 1:02d}]"
                avail_name = max(10, left_inner_w - len(num_str) - len(tag) - 6)
                disp_name = a.name if len(a.name) <= avail_name else (a.name[: avail_name - 2] + "..")

                row_txt = Text()
                if is_sel:
                    row_txt.append(f" > {num_str} ", style="bold yellow")
                    row_txt.append(disp_name, style="bold cyan underline")
                    if tag:
                        row_txt.append(f"  {tag}", style="bold green")
                else:
                    row_txt.append(f"   {num_str} ", style="dim cyan")
                    row_txt.append(disp_name, style="white")
                    if tag:
                        row_txt.append(f"  {tag}", style="dim green")
                list_lines.append(row_txt)

            if not items:
                list_lines.append(Text("  Eşleşen karakter bulunamadı.", style="dim"))

            scroll_hint = ""
            if start > 0 or end < len(items):
                up_n = start
                dn_n = len(items) - end
                parts = []
                if up_n > 0:
                    parts.append(f"↑ {up_n}")
                if dn_n > 0:
                    parts.append(f"↓ {dn_n}")
                scroll_hint = f"[dim]{'  |  '.join(parts)}[/dim]"

            list_title = f"{self.categories[self.cat_idx]} ({len(items)})" if not self.search_query else f"Arama Sonuçları ({len(items)})"
            self._cached_list_panel = Panel(
                Group(*list_lines),
                title=f"[bold cyan]{escape(list_title)}[/bold cyan]",
                subtitle=scroll_hint or None,
                border_style="bright_black",
                box=box.ROUNDED,
                padding=(0, 1),
            )
            self._cached_list_key = list_key
            layout["list_panel"].update(self._cached_list_panel)

        # Clean Right Live Portrait Preview Panel (centered & unobstructed)
        if selected:
            theme_info = self.theme_lib.get(selected.recommended_color)
            hex_col = str(theme_info.get("primary", "#FFFFFF")) if not theme_info.get("is_rainbow") else "bright_magenta"
            fallback_style = f"bold {hex_col}"

            art_h = max(4, body_h - 5)
            right_inner_w = max(28, int(term_w * 0.54) - 4)

            proc = self._get_preview_renderer(selected, right_inner_w, art_h)
            if proc is not None:
                pf = proc.step(dt_anim if dt_anim > 0 else 0.08)
                p_lines, p_colors = pf.lines, pf.colors
                mode_info = "[bold green]Canlı 3B Shader[/bold green]"
            else:
                f_idx = self._preview_frame % selected.frame_count
                frame_txt = selected.frames[f_idx]
                p_lines = frame_txt.split("\n")
                p_colors = selected.get_frame_colors(f_idx)
                mode_info = f"[bold cyan]{selected.frame_count} kare • {selected.default_fps:g} FPS[/bold cyan]"

            # Crop cleanly if taller than art_h so bottom metadata never overflows Panel
            if len(p_lines) > art_h:
                top_cut = (len(p_lines) - art_h) // 2
                p_lines = p_lines[top_cut : top_cut + art_h]
                if p_colors is not None:
                    p_colors = p_colors[top_cut : top_cut + art_h]

            art_text = _build_rich_multicolor_text(p_lines, p_colors, fallback_style)
            art_area = Align.center(art_text, vertical="middle", height=art_h)
            info_line1 = Text.from_markup(
                f"[bold white]{escape(selected.name)}[/bold white]   •   {mode_info}"
            )
            info_line2 = Text.from_markup(
                f"[dim]Boyut: {selected.dimensions[0]}x{selected.dimensions[1]}  •  Etiket: {escape(', '.join(selected.tags[:4]))}[/dim]"
            )
            preview_group = Group(
                art_area,
                Rule(style="dim"),
                Align.center(info_line1),
                Align.center(info_line2),
            )
            layout["preview_panel"].update(
                Panel(
                    preview_group,
                    title="[bold magenta]Canlı Portre Önizleme[/bold magenta]",
                    border_style="bright_black",
                    box=box.ROUNDED,
                    padding=(0, 1),
                )
            )
        else:
            layout["preview_panel"].update(
                Panel(
                    Align.center("[dim]Seçili karakter yok.[/dim]", vertical="middle"),
                    title="[bold magenta]Canlı Portre Önizleme[/bold magenta]",
                    border_style="bright_black",
                    box=box.ROUNDED,
                )
            )

        return layout

    def run(self) -> None:
        os.system("")
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        if WINDOWS:
            os.system("title ASCII Mate — Terminal Hub")

        if not self.library.assets:
            self.library.reload()
        self._poll_active_widgets(force=True)

        if self.prewarm:
            prewarm_gui_host(self.base_dir)

        if not WINDOWS:
            self._run_simple_fallback()
            return

        last_size = (self.console.size.width, self.console.size.height)
        dirty = True

        with Live(self._build_layout(0.0), console=self.console, refresh_per_second=16, screen=True) as live:
            while True:
                now = time.monotonic()
                cur_size = (self.console.size.width, self.console.size.height)
                if cur_size != last_size:
                    last_size = cur_size
                    dirty = True

                if self._poll_active_widgets():
                    dirty = True

                items = self._current_items()
                selected = items[self.item_idx] if items and 0 <= self.item_idx < len(items) else None
                fps = self._preview_fps(selected)
                dt_anim = 0.0
                if fps > 0.0:
                    interval = 1.0 / fps
                    elapsed = now - self._last_anim_time
                    if elapsed >= interval:
                        self._last_anim_time = now
                        dt_anim = min(0.25, elapsed)
                        if selected and not selected.procedural and selected.frame_count > 1:
                            self._preview_frame = (self._preview_frame + 1) % selected.frame_count
                        dirty = True

                if msvcrt.kbhit():
                    ch = msvcrt.getwch()
                    dirty = True
                    if ch in ("\x00", "\xe0"):
                        code = msvcrt.getwch()
                        if code == "H":  # Up
                            if items:
                                self.item_idx = (self.item_idx - 1) % len(items)
                                self._preview_frame = 0
                        elif code == "P":  # Down
                            if items:
                                self.item_idx = (self.item_idx + 1) % len(items)
                                self._preview_frame = 0
                        elif code == "K":  # Left
                            self.search_query = ""
                            self.cat_idx = (self.cat_idx - 1) % len(self.categories)
                            self.item_idx = 0
                            self._preview_frame = 0
                        elif code == "M":  # Right
                            self.search_query = ""
                            self.cat_idx = (self.cat_idx + 1) % len(self.categories)
                            self.item_idx = 0
                            self._preview_frame = 0
                    elif ch in ("\r", "\n"):
                        if items:
                            chosen = items[self.item_idx]
                            self.status_msg = f"'{chosen.name}' masaüstüne başlatılıyor..."
                            live.update(self._build_layout(0.0))
                            ok, msg = spawn_asset_via_host(self.base_dir, chosen.id)
                            self.status_msg = msg
                            self._poll_active_widgets(force=True)
                    elif ch in ("1", "2", "3", "4", "5", "6"):
                        self.search_query = ""
                        self.cat_idx = int(ch) - 1
                        self.item_idx = 0
                        self._preview_frame = 0
                    elif ch == "/":
                        live.stop()
                        self._prompt_search()
                        self._invalidate_panel_caches()
                        live.start()
                    elif ch in ("w", "W"):
                        live.stop()
                        self._manage_active_widgets()
                        self._poll_active_widgets(force=True)
                        self._invalidate_panel_caches()
                        live.start()
                    elif ch in ("i", "I"):
                        live.stop()
                        self._import_community_prompt()
                        self._invalidate_panel_caches()
                        live.start()
                    elif ch in ("r", "R"):
                        self.library.reload()
                        send_ipc({"cmd": "reload"}, timeout=0.3)
                        self._invalidate_panel_caches()
                        self.status_msg = f"Kütüphane yenilendi ({len(self.library.assets)} animasyon)."
                    elif ch == "\x1b":  # Esc clears search
                        self.search_query = ""
                        self.item_idx = 0
                    elif ch in ("q", "Q"):
                        break

                if dirty:
                    live.update(self._build_layout(dt_anim))
                    dirty = False

                time.sleep(0.03)

        self.console.clear()
        self.console.print("[bold cyan]ASCII Mate Terminal Hub kapatıldı.[/bold cyan]")
        if self._active_widgets_cache:
            self.console.print("[dim]Not: Açık masaüstü widget'larınız arka planda çalışmaya devam ediyor (Sistem Tepsisinden yönetebilirsiniz).[/dim]")

    def _prompt_search(self) -> None:
        self.console.clear()
        self.console.print("[bold cyan]Karakter Ara[/bold cyan] [dim](ör. satürn, kedi, kahve, kalp, boş bırakırsanız temizlenir)[/dim]")
        q = input("Arama kelimesi: ").strip()
        self.search_query = q
        self.item_idx = 0
        self._preview_frame = 0
        self.status_msg = f"'{q}' için arama sonuçları." if q else "Arama temizlendi."

    def _import_community_prompt(self) -> None:
        self.console.clear()
        self.console.print("[bold magenta]Topluluk Dosyası İçe Aktar (.ascii.json veya ===FRAME=== içeren .txt)[/bold magenta]")
        self.console.print(f"[dim]İpucu: Doğrudan '{self.library.community_dir}' klasörüne dosya atabilir veya açık widget'ın üstüne sürükleyip bırakabilirsiniz.[/dim]\n")
        path_str = input("Dosya yolunu yapıştırın (iptal için Enter): ").strip().strip('"')
        if not path_str:
            return
        asset, msg = import_file_to_community(path_str, self.library.community_dir)
        if asset:
            self.library.reload()
            send_ipc({"cmd": "reload"}, timeout=0.3)
            self.cat_idx = len(self.categories) - 1
            self.search_query = ""
            self.status_msg = msg
        else:
            self.status_msg = f"Hata: {msg}"

    def _manage_active_widgets(self) -> None:
        while True:
            self.console.clear()
            res = send_ipc({"cmd": "list"}, timeout=0.5)
            widgets = res.get("widgets", []) if (res and res.get("ok")) else []
            self.console.print("[bold green]Çalışan Masaüstü Widget Yönetimi[/bold green]\n")
            if not widgets:
                self.console.print("[dim]Şu anda açık masaüstü widget'ı yok.[/dim]\n")
                input("Ana ekrana dönmek için Enter'a basın...")
                return

            t = Table(box=box.ROUNDED, border_style="cyan")
            t.add_column("#", justify="right")
            t.add_column("Karakter")
            t.add_column("Boyut")
            t.add_column("Saydamlık")
            t.add_column("Hayalet Modu")
            for i, w in enumerate(widgets, start=1):
                t.add_row(
                    str(i),
                    w["name"],
                    f"{w['font_size']} pt",
                    f"%{int(round(w['opacity'] * 100))}",
                    "Açık" if w["click_through"] else "Kapalı",
                )
            self.console.print(t)
            self.console.print("\n[cyan]\\[Numara][/cyan] Widget'ı Kapat  |  [cyan]\\[U][/cyan] Tümünde Hayalet Modunu Kapat  |  [cyan]\\[C][/cyan] Hepsini Kapat  |  [cyan]\\[Enter][/cyan] Geri Dön")
            cmd = input("Seçim: ").strip().lower()
            if not cmd:
                return
            elif cmd == "u":
                send_ipc({"cmd": "unghost_all"})
            elif cmd == "c":
                send_ipc({"cmd": "close_all"})
            elif cmd.isdigit():
                idx = int(cmd) - 1
                if 0 <= idx < len(widgets):
                    send_ipc({"cmd": "close", "instance_id": widgets[idx]["instance_id"]})

    def _run_simple_fallback(self) -> None:
        """Simple numbered loop for non-Windows terminals."""
        while True:
            self.console.clear()
            banner_txt, _ = build_banner_text(self.console.size.width)
            self.console.print(banner_txt)
            for idx, cat in enumerate(self.categories, start=1):
                self.console.print(f"[{idx}] {cat}", markup=False)
            choice = input("Kategori seçin (Q çıkış): ").strip().lower()
            if choice == "q":
                break
            if choice.isdigit() and 1 <= int(choice) <= len(self.categories):
                items = self.library.by_category(self.categories[int(choice) - 1])
                for i, a in enumerate(items, start=1):
                    self.console.print(f"  {i}. {a.name}")
                pick = input("Açılacak numara: ").strip()
                if pick.isdigit() and 1 <= int(pick) <= len(items):
                    spawn_asset_via_host(self.base_dir, items[int(pick) - 1].id)
