"""Main entrypoint for ASCII Mate (CLI Hub, GUI Host, and Direct --widget mode)."""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

BASE_ROOT = Path(__file__).resolve().parent
if str(BASE_ROOT) not in sys.path:
    sys.path.insert(0, str(BASE_ROOT))

from src.core.app_logging import get_logger, setup_logging
from src.core.config_manager import ConfigManager
from src.core.library import AnimationLibrary, ThemeLibrary

log = get_logger("main")

_HOST_MUTEX_HANDLE = None


def _set_windows_app_id() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("asciimate.companion.app")
    except Exception:
        log.exception("AppUserModelID ayarlanamadı")


def _acquire_host_mutex() -> bool:
    """Returns True if this process is the sole GUI Host instance, False if another host already holds the mutex."""
    global _HOST_MUTEX_HANDLE
    if os.name != "nt":
        return True
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, True, "Local\\ASCII_Mate_Host_Mutex")
        last_err = kernel32.GetLastError()
        if handle and last_err == 183:  # ERROR_ALREADY_EXISTS
            kernel32.CloseHandle(handle)
            return False
        _HOST_MUTEX_HANDLE = handle
        return True
    except Exception:
        log.exception("Host mutex'i alınamadı; tek-örnek denetimi atlanıyor")
        return True


def _release_host_mutex() -> None:
    global _HOST_MUTEX_HANDLE
    if _HOST_MUTEX_HANDLE and os.name == "nt":
        try:
            import ctypes
            ctypes.windll.kernel32.ReleaseMutex(_HOST_MUTEX_HANDLE)
            ctypes.windll.kernel32.CloseHandle(_HOST_MUTEX_HANDLE)
        except Exception:
            log.exception("Host mutex'i bırakılamadı")
        _HOST_MUTEX_HANDLE = None


def resolve_paths() -> tuple[Path, Path]:
    """
    Returns (resource_dir, writable_dir).
    When run from source, both point to ascii_mate/.
    When packaged with PyInstaller, resource_dir points to _MEIPASS (if present) or exe dir,
    and writable_dir points to exe dir so config.json & community/ remain portable.
    """
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        meipass = Path(getattr(sys, "_MEIPASS", exe_dir))
        return meipass, exe_dir
    base = Path(__file__).resolve().parent
    return base, base


def run_host(initial_widget_id: str | None = None, initial_theme: str | None = None) -> int:
    _set_windows_app_id()
    # Eski (bayat) host kapanırken mutex'i hemen bırakmayabilir: kısa bekle-ve-tekrar dene (~4 sn).
    acquired = False
    for _attempt in range(30 if initial_widget_id else 1):
        if _acquire_host_mutex():
            acquired = True
            break
        time.sleep(0.13)
    if not acquired:
        if initial_widget_id:
            # Güncel bir host gerçekten çalışıyor: widget'ı ona yaptır.
            from src.cli.terminal_hub import send_ipc
            payload = {"cmd": "spawn", "asset_id": initial_widget_id}
            if initial_theme:
                payload["color_theme"] = initial_theme
            res = send_ipc(payload, timeout=1.0)
            return 0 if res and res.get("ok") else 1
        return 0

    from PyQt6.QtWidgets import QApplication
    from src.gui.tray_manager import WidgetHostManager

    res_dir, write_dir = resolve_paths()
    anim_dir = res_dir / "assets" / "animations"
    comm_dir = write_dir / "assets" / "animations" / "community"
    themes_path = res_dir / "assets" / "themes.json"
    config_path = write_dir / "config.json"

    comm_dir.mkdir(parents=True, exist_ok=True)

    library = AnimationLibrary(anim_dir, extra_community_dir=comm_dir)
    theme_lib = ThemeLibrary(themes_path)
    config_mgr = ConfigManager(config_path)

    app = QApplication(sys.argv)
    manager = WidgetHostManager(
        app=app,
        base_dir=write_dir,
        library=library,
        theme_lib=theme_lib,
        config_mgr=config_mgr,
        enable_ipc=True,
    )

    if initial_widget_id:
        w = manager.spawn_widget(initial_widget_id, color_theme=initial_theme)
        if not w:
            print(f"[HATA] '{initial_widget_id}' ID'li animasyon bulunamadı.")
    elif config_mgr.get_global("restore_last_session", False):
        manager.restore_last_session_widgets()
    try:
        return app.exec()
    finally:
        _release_host_mutex()


def run_cli(prewarm: bool = True) -> int:
    _set_windows_app_id()
    from src.gui.tray_manager import focus_existing_cli_hub

    if focus_existing_cli_hub(timeout=0.35):
        return 0

    from src.cli.terminal_hub import TerminalHub

    res_dir, write_dir = resolve_paths()
    anim_dir = res_dir / "assets" / "animations"
    comm_dir = write_dir / "assets" / "animations" / "community"
    themes_path = res_dir / "assets" / "themes.json"
    comm_dir.mkdir(parents=True, exist_ok=True)

    library = AnimationLibrary(anim_dir, extra_community_dir=comm_dir)
    theme_lib = ThemeLibrary(themes_path)
    hub = TerminalHub(base_dir=write_dir, library=library, theme_lib=theme_lib, prewarm=prewarm)
    hub.run()
    return 0


def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description="ASCII Mate")
    parser.add_argument("--host", action="store_true", help="Arka plan PyQt6 widget ve tepsi sunucusunu başlatır.")
    parser.add_argument("--widget", type=str, default=None, help="Doğrudan belirtilen ID'li widget'ı masaüstünde açar.")
    parser.add_argument("--theme", type=str, default=None, help="--widget ile açılırken uygulanacak renk teması.")
    parser.add_argument("--no-prewarm", action="store_true", help="Terminal Hub açılırken GUI host ön-ısıtmasını devre dışı bırakır.")
    args = parser.parse_args()

    # Paketli GUI exe (konsolsuz) argümansız açılınca tepsi host'unu başlatır; Terminal Hub ASCII_Mate_CLI.exe'dedir.
    if (
        getattr(sys, "frozen", False)
        and not args.widget
        and not args.host
        and not Path(sys.executable).stem.lower().endswith("_cli")
    ):
        return run_host()

    if args.host:
        return run_host()

    if args.widget:
        from src.cli.terminal_hub import _shutdown_stale_host_if_needed, send_ipc

        _, write_dir = resolve_paths()
        if _shutdown_stale_host_if_needed(write_dir):
            payload = {"cmd": "spawn", "asset_id": args.widget}
            if args.theme:
                payload["color_theme"] = args.theme
            res = send_ipc(payload, timeout=0.6)
            if res and res.get("ok"):
                return 0
        return run_host(initial_widget_id=args.widget, initial_theme=args.theme)

    return run_cli(prewarm=not args.no_prewarm)


if __name__ == "__main__":
    sys.exit(main())
