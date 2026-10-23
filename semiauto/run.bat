@echo off
title TOOLS PROSES NIK SEMI-MANUAL (PERTAMINA)
cd /d "%~dp0"

echo ======================================================
echo    MEMULAI TOOLS PROSES NIK SEMI-MANUAL
echo ======================================================

if exist "..\.venv\Scripts\python.exe" (
    echo [INFO] Menggunakan venv di ..\.venv
    ..\.venv\Scripts\python.exe main.py
) else if exist ".venv\Scripts\python.exe" (
    echo [INFO] Menggunakan venv di .venv
    .venv\Scripts\python.exe main.py
) else (
    echo [INFO] Menggunakan python sistem
    python main.py
)

pause
