"""Dark-glass right-click context menu for CompanionWidget."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtGui import QAction, QColor
from PyQt6.QtWidgets import QColorDialog, QFileDialog, QInputDialog, QMenu, QMessageBox

from src.core.converter import import_file_to_community
from src.core.procedural_engine import create_procedural_renderer
from src.gui.settings_dialog import SettingsDialog

if TYPE_CHECKING:
    from src.gui.companion_widget import CompanionWidget


DARK_GLASS_MENU_QSS = """
QMenu {
    background-color: rgba(18, 20, 29, 240);
    color: #E2E8F0;
    border: 1px solid rgba(148, 163, 184, 70);
    border-radius: 10px;
    padding: 6px 4px;
    font-family: 'Segoe UI', sans-serif;
    font-size: 12px;
}
QMenu::item {
    padding: 6px 24px 6px 14px;
    border-radius: 6px;
    margin: 1px 4px;
}
QMenu::item:selected {
    background-color: rgba(56, 189, 248, 65);
    color: #FFFFFF;
}
QMenu::separator {
    height: 1px;
    background: rgba(148, 163, 184, 45);
    margin: 5px 10px;
}
QMenu::indicator {
    width: 14px;
    height: 14px;
    margin-left: 6px;
}
"""


def build_context_menu(widget: "CompanionWidget") -> QMenu:
    """Constructs the full right-click dark glass context menu."""
    menu = QMenu(widget)
    menu.setStyleSheet(DARK_GLASS_MENU_QSS)

    # Header (disabled info action)
    header = QAction(f"✨ {widget.asset.name} ({widget.asset.category})", menu)
    header.setEnabled(False)
    menu.addAction(header)
    menu.addSeparator()

    # Fine-tuning settings dialog
    settings_act = QAction("🎛️  İnce Ayar Paneli (Slider'lar)...", menu)
    settings_act.triggered.connect(lambda: SettingsDialog(widget).exec())
    menu.addAction(settings_act)

    # Opacity Submenu
    op_menu = menu.addMenu(f"💧  Saydamlık (%{int(round(widget.state.opacity * 100))})")
    op_menu.setStyleSheet(DARK_GLASS_MENU_QSS)
    for pct in (15, 30, 50, 75, 90, 100):
        act = QAction(f"%{pct}", op_menu, checkable=True)
        act.setChecked(abs(widget.state.opacity * 100 - pct) < 4)
        act.triggered.connect(lambda _c, p=pct: widget.set_opacity(p / 100.0))
        op_menu.addAction(act)

    # Line Spacing (HD Tightness) Submenu
    ls_menu = menu.addMenu(f"📐  Satır Aralığı ({widget.state.line_spacing:.2f}x)")
    ls_menu.setStyleSheet(DARK_GLASS_MENU_QSS)
    for ls_val, ls_lbl in (
        (0.82, "0.82x (Ultra Sıkı HD)"),
        (0.86, "0.86x (Sıkı)"),
        (0.88, "0.88x (Varsayılan HD)"),
        (0.92, "0.92x (Dengeli)"),
        (1.00, "1.00x (Klasik Terminal)"),
    ):
        act = QAction(ls_lbl, ls_menu, checkable=True)
        act.setChecked(abs(widget.state.line_spacing - ls_val) < 0.015)
        act.triggered.connect(lambda _c, v=ls_val: widget.set_line_spacing(v))
        ls_menu.addAction(act)

    # Study Timer Submenu
    timer_label = "Süresiz" if widget.state.duration_minutes == 0 else f"{widget.state.duration_minutes} dk"
    timer_menu = menu.addMenu(f"⏱️  Ekranda Kalma Süresi ({timer_label})")
    timer_menu.setStyleSheet(DARK_GLASS_MENU_QSS)
    for mins, label in (
        (0, "∞  Süresiz (Ben kapatana kadar)"),
        (15, "15 Dakika"),
        (25, "25 Dakika (Pomodoro)"),
        (45, "45 Dakika"),
        (60, "60 Dakika"),
    ):
        act = QAction(label, timer_menu, checkable=True)
        act.setChecked(widget.state.duration_minutes == mins)
        act.triggered.connect(lambda _c, m=mins: widget.set_timer_minutes(m))
        timer_menu.addAction(act)

    custom_timer_act = QAction("⏳  Özel Dakika Gir...", timer_menu)
    custom_timer_act.triggered.connect(lambda: _prompt_custom_timer(widget))
    timer_menu.addAction(custom_timer_act)
    timer_menu.addSeparator()
    show_t_act = QAction("Kalan Süreyi Altta Göster", timer_menu, checkable=True)
    show_t_act.setChecked(widget.state.show_timer_below)
    show_t_act.triggered.connect(lambda checked: widget.set_show_timer_below(checked))
    timer_menu.addAction(show_t_act)

    brk_act = QAction("☕ Süre Bitince 5 dk Mola Sayacı Başlat", timer_menu, checkable=True)
    brk_act.setChecked(widget.state.pomodoro_break_enabled)
    brk_act.triggered.connect(lambda checked: widget.set_pomodoro_break_enabled(checked))
    timer_menu.addAction(brk_act)

    # 3D Grid Resolution & Orbit Submenu (for live 3D/Shader widgets)
    if widget.asset.is_procedural:
        res_labels = {
            "auto": "Otomatik (Büyütmeye Göre)",
            "compact": "Kompakt (38×18)",
            "standard": "Standart (52×24)",
            "hd": "HD (64×30)",
            "ultra": "Ultra HD (74×34)",
        }
        cur_lbl = res_labels.get(widget.state.grid_resolution, "Otomatik")
        res_menu = menu.addMenu(f"🖥️  3B Izgara Çözünürlüğü ({cur_lbl})")
        res_menu.setStyleSheet(DARK_GLASS_MENU_QSS)
        for r_key, r_name in res_labels.items():
            ract = QAction(r_name, res_menu, checkable=True)
            ract.setChecked(widget.state.grid_resolution == r_key)
            ract.triggered.connect(lambda _c, rk=r_key: widget.set_grid_resolution(rk))
            res_menu.addAction(ract)

        orbit_menu = menu.addMenu("🧭  3B Serbest Bakış (Shift+Sol Tık)")
        orbit_menu.setStyleSheet(DARK_GLASS_MENU_QSS)
        free_orb_act = QAction("Sol Tıkla Doğrudan Döndür (Sürükleme Kapalı)", orbit_menu, checkable=True)
        free_orb_act.setChecked(widget.state.free_orbit_3d)
        free_orb_act.triggered.connect(lambda checked: widget.set_free_orbit(checked))
        orbit_menu.addAction(free_orb_act)

        reset_orb_act = QAction("🔄 3B Kamera Açısını Sıfırla", orbit_menu)
        reset_orb_act.triggered.connect(widget.reset_orbit)
        orbit_menu.addAction(reset_orb_act)

    # Speed Submenu
    spd_menu = menu.addMenu(f"⚡  Animasyon Hızı ({widget.state.speed_multiplier:.2g}x)")
    spd_menu.setStyleSheet(DARK_GLASS_MENU_QSS)
    for mult, label in (
        (0.25, "0.25x (Çok Sakin)"),
        (0.5, "0.5x (Yavaş)"),
        (1.0, "1x (Normal)"),
        (2.0, "2x (Hızlı)"),
        (3.0, "3x (Çok Hızlı)"),
    ):
        act = QAction(label, spd_menu, checkable=True)
        act.setChecked(abs(widget.state.speed_multiplier - mult) < 0.05)
        act.triggered.connect(lambda _c, m=mult: widget.set_speed_multiplier(m))
        spd_menu.addAction(act)

    # Color Themes Submenu
    color_menu = menu.addMenu("🎨  Renk & Tema")
    color_menu.setStyleSheet(DARK_GLASS_MENU_QSS)
    auto_act = QAction("✨ Önerilen (Varsayılan)", color_menu, checkable=True)
    auto_act.setChecked(widget.state.color_theme in ("auto", "auto_hd"))
    auto_act.triggered.connect(lambda: widget.set_color_theme("auto"))
    color_menu.addAction(auto_act)
    color_menu.addSeparator()

    for key, info in widget.theme_lib.themes.items():
        if key == "auto_hd":
            continue
        act = QAction(str(info.get("name", key)), color_menu, checkable=True)
        act.setChecked(widget.state.color_theme == key)
        act.triggered.connect(lambda _c, k=key: widget.set_color_theme(k))
        color_menu.addAction(act)

    color_menu.addSeparator()
    pick_act = QAction("🖌️  Özel Renk Seç (Hex)...", color_menu)
    pick_act.triggered.connect(lambda: _pick_custom_color(widget))
    color_menu.addAction(pick_act)

    # Particles & Scene Effects Submenu
    scene_menu = menu.addMenu("✨  Parçacık & Sahne Ayarları")
    scene_menu.setStyleSheet(DARK_GLASS_MENU_QSS)

    if widget.asset.particles.type != "none":
        toggle_lbl = widget.asset.particles.toggle_label or "Özel Parçacık Efekti"
        p_act = QAction(f"🌟 {toggle_lbl}", scene_menu, checkable=True)
        p_act.setChecked(widget.is_particles_active())
        p_act.triggered.connect(lambda checked: widget.set_particles_enabled(checked))
        scene_menu.addAction(p_act)
        scene_menu.addSeparator()

    for ptype, label in (
        (None, "Varsayılan Efekt"),
        ("none", "Efektsiz (Kapalı)"),
        ("snow", "❄️ Kar Yağışı Modu"),
        ("rain", "🌧️ Yağmur Modu"),
        ("lightning", "⚡ Şimşekli Fırtına Modu"),
        ("steam", "♨️ Buhar Modu"),
        ("hearts", "♥ Kalpler Modu"),
        ("sparks", "✨ Kıvılcım Modu"),
        ("stars", "✦ Yıldız Tozu Modu"),
    ):
        act = QAction(label, scene_menu, checkable=True)
        act.setChecked(widget.state.particle_override_type == ptype)
        act.triggered.connect(lambda _c, pt=ptype: widget.set_particle_override(pt))
        scene_menu.addAction(act)

    scene_menu.addSeparator()
    dens_menu = scene_menu.addMenu("Yoğunluk (Az / Orta / Çok)")
    dens_menu.setStyleSheet(DARK_GLASS_MENU_QSS)
    for dkey, dlabel in (("low", "Az"), ("medium", "Orta"), ("high", "Çok")):
        dact = QAction(dlabel, dens_menu, checkable=True)
        dact.setChecked(widget.state.particle_density == dkey)
        dact.triggered.connect(lambda _c, dk=dkey: widget.set_particle_density(dk))
        dens_menu.addAction(dact)

    scene_menu.addSeparator()
    zzz_act = QAction("💤 Uyku Zzz Baloncukları", scene_menu, checkable=True)
    zzz_act.setChecked(widget.state.sleep_zzz_enabled)
    zzz_act.triggered.connect(lambda checked: widget.set_sleep_zzz(checked))
    scene_menu.addAction(zzz_act)

    blink_act = QAction("👀 Göz Kırpma Efekti", scene_menu, checkable=True)
    blink_act.setChecked(widget.state.eye_blink_enabled)
    blink_act.triggered.connect(lambda checked: widget.set_eye_blink(checked))
    scene_menu.addAction(blink_act)

    track_act = QAction("👀 Fare İmlecinin Yönüne Bak", scene_menu, checkable=True)
    track_act.setChecked(widget.state.track_cursor)
    track_act.triggered.connect(lambda checked: widget.set_track_cursor(checked))
    scene_menu.addAction(track_act)

    menu.addSeparator()

    # Quick Visual Toggles
    glow_act = QAction("✨ Yumuşak Parıltı (Glow)", menu, checkable=True)
    glow_act.setChecked(widget.state.glow_enabled)
    glow_act.triggered.connect(lambda checked: widget.set_glow(checked))
    menu.addAction(glow_act)

    shadow_act = QAction("🌑 Okunabilirlik Gölgesi (Kontur)", menu, checkable=True)
    shadow_act.setChecked(widget.state.shadow_enabled)
    shadow_act.triggered.connect(lambda checked: widget.set_shadow(checked))
    menu.addAction(shadow_act)

    flip_act = QAction("🔄 Yatay Aynala (Flip)", menu, checkable=True)
    flip_act.setChecked(widget.state.flip_horizontal)
    flip_act.triggered.connect(lambda checked: widget.set_flip(checked))
    menu.addAction(flip_act)

    top_act = QAction("📌 Her Zaman Üstte", menu, checkable=True)
    top_act.setChecked(widget.state.always_on_top)
    top_act.triggered.connect(lambda checked: widget.set_always_on_top(checked))
    menu.addAction(top_act)

    ghost_act = QAction("👻 Ders / Hayalet Modu (Tıklama Geçirgen)", menu, checkable=True)
    ghost_act.setChecked(widget.state.click_through)
    ghost_act.triggered.connect(lambda checked: widget.set_click_through(checked))
    menu.addAction(ghost_act)

    menu.addSeparator()

    # Community Import / Export / Library
    import_act = QAction("📥 Dosya İçe Aktar (.ascii.json / .txt)...", menu)
    import_act.triggered.connect(lambda: _import_community_file(widget))
    menu.addAction(import_act)

    export_act = QAction("📤 Dışa Aktar (.ascii.json)...", menu)
    export_act.triggered.connect(lambda: _export_asset_file(widget))
    menu.addAction(export_act)

    if widget.manager_callbacks and "open_hub" in widget.manager_callbacks:
        hub_act = QAction("📚 Kütüphaneden Başka Karakter Aç...", menu)
        hub_act.triggered.connect(widget.manager_callbacks["open_hub"])
        menu.addAction(hub_act)

    menu.addSeparator()
    close_act = QAction("❌ Bu Widget'ı Kapat", menu)
    close_act.triggered.connect(widget.close_widget)
    menu.addAction(close_act)

    return menu


def _prompt_custom_timer(widget: "CompanionWidget") -> None:
    mins, ok = QInputDialog.getInt(
        widget,
        "Özel Çalışma Zamanlayıcısı",
        "Kaç dakika ekranda kalsın? (0 = Süresiz):",
        value=max(1, widget.state.duration_minutes or 30),
        min=0,
        max=600,
    )
    if ok:
        widget.set_timer_minutes(mins)


def _pick_custom_color(widget: "CompanionWidget") -> None:
    color = QColorDialog.getColor(QColor("#FFFFFF"), widget, "Özel ASCII Rengi Seç")
    if color.isValid():
        widget.set_color_theme(color.name().upper())


def _import_community_file(widget: "CompanionWidget") -> None:
    file_path, _ = QFileDialog.getOpenFileName(
        widget,
        "ASCII Animasyon İçe Aktar",
        "",
        "ASCII Dosyaları (*.ascii.json *.json *.txt);;Tüm Dosyalar (*.*)",
    )
    if not file_path:
        return
    asset, msg = import_file_to_community(file_path, widget.library.community_dir)
    if asset:
        widget.library.reload()
        QMessageBox.information(widget, "Başarılı", f"{msg}\n\nKarakter eklendi ve şimdi açılıyor!")
        if widget.manager_callbacks and "spawn_asset" in widget.manager_callbacks:
            widget.manager_callbacks["spawn_asset"](asset.id)
    else:
        QMessageBox.warning(widget, "İçe Aktarma Hatası", msg)


def _export_asset_file(widget: "CompanionWidget") -> None:
    default_name = f"{widget.asset.id}.ascii.json"
    out_path, _ = QFileDialog.getSaveFileName(
        widget,
        "ASCII Animasyonu Dışa Aktar",
        default_name,
        "ASCII JSON (*.ascii.json)",
    )
    if not out_path:
        return
    try:
        payload = widget.asset.to_dict()
        if widget.asset.is_procedural and widget.asset.procedural:
            # Bake a smooth 24-frame playable multi-color loop of the live 3D shader
            gw, gh = widget._compute_target_3d_grid()
            renderer = create_procedural_renderer(widget.asset.procedural, {"width": gw, "height": gh})
            if renderer is not None:
                baked_frames = []
                raw_color_grids = []
                dt = 1.0 / max(10.0, min(20.0, float(widget.asset.default_fps or 18.0)))
                for _ in range(24):
                    pf = renderer.step(
                        dt,
                        1.0,
                        yaw_offset=widget.state.orbit_yaw,
                        pitch_offset=widget.state.orbit_pitch,
                    )
                    baked_frames.append("\n".join(pf.lines))
                    raw_color_grids.append(pf.colors)

                # Quantize RGB palette into single-char keys for valid schema v2.0 color_frames
                key_chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
                pal_rev = {}
                palette_map = {}
                color_frames = []
                for cgrid in raw_color_grids:
                    crows = []
                    for crow in cgrid:
                        chars = []
                        for rgb in crow:
                            if rgb is None:
                                chars.append(" ")
                            else:
                                # Quantize RGB to 32-step grid to keep palette <= 62 keys
                                q = (rgb[0] & 0xE0, rgb[1] & 0xE0, rgb[2] & 0xE0)
                                k = pal_rev.get(q)
                                if k is None:
                                    if len(pal_rev) < len(key_chars):
                                        k = key_chars[len(pal_rev)]
                                        pal_rev[q] = k
                                        palette_map[k] = f"#{q[0]:02X}{q[1]:02X}{q[2]:02X}"
                                    else:
                                        k = min(
                                            pal_rev,
                                            key=lambda pq: (pq[0] - q[0]) ** 2 + (pq[1] - q[1]) ** 2 + (pq[2] - q[2]) ** 2,
                                        )
                                        k = pal_rev[k]
                                chars.append(k)
                        crows.append("".join(chars))
                    color_frames.append("\n".join(crows))

                payload["schema_version"] = "2.0"
                payload["frames"] = baked_frames
                payload["palette_map"] = palette_map
                payload["color_frames"] = color_frames

        with Path(out_path).open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        QMessageBox.information(widget, "Dışa Aktarıldı", f"Kaydedildi:\n{out_path}")
    except Exception as e:
        QMessageBox.warning(widget, "Hata", f"Kaydedilemedi: {e}")
