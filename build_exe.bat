@echo off
chcp 65001 > nul
title ASCII Mate - EXE Paketleyici
cd /d "%~dp0"

python -m pip show pyinstaller >nul 2>nul
if %errorlevel% neq 0 (
    echo [BILGI] PyInstaller kuruluyor...
    python -m pip install -r requirements-dev.txt
)

if /i "%~1"=="onefile" (
    echo ==============================================================
    echo   PyInstaller ile Tek Dosya (--onefile^) Olusturuluyor...
    echo ==============================================================
    echo.
    python -m PyInstaller --noconfirm --clean ^
        --name "ASCII_Mate" ^
        --onefile ^
        --console ^
        --add-data "assets;assets" ^
        main.py
    echo.
    if exist "dist\ASCII_Mate.exe" (
        echo [BASARILI] Tek dosya paket hazir: dist\ASCII_Mate.exe
    ) else (
        echo [HATA] Derleme sirasinda sorun olustu.
    )
) else (
    echo ==============================================================
    echo   PyInstaller ile Hizli Acilan Klasor (--onedir^) Olusturuluyor...
    echo   (Tek dosya icin: build_exe.bat onefile^)
    echo ==============================================================
    echo.
    python -m PyInstaller --noconfirm --clean ASCII_Mate.spec
    echo.
    if exist "dist\ASCII_Mate\ASCII_Mate.exe" (
        echo [BASARILI] Aninda acilan paket hazir: dist\ASCII_Mate\ASCII_Mate.exe
    ) else (
        echo [HATA] Derleme sirasinda sorun olustu.
    )
)
pause
