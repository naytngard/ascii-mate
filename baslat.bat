@echo off
chcp 65001 > nul
title ASCII Mate
cd /d "%~dp0"

where python >nul 2>nul
if %errorlevel% neq 0 (
    echo [HATA] Python bulunamadi! Lutfen Python 3.10+ yukleyin.
    pause
    exit /b 1
)

python -c "import PyQt6, rich" >nul 2>nul
if %errorlevel% neq 0 (
    echo [BILGI] Gerekli kutuphaneler kuruluyor...
    python -m pip install -r requirements.txt
)

python main.py
if %errorlevel% neq 0 (
    echo.
    echo [UYARI] Program bir hata ile kapandi.
    pause
)
