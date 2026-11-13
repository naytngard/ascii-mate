@echo off
chcp 65001 > nul
title ASCII Mate
cd /d "%~dp0"

set "PY=python"
where python >nul 2>nul
if %errorlevel% neq 0 (
    where py >nul 2>nul
    if %errorlevel% neq 0 (
        echo [HATA] Python bulunamadi! Lutfen Python 3.10+ yukleyin.
        pause
        exit /b 1
    )
    set "PY=py -3"
)

%PY% -c "import PyQt6, rich" >nul 2>nul
if %errorlevel% neq 0 (
    echo [BILGI] Gerekli kutuphaneler kuruluyor...
    %PY% -m pip install -r requirements.txt
)

%PY% main.py
if %errorlevel% neq 0 (
    echo.
    echo [UYARI] Program bir hata ile kapandi. Ayrintilar: %%APPDATA%%\ASCII_Mate\logs
    pause
)
