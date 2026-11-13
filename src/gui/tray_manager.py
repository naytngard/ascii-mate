"""System tray icon, multi-widget host manager, quick picker, and IPC server."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
import time
import uuid
from multiprocessing.connection import Listener
from pathlib import Path
from typing import Dict, List, Optional

from PyQt6.QtCore import QObject, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QFont, QIcon, QPainter, QPixmap
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
)

from src.core.app_logging import get_logger
from src.core.config_manager import ConfigManager, get_runtime_signature
from src.core.ipc import PIPE_ADDRESS, PIPE_CLI_ADDRESS, connect, get_authkey, pipe_exists
from src.core.library import AnimationLibrary, ThemeLibrary
from src.gui.companion_widget import CompanionWidget
from src.gui.context_menu import DARK_GLASS_MENU_QSS
from src.gui.power import PowerMonitor
from src.gui.settings_dialog import DARK_GLASS_DIALOG_QSS

log = get_logger("tray")


def focus_existing_cli_hub(timeout: float = 0.35) -> bool:
    """Asks an already-running CLI Terminal Hub to bring its console window to front."""
    try:
        if not pipe_exists(PIPE_CLI_ADDRESS):
            return False
        with connect(PIPE_CLI_ADDRESS) as conn:
            conn.send({"cmd": "focus"})
            if conn.poll(timeout):
                res = conn.recv()
                return bool(isinstance(res, dict) and res.get("ok"))
            return True
    except Exception:
        log.debug("CLI hub odağı istenemedi", exc_info=True)
        return False


def create_app_icon(base_dir: Optional[Path] = None) -> QIcon:
    """Loads the bespoke ASCII Mate icon from assets, with a crisp drawn fallback."""
    candidates: List[Path] = []
    if base_dir is not None:
        candidates.extend([base_dir / "assets" / "app_icon.ico", base_dir / "assets" / "app_icon.png"])
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        mp = Path(meipass)
        candidates.extend([mp / "assets" / "app_icon.ico", mp / "assets" / "app_icon.png"])
    proj_assets = Path(__file__).resolve().parents[2] / "assets"
    candidates.extend([proj_assets / "app_icon.ico", proj_assets / "app_icon.png"])

    for cand in candidates:
        if cand.exists():
            icon = QIcon(str(cand))
            if not icon.isNull():
                return icon

    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    painter.setBrush(QColor(15, 23, 42, 245))
    painter.setPen(QColor(56, 189, 248, 220))
    painter.drawRoundedRect(4, 4, 56, 56, 14, 14)

    font = QFont("Consolas", 14, QFont.Weight.Bold)
    painter.setFont(font)
    painter.setPen(QColor(250, 204, 21))
    painter.drawText(pm.rect().adjusted(0, -14, 0, 0), Qt.AlignmentFlag.AlignCenter, "\\o/")
    painter.setPen(QColor(125, 211, 252))
    painter.drawText(pm.rect().adjusted(0, 6, 0, 0), Qt.AlignmentFlag.AlignCenter, "|")
    painter.drawText(pm.rect().adjusted(0, 22, 0, 0), Qt.AlignmentFlag.AlignCenter, "/ \\")
    painter.end()
    return QIcon(pm)


class QuickPickerDialog(QDialog):
    """Lightweight GUI animation picker accessible directly from tray/context menu."""

    def __init__(self, library: AnimationLibrary, on_pick) -> None:
        super().__init__()
        self.library = library
        self.on_pick = on_pick
        self.setWindowTitle("ASCII Mate — Karakter Seç")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.resize(460, 520)
        self.setStyleSheet(DARK_GLASS_DIALOG_QSS)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("✨ Masaüstüne Karakter Ekle")
        title.setObjectName("HeaderTitle")
        layout.addWidget(title)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Ara (ör. kedi, kahve, bulut, uzay)...")
        self.search_edit.textChanged.connect(self._populate)
        layout.addWidget(self.search_edit)

        self.list_widget = QListWidget()
        self.list_widget.setStyleSheet(
            "QListWidget { background: rgba(15, 18, 28, 220); border: 1px solid rgba(148,163,184,70); border-radius: 8px; padding: 4px; color: #E2E8F0; }"
            "QListWidget::item { padding: 6px 8px; border-radius: 4px; }"
            "QListWidget::item:selected { background: rgba(56, 189, 248, 80); color: #FFFFFF; }"
        )
        self.list_widget.itemDoubleClicked.connect(self._launch_selected)
        layout.addWidget(self.list_widget)

        btn_row = QHBoxLayout()
        add_btn = QPushButton("🚀 Masaüstüne Çıkar")
        add_btn.clicked.connect(self._launch_selected)
        refresh_btn = QPushButton("🔄 Yenile")
        refresh_btn.clicked.connect(self._refresh_library)
        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.close)
        btn_row.addWidget(add_btn)
        btn_row.addWidget(refresh_btn)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)

        self._populate("")

    def _populate(self, query: str) -> None:
        self.list_widget.clear()
        for asset in self.library.search(query):
            badge = " [3B]" if asset.is_procedural else (" [HD]" if asset.has_multicolor else "")
            item = QListWidgetItem(f"{asset.name}{badge}  [{asset.category}]")
            item.setData(Qt.ItemDataRole.UserRole, asset.id)
            self.list_widget.addItem(item)

    def _refresh_library(self) -> None:
        self.library.reload()
        self._populate(self.search_edit.text())

    def _launch_selected(self) -> None:
        item = self.list_widget.currentItem()
        if item:
            asset_id = item.data(Qt.ItemDataRole.UserRole)
            self.on_pick(str(asset_id))


class IPCBridge(QObject):
    """Receives commands from CLI Hub via named pipe and relays safely to Qt main thread."""

    command_received = pyqtSignal(dict, object)  # payload, reply_event/container

    def __init__(self) -> None:
        super().__init__()
        self._running = True
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self) -> None:
        # Remove stale Unix socket if present
        if os.name != "nt" and os.path.exists(PIPE_ADDRESS):
            try:
                os.unlink(PIPE_ADDRESS)
            except OSError:
                pass
        try:
            listener = Listener(PIPE_ADDRESS, authkey=get_authkey())
        except Exception:
            # Başka bir host pipe'a sahip olabilir
            log.exception("IPC dinleyicisi başlatılamadı")
            return
        with listener:
            while self._running:
                try:
                    conn = listener.accept()  # yanlış authkey → AuthenticationError (istemci reddedilir)
                except Exception:
                    if not self._running:
                        break
                    log.warning("IPC accept hatası (döngü sürüyor)", exc_info=True)
                    time.sleep(0.1)
                    continue
                try:
                    msg = conn.recv()
                    if not isinstance(msg, dict):
                        raise ValueError("IPC mesajı dict olmalı")
                    done_ev = threading.Event()
                    holder: Dict[str, object] = {"reply": {"ok": True}, "event": done_ev}
                    self.command_received.emit(msg, holder)
                    done_ev.wait(timeout=3.0)
                    conn.send(holder["reply"])
                except Exception as e:
                    log.warning("IPC komutu işlenemedi", exc_info=True)
                    try:
                        conn.send({"ok": False, "error": str(e)})
                    except Exception:
                        pass
                finally:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def stop(self) -> None:
        self._running = False


class WidgetHostManager(QObject):
    """Manages active CompanionWidgets, System Tray icon, and IPC requests."""

    def __init__(
        self,
        app: QApplication,
        base_dir: Path,
        library: AnimationLibrary,
        theme_lib: ThemeLibrary,
        config_mgr: ConfigManager,
        enable_ipc: bool = True,
    ) -> None:
        super().__init__()
        self.app = app
        self.base_dir = base_dir
        self.library = library
        self.theme_lib = theme_lib
        self.config_mgr = config_mgr
        self._runtime_sig = get_runtime_signature(self.base_dir)
        self.widgets: Dict[str, CompanionWidget] = {}
        self._picker: Optional[QuickPickerDialog] = None
        self._hub_proc: Optional[subprocess.Popen] = None
        self._restoring: bool = False

        self.app.setQuitOnLastWindowClosed(False)
        PowerMonitor.instance().battery_saver_enabled = bool(self.config_mgr.get_global("battery_saver", True))
        self.icon = create_app_icon(self.base_dir)
        self.app.setWindowIcon(self.icon)

        self.tray = QSystemTrayIcon(self.icon, self)
        self.tray.setToolTip("ASCII Mate")
        self.tray.activated.connect(self._on_tray_activated)
        self._rebuild_tray_menu()
        self.tray.show()

        self.ipc: Optional[IPCBridge] = None
        if enable_ipc:
            self.ipc = IPCBridge()
            self.ipc.command_received.connect(self._handle_ipc_command)

    def spawn_widget(
        self,
        asset_id: str,
        color_theme: Optional[str] = None,
        overrides: Optional[Dict[str, object]] = None,
    ) -> Optional[CompanionWidget]:
        asset = self.library.get(asset_id)
        if not asset:
            self.library.reload()
            asset = self.library.get(asset_id)
        if not asset:
            return None

        # Aynı animasyonun kopyaları ayrı ayar/konum tutsun: en küçük boş örnek sırası (slot)
        used_slots = {w.slot for w in self.widgets.values() if w.asset.id == asset_id}
        slot = 0
        while slot in used_slots:
            slot += 1
        instance_id = f"{asset_id}_{uuid.uuid4().hex[:6]}"
        callbacks = {
            "spawn_asset": self.spawn_widget,
            "open_hub": self.open_quick_picker,
            "refresh_tray": self._rebuild_tray_menu,
        }
        w = CompanionWidget(
            instance_id=instance_id,
            asset=asset,
            library=self.library,
            theme_lib=self.theme_lib,
            config_mgr=self.config_mgr,
            manager_callbacks=callbacks,
            slot=slot,
        )
        if color_theme:
            w.set_color_theme(color_theme)
        if overrides:
            if "font_size" in overrides:
                w.set_font_size(int(overrides["font_size"]))  # type: ignore[arg-type]
            if "opacity" in overrides:
                w.set_opacity(float(overrides["opacity"]))  # type: ignore[arg-type]
            if "grid_resolution" in overrides:
                w.set_grid_resolution(str(overrides["grid_resolution"]))
            if "duration_minutes" in overrides and int(overrides["duration_minutes"]) > 0:  # type: ignore[arg-type]
                w.set_timer_minutes(int(overrides["duration_minutes"]))  # type: ignore[arg-type]
            if overrides.get("x") is not None and overrides.get("y") is not None:
                w.move(int(overrides["x"]), int(overrides["y"]))  # type: ignore[arg-type]
                w.state.x = int(overrides["x"])  # type: ignore[arg-type]
                w.state.y = int(overrides["y"])  # type: ignore[arg-type]
                w._save_state()

        w.closed.connect(self._on_widget_closed)
        self.widgets[instance_id] = w
        w.show()
        if not self._restoring:
            self._persist_active_list()
        self._rebuild_tray_menu()
        return w

    def restore_last_session_widgets(self) -> int:
        saved_ids = self.config_mgr.get_last_open_widgets()
        if not saved_ids:
            return 0
        self._restoring = True
        restored = 0
        try:
            for aid in saved_ids:
                if self.spawn_widget(aid) is not None:
                    restored += 1
        finally:
            self._restoring = False
            self._persist_active_list()
            self._rebuild_tray_menu()
        return restored

    def load_profile(self, name: str) -> None:
        items = self.config_mgr.get_profiles().get(name)
        if not items:
            return
        self._restoring = True
        try:
            self.close_all_widgets()
            screen = QApplication.primaryScreen()
            avail = screen.availableGeometry() if screen else None
            for idx, entry in enumerate(items):
                aid = str(entry.get("asset_id", ""))
                if not aid:
                    continue
                theme = str(entry.get("color_theme", "auto")) if entry.get("color_theme") else None
                ov = dict(entry)
                w = self.spawn_widget(aid, color_theme=theme, overrides=ov)
                # Stagger nicely across bottom-right / bottom-center / top-right when preset lacks x/y
                if w and (entry.get("x") is None or entry.get("y") is None) and avail is not None:
                    slot = idx % 3
                    if slot == 0:
                        nx = avail.right() - w.width() - 36
                        ny = avail.bottom() - w.height() - 36
                    elif slot == 1:
                        nx = avail.left() + 40
                        ny = avail.bottom() - w.height() - 36
                    else:
                        nx = avail.right() - w.width() - 36
                        ny = avail.top() + 40
                    w.move(max(avail.left(), nx), max(avail.top(), ny))
                    w.state.x = w.x()
                    w.state.y = w.y()
                    w._save_state()
        finally:
            self._restoring = False
            self._persist_active_list()
            self._rebuild_tray_menu()

    def save_current_profile_prompt(self) -> None:
        if not self.widgets:
            QMessageBox.information(None, "Bilgi", "Kaydedilecek açık widget yok.")
            return
        name, ok = QInputDialog.getText(
            None,
            "Masaüstü Düzeni Kaydet",
            "Bu düzen için bir profil adı girin:",
        )
        if not ok or not name.strip():
            return
        items = [
            {
                "asset_id": w.asset.id,
                "x": w.x(),
                "y": w.y(),
                "font_size": w.state.font_size,
                "opacity": w.state.opacity,
                "color_theme": w.state.color_theme,
                "grid_resolution": w.state.grid_resolution,
                "duration_minutes": w.state.duration_minutes,
            }
            for w in self.widgets.values()
        ]
        self.config_mgr.save_profile(name.strip(), items)
        self._rebuild_tray_menu()

    def set_battery_saver(self, enabled: bool) -> None:
        self.config_mgr.set_global("battery_saver", bool(enabled))
        mon = PowerMonitor.instance()
        mon.battery_saver_enabled = bool(enabled)
        mon.changed.emit()  # widget'lar zamanlayıcı aralığını yeniden hesaplasın

    def set_restore_last_session(self, enabled: bool) -> None:
        self.config_mgr.set_global("restore_last_session", bool(enabled))
        self._rebuild_tray_menu()

    def close_widget_by_id(self, instance_id: str) -> bool:
        w = self.widgets.get(instance_id)
        if w:
            w.close_widget()
            return True
        return False

    def disable_all_click_through(self) -> None:
        for w in self.widgets.values():
            if w.state.click_through:
                w.set_click_through(False)
        self._rebuild_tray_menu()

    def close_all_widgets(self) -> None:
        for w in list(self.widgets.values()):
            w.close_widget()

    def open_quick_picker(self) -> None:
        if self._picker is None or not self._picker.isVisible():
            self._picker = QuickPickerDialog(self.library, self.spawn_widget)
        self._picker.show()
        self._picker.raise_()
        self._picker.activateWindow()

    def open_terminal_hub(self) -> None:
        # 1. If a Terminal Hub is already open anywhere, focus its existing console window!
        if focus_existing_cli_hub():
            return
        # 2. Avoid racing multiple consoles while a freshly spawned Terminal Hub is initializing
        if self._hub_proc is not None and self._hub_proc.poll() is None:
            return
        if getattr(sys, "frozen", False):
            cli_exe = Path(sys.executable).with_name("ASCII_Mate_CLI.exe")
            self._hub_proc = subprocess.Popen(
                [str(cli_exe) if cli_exe.exists() else sys.executable],
                creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
            )
        else:
            main_py = self.base_dir / "main.py"
            self._hub_proc = subprocess.Popen(
                [sys.executable, str(main_py)],
                cwd=str(self.base_dir),
                creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
            )

    def _on_widget_closed(self, instance_id: str) -> None:
        self.widgets.pop(instance_id, None)
        if not self._restoring:
            self._persist_active_list()
        self._rebuild_tray_menu()

    def _persist_active_list(self) -> None:
        if not self._restoring:
            self.config_mgr.set_last_open_widgets([w.asset.id for w in self.widgets.values()])

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.open_quick_picker()

    def _rebuild_tray_menu(self) -> None:
        menu = QMenu()
        menu.setStyleSheet(DARK_GLASS_MENU_QSS)

        title = QAction("✨ ASCII Mate", menu)
        title.setEnabled(False)
        menu.addAction(title)
        menu.addSeparator()

        add_act = QAction("➕  Yeni Karakter Aç (Hızlı Seç)...", menu)
        add_act.triggered.connect(self.open_quick_picker)
        menu.addAction(add_act)

        hub_act = QAction("🖥️  Terminal Merkezini (CLI Hub) Aç", menu)
        hub_act.triggered.connect(self.open_terminal_hub)
        menu.addAction(hub_act)

        menu.addSeparator()

        if self.widgets:
            active_hdr = QAction(f"🟢 Çalışan Widget'lar ({len(self.widgets)})", menu)
            active_hdr.setEnabled(False)
            menu.addAction(active_hdr)

            has_ghost = False
            for iid, w in list(self.widgets.items()):
                sub = menu.addMenu(f"  • {w.asset.name}")
                sub.setStyleSheet(DARK_GLASS_MENU_QSS)

                bring_act = QAction("Öne Getir", sub)
                bring_act.triggered.connect(lambda _c, wid=w: (wid.raise_(), wid.activateWindow()))
                sub.addAction(bring_act)

                if w.state.click_through:
                    has_ghost = True
                ghost_act = QAction("👻 Hayalet Modu (Tıklama Geçirgen)", sub, checkable=True)
                ghost_act.setChecked(w.state.click_through)
                ghost_act.triggered.connect(lambda chk, wid=w: wid.set_click_through(chk))
                sub.addAction(ghost_act)

                close_one = QAction("❌ Kapat", sub)
                close_one.triggered.connect(lambda _c, wid=w: wid.close_widget())
                sub.addAction(close_one)

            if has_ghost:
                unghost = QAction("🔓 Tümünde Hayalet Modunu Kapat", menu)
                unghost.triggered.connect(self.disable_all_click_through)
                menu.addAction(unghost)

            close_all_act = QAction("🧹 Tüm Widget'ları Kapat", menu)
            close_all_act.triggered.connect(self.close_all_widgets)
            menu.addAction(close_all_act)
        else:
            empty_act = QAction("⚪ Aktif widget yok", menu)
            empty_act.setEnabled(False)
            menu.addAction(empty_act)

        menu.addSeparator()

        # Scene Profiles Submenu
        prof_menu = menu.addMenu("📌  Masaüstü Düzeni (Profiller)")
        prof_menu.setStyleSheet(DARK_GLASS_MENU_QSS)
        profiles = self.config_mgr.get_profiles()
        for pname, pitems in profiles.items():
            pact = QAction(f"▶  {pname} ({len(pitems)} widget)", prof_menu)
            pact.triggered.connect(lambda _c, pn=pname: self.load_profile(pn))
            prof_menu.addAction(pact)
        prof_menu.addSeparator()
        save_prof_act = QAction("💾  Mevcut Masaüstü Düzenini Kaydet...", prof_menu)
        save_prof_act.triggered.connect(self.save_current_profile_prompt)
        prof_menu.addAction(save_prof_act)

        if profiles:
            del_menu = prof_menu.addMenu("🗑️  Profil Sil")
            del_menu.setStyleSheet(DARK_GLASS_MENU_QSS)
            for pname in profiles:
                dact = QAction(pname, del_menu)
                dact.triggered.connect(
                    lambda _c, pn=pname: (self.config_mgr.delete_profile(pn), self._rebuild_tray_menu())
                )
                del_menu.addAction(dact)

        restore_act = QAction("🔄  Açılışta Son Açık Widget'ları Geri Yükle", menu, checkable=True)
        restore_act.setChecked(bool(self.config_mgr.get_global("restore_last_session", False)))
        restore_act.triggered.connect(lambda checked: self.set_restore_last_session(checked))
        menu.addAction(restore_act)

        batt_act = QAction("🔋  Pildeyken FPS'i Otomatik Düşür", menu, checkable=True)
        batt_act.setChecked(bool(self.config_mgr.get_global("battery_saver", True)))
        batt_act.triggered.connect(self.set_battery_saver)
        menu.addAction(batt_act)

        menu.addSeparator()
        quit_act = QAction("🚪 Uygulamadan Tamamen Çık", menu)
        quit_act.triggered.connect(self.shutdown)
        menu.addAction(quit_act)

        self.tray.setContextMenu(menu)

    def _handle_ipc_command(self, msg: dict, holder: dict) -> None:
        cmd = msg.get("cmd")
        reply = {"ok": True}
        if cmd == "ping":
            reply["active_count"] = len(self.widgets)
            reply["host_sig"] = self._runtime_sig
        elif cmd == "spawn":
            asset_id = str(msg.get("asset_id", ""))
            theme_arg = msg.get("color_theme")
            w = self.spawn_widget(asset_id, color_theme=str(theme_arg) if theme_arg else None)
            if w:
                reply["instance_id"] = w.instance_id
                reply["name"] = w.asset.name
            else:
                reply = {"ok": False, "error": f"Karakter bulunamadı: {asset_id}"}
        elif cmd == "list":
            reply["widgets"] = [
                {
                    "instance_id": iid,
                    "asset_id": w.asset.id,
                    "name": w.asset.name,
                    "click_through": w.state.click_through,
                    "opacity": w.state.opacity,
                    "font_size": w.state.font_size,
                }
                for iid, w in self.widgets.items()
            ]
        elif cmd == "close":
            iid = str(msg.get("instance_id", ""))
            reply["closed"] = self.close_widget_by_id(iid)
        elif cmd == "unghost_all":
            self.disable_all_click_through()
        elif cmd == "close_all":
            self.close_all_widgets()
        elif cmd == "reload":
            self.library.reload()
            reply["count"] = len(self.library.assets)
        elif cmd == "shutdown":
            holder["reply"] = reply
            holder["event"].set()
            self.shutdown()
            return
        else:
            reply = {"ok": False, "error": f"Bilinmeyen komut: {cmd}"}

        holder["reply"] = reply
        holder["event"].set()

    def shutdown(self) -> None:
        self.close_all_widgets()
        if self.ipc:
            self.ipc.stop()
        self.tray.hide()
        self.app.quit()
