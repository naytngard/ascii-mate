"""Dark-glass fine-tuning settings dialog for a CompanionWidget."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
)

if TYPE_CHECKING:
    from src.gui.companion_widget import CompanionWidget


DARK_GLASS_DIALOG_QSS = """
QDialog {
    background-color: rgba(20, 22, 32, 245);
    color: #E2E8F0;
    border: 1px solid rgba(148, 163, 184, 70);
    border-radius: 12px;
    font-family: 'Segoe UI', sans-serif;
}
QLabel {
    color: #CBD5E1;
    font-size: 12px;
}
QLabel#HeaderTitle {
    color: #F8FAFC;
    font-size: 15px;
    font-weight: bold;
}
QSlider::groove:horizontal {
    height: 6px;
    background: rgba(255, 255, 255, 28);
    border-radius: 3px;
}
QSlider::handle:horizontal {
    background: #38BDF8;
    width: 14px;
    height: 14px;
    margin: -4px 0;
    border-radius: 7px;
}
QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {
    background-color: rgba(30, 34, 48, 230);
    color: #F8FAFC;
    border: 1px solid rgba(148, 163, 184, 75);
    border-radius: 6px;
    padding: 4px 8px;
}
QPushButton {
    background-color: rgba(56, 189, 248, 40);
    color: #E0F2FE;
    border: 1px solid rgba(56, 189, 248, 120);
    border-radius: 6px;
    padding: 6px 12px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: rgba(56, 189, 248, 85);
}
QCheckBox {
    color: #E2E8F0;
    spacing: 8px;
}
QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid rgba(148, 163, 184, 100);
    background: rgba(30, 34, 48, 220);
}
QCheckBox::indicator:checked {
    background: #38BDF8;
    border-color: #38BDF8;
}
"""


class SettingsDialog(QDialog):
    """Live fine-tuning settings dialog for a floating ASCII companion."""

    def __init__(self, widget: "CompanionWidget") -> None:
        super().__init__(widget)
        self.widget = widget
        self.setWindowTitle(f"Ayarlar — {widget.asset.name}")
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        self.setMinimumWidth(370)
        self.setStyleSheet(DARK_GLASS_DIALOG_QSS)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(12)

        title = QLabel(f"✨ {self.widget.asset.name} — İnce Ayarlar")
        title.setObjectName("HeaderTitle")
        root.addWidget(title)

        form = QFormLayout()
        form.setSpacing(10)

        # Opacity Slider (15% - 100%)
        opacity_row = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Orientation.Horizontal)
        self.opacity_slider.setRange(15, 100)
        self.opacity_slider.setValue(int(round(self.widget.state.opacity * 100)))
        self.opacity_lbl = QLabel(f"%{self.opacity_slider.value()}")
        self.opacity_lbl.setMinimumWidth(38)
        self.opacity_slider.valueChanged.connect(self._on_opacity_changed)
        opacity_row.addWidget(self.opacity_slider)
        opacity_row.addWidget(self.opacity_lbl)
        form.addRow("💧 Saydamlık:", opacity_row)

        # Font Size Slider (8 - 42)
        size_row = QHBoxLayout()
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(8, 42)
        self.size_slider.setValue(self.widget.state.font_size)
        self.size_lbl = QLabel(f"{self.size_slider.value()} pt")
        self.size_lbl.setMinimumWidth(38)
        self.size_slider.valueChanged.connect(self._on_size_changed)
        size_row.addWidget(self.size_slider)
        size_row.addWidget(self.size_lbl)
        form.addRow("🔍 Boyut:", size_row)

        # Line Spacing Slider (0.75x - 1.15x -> 75..115)
        ls_row = QHBoxLayout()
        self.ls_slider = QSlider(Qt.Orientation.Horizontal)
        self.ls_slider.setRange(75, 115)
        self.ls_slider.setValue(int(round(self.widget.state.line_spacing * 100)))
        self.ls_lbl = QLabel(f"{self.widget.state.line_spacing:.2f}x")
        self.ls_lbl.setMinimumWidth(42)
        self.ls_slider.valueChanged.connect(self._on_ls_changed)
        ls_row.addWidget(self.ls_slider)
        ls_row.addWidget(self.ls_lbl)
        form.addRow("📐 Satır Sıkılığı:", ls_row)

        # Speed Multiplier Slider (0.25x - 3.00x -> 25..300)
        speed_row = QHBoxLayout()
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(25, 300)
        self.speed_slider.setValue(int(round(self.widget.state.speed_multiplier * 100)))
        self.speed_lbl = QLabel(f"{self.widget.state.speed_multiplier:.2f}x")
        self.speed_lbl.setMinimumWidth(42)
        self.speed_slider.valueChanged.connect(self._on_speed_changed)
        speed_row.addWidget(self.speed_slider)
        speed_row.addWidget(self.speed_lbl)
        form.addRow("⚡ Hız Çarpanı:", speed_row)

        # Custom FPS
        self.fps_spin = QDoubleSpinBox()
        self.fps_spin.setRange(0.0, 30.0)
        self.fps_spin.setSingleStep(1.0)
        self.fps_spin.setSpecialValueText(f"Varsayılan ({self.widget.asset.default_fps:g})")
        self.fps_spin.setValue(self.widget.state.custom_fps or 0.0)
        self.fps_spin.valueChanged.connect(self._on_fps_changed)
        form.addRow("🎞️ Manuel FPS (0=Oto):", self.fps_spin)

        # Study Timer Duration
        timer_row = QHBoxLayout()
        self.timer_spin = QSpinBox()
        self.timer_spin.setRange(0, 360)
        self.timer_spin.setSpecialValueText("Süresiz")
        self.timer_spin.setSuffix(" dk")
        self.timer_spin.setValue(self.widget.state.duration_minutes)
        apply_timer_btn = QPushButton("Başlat / Güncelle")
        apply_timer_btn.clicked.connect(self._on_apply_timer)
        timer_row.addWidget(self.timer_spin)
        timer_row.addWidget(apply_timer_btn)
        form.addRow("⏱️ Ekranda Kalma:", timer_row)

        # Color Theme Selector + Hex
        color_row = QHBoxLayout()
        self.theme_combo = QComboBox()
        self.theme_combo.addItem("Önerilen (Otomatik)", "auto")
        for key, info in self.widget.theme_lib.themes.items():
            self.theme_combo.addItem(str(info.get("name", key)), key)
        idx = self.theme_combo.findData(self.widget.state.color_theme)
        if idx >= 0:
            self.theme_combo.setCurrentIndex(idx)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)

        self.hex_edit = QLineEdit()
        self.hex_edit.setPlaceholderText("#FFFFFF")
        self.hex_edit.setMaximumWidth(80)
        if self.widget.state.color_theme.startswith("#"):
            self.hex_edit.setText(self.widget.state.color_theme)
        self.hex_edit.returnPressed.connect(self._on_hex_entered)

        pick_btn = QPushButton("🎨")
        pick_btn.setMaximumWidth(36)
        pick_btn.clicked.connect(self._on_pick_color)
        color_row.addWidget(self.theme_combo)
        color_row.addWidget(self.hex_edit)
        color_row.addWidget(pick_btn)
        form.addRow("🎨 Renk Modu:", color_row)

        # Particle Selector
        particle_row = QHBoxLayout()
        self.particle_combo = QComboBox()
        particle_choices = [
            ("Varsayılan", None),
            ("Kapalı", "none"),
            ("❄️ Kar Yağışı", "snow"),
            ("🌧️ Yağmur", "rain"),
            ("⚡ Şimşekli Fırtına", "lightning"),
            ("♨️ Buhar", "steam"),
            ("♥ Kalpler", "hearts"),
            ("✨ Kıvılcım", "sparks"),
            ("✦ Yıldız Tozu", "stars"),
        ]
        for label, val in particle_choices:
            self.particle_combo.addItem(label, val)
        p_idx = self.particle_combo.findData(self.widget.state.particle_override_type)
        if p_idx >= 0:
            self.particle_combo.setCurrentIndex(p_idx)
        self.particle_combo.currentIndexChanged.connect(self._on_particle_changed)

        self.density_combo = QComboBox()
        self.density_combo.addItem("Az", "low")
        self.density_combo.addItem("Orta", "medium")
        self.density_combo.addItem("Çok", "high")
        d_idx = self.density_combo.findData(self.widget.state.particle_density)
        if d_idx >= 0:
            self.density_combo.setCurrentIndex(d_idx)
        self.density_combo.currentIndexChanged.connect(self._on_density_changed)
        particle_row.addWidget(self.particle_combo)
        particle_row.addWidget(self.density_combo)
        form.addRow("✨ Parçacık Efekti:", particle_row)

        root.addLayout(form)

        # Toggles
        self.glow_chk = QCheckBox("Yumuşak Neon Parıltı (Glow)")
        self.glow_chk.setChecked(self.widget.state.glow_enabled)
        self.glow_chk.toggled.connect(lambda v: self.widget.set_glow(v))
        root.addWidget(self.glow_chk)

        self.shadow_chk = QCheckBox("Okunabilirlik Gölgesi (Her Zeminde Net)")
        self.shadow_chk.setChecked(self.widget.state.shadow_enabled)
        self.shadow_chk.toggled.connect(lambda v: self.widget.set_shadow(v))
        root.addWidget(self.shadow_chk)

        self.flip_chk = QCheckBox("Yatay Aynala (Sola / Sağa Çevir)")
        self.flip_chk.setChecked(self.widget.state.flip_horizontal)
        self.flip_chk.toggled.connect(lambda v: self.widget.set_flip(v))
        root.addWidget(self.flip_chk)

        self.top_chk = QCheckBox("Her Zaman Üstte (Always on Top)")
        self.top_chk.setChecked(self.widget.state.always_on_top)
        self.top_chk.toggled.connect(lambda v: self.widget.set_always_on_top(v))
        root.addWidget(self.top_chk)

        self.zzz_chk = QCheckBox("Uyku Zzz Baloncukları Göster")
        self.zzz_chk.setChecked(self.widget.state.sleep_zzz_enabled)
        self.zzz_chk.toggled.connect(lambda v: self.widget.set_sleep_zzz(v))
        root.addWidget(self.zzz_chk)

        self.blink_chk = QCheckBox("Göz Kırpma Efekti")
        self.blink_chk.setChecked(self.widget.state.eye_blink_enabled)
        self.blink_chk.toggled.connect(lambda v: self.widget.set_eye_blink(v))
        root.addWidget(self.blink_chk)

        close_btn = QPushButton("Tamam")
        close_btn.clicked.connect(self.accept)
        root.addWidget(close_btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _on_opacity_changed(self, val: int) -> None:
        self.opacity_lbl.setText(f"%{val}")
        self.widget.set_opacity(val / 100.0)

    def _on_size_changed(self, val: int) -> None:
        self.size_lbl.setText(f"{val} pt")
        self.widget.set_font_size(val)

    def _on_ls_changed(self, val: int) -> None:
        ls = val / 100.0
        self.ls_lbl.setText(f"{ls:.2f}x")
        self.widget.set_line_spacing(ls)

    def _on_speed_changed(self, val: int) -> None:
        mult = val / 100.0
        self.speed_lbl.setText(f"{mult:.2f}x")
        self.widget.set_speed_multiplier(mult)

    def _on_fps_changed(self, val: float) -> None:
        self.widget.set_custom_fps(None if val <= 0.0 else val)

    def _on_apply_timer(self) -> None:
        self.widget.set_timer_minutes(self.timer_spin.value())

    def _on_theme_changed(self) -> None:
        key = self.theme_combo.currentData()
        if key:
            self.hex_edit.clear()
            self.widget.set_color_theme(str(key))

    def _on_hex_entered(self) -> None:
        text = self.hex_edit.text().strip()
        if text.startswith("#") and len(text) in (4, 7):
            self.widget.set_color_theme(text)

    def _on_pick_color(self) -> None:
        c = QColorDialog.getColor(QColor("#FFFFFF"), self, "ASCII Rengi Seç")
        if c.isValid():
            hex_code = c.name().upper()
            self.hex_edit.setText(hex_code)
            self.widget.set_color_theme(hex_code)

    def _on_particle_changed(self) -> None:
        val = self.particle_combo.currentData()
        self.widget.set_particle_override(val)

    def _on_density_changed(self) -> None:
        val = self.density_combo.currentData()
        if val:
            self.widget.set_particle_density(str(val))
