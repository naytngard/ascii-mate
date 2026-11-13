# -*- mode: python ; coding: utf-8 -*-
# Iki exe uretir: ASCII_Mate.exe (konsolsuz GUI/tepsi) ve ASCII_Mate_CLI.exe (Terminal Hub icin konsollu).

EXCLUDES = [
    'numpy.f2py', 'tkinter', '_tkinter', 'unittest', 'pydoc', 'doctest', 'test', 'pytest',
    'PyQt6.QtWebEngineCore', 'PyQt6.QtWebEngineWidgets', 'PyQt6.QtQml', 'PyQt6.QtQuick',
    'PyQt6.QtMultimedia', 'PyQt6.QtSql', 'PyQt6.QtNetwork', 'PyQt6.QtBluetooth',
    'PyQt6.QtPdf', 'PyQt6.Qt3DCore', 'PyQt6.QtCharts', 'PyQt6.QtSvg',
]

a = Analysis(
    ['main.py'],
    pathex=['.'],
    binaries=[],
    datas=[('assets', 'assets')],
    hiddenimports=['src', 'src.core', 'src.gui', 'src.cli'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=EXCLUDES,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

gui_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ASCII_Mate',
    icon='assets/app_icon.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
cli_exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ASCII_Mate_CLI',
    icon='assets/app_icon.ico',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    gui_exe,
    cli_exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='ASCII_Mate',
)
