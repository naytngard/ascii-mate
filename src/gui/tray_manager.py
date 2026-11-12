"""System tray icon, multi-widget host manager, quick picker, and IPC server."""

from __future__ import annotations

import os
import subprocess
import sys
import threading
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
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QSystemTrayIcon,
    QVBoxLayout,
)

from src.core.config_manager import ConfigManager, get_runtime_signature
from src.core.library import AnimationLibrary, ThemeLibrary
from src.gui.companion_widget import CompanionWidget
from src.gui.context_menu import DARK_GLASS_MENU_QSS
from src.gui.settings_dialog import DARK_GLASS_DIALOG_QSS

PIPE_ADDRESS = r"\\.\pipe\ascii_mate_ipc" if os.name == "nt" else "/tmp/ascii_mate_ipc.sock"


def create_app_icon() -> QIcon:
    """Generates a crisp, self-contained glowing stickman badge icon without external .ico files."""
    pm = QPixmap(64, 64)
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    painter.setBrush(QColor(18, 22, 34, 245))
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
            with Listener(PIPE_ADDRESS) as listener:
                while self._running:
                    try:
                        conn = listener.accept()
                    except Exception:
                        break
                    try:
                        msg = conn.recv()
                        done_ev = threading.Event()
                        holder: Dict[str, object] = {"reply": {"ok": True}, "event": done_ev}
                        self.command_received.emit(msg, holder)
                        done_ev.wait(timeout=3.0)
                        conn.send(holder["reply"])
                    except Exception as e:
                        try:
                            conn.send({"ok": False, "error": str(e)})
                        except Exception:
                            pass
                    finally:
                        conn.close()
        except Exception:
            # Another host may already own the pipe
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

        self.app.setQuitOnLastWindowClosed(False)
        self.icon = create_app_icon()
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

    def spawn_widget(self, asset_id: str) -> Optional[CompanionWidget]:
        asset = self.library.get(asset_id)
        if not asset:
            self.library.reload()
            asset = self.library.get(asset_id)
        if not asset:
            return None

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
        )
        w.closed.connect(self._on_widget_closed)
        self.widgets[instance_id] = w
        w.show()
        self._persist_active_list()
        self._rebuild_tray_menu()
        return w

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
        if getattr(sys, "frozen", False):
            subprocess.Popen([sys.executable], creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0)
        else:
            main_py = self.base_dir / "main.py"
            subprocess.Popen(
                [sys.executable, str(main_py)],
                cwd=str(self.base_dir),
                creationflags=subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0,
            )

    def _on_widget_closed(self, instance_id: str) -> None:
        self.widgets.pop(instance_id, None)
        self._persist_active_list()
        self._rebuild_tray_menu()

    def _persist_active_list(self) -> None:
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
            w = self.spawn_widget(asset_id)
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
