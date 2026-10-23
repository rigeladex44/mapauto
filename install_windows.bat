@echo off
setlocal enabledelayedexpansion
title INSTALASI OTOMATIS BOT LPG PREMIUM

echo ====================================================
echo 🤖 WINDOWS AUTO-DETECTION & INSTALLATION SYSTEM
echo ====================================================
echo.

:: 1. DETEKSI VERSI WINDOWS & ARSITEKTUR
echo 💻 [1/5] Mendeteksi Sistem Operasi...
ver
echo Arsitektur CPU  : %PROCESSOR_ARCHITECTURE%
if not "%PROCESSOR_ARCHITEW6432%"=="" (
    echo Arsitektur OS   : 64-bit (via WoW64)
    set "OS_64BIT=1"
) else (
    if /i "%PROCESSOR_ARCHITECTURE%"=="AMD64" (
        echo Arsitektur OS   : 64-bit
        set "OS_64BIT=1"
    ) else (
        echo Arsitektur OS   : 32-bit
        set "OS_64BIT=0"
    )
)
echo.

:: 2. DETEKSI & INSTALASI PYTHON OTOMATIS
echo 🐍 [2/5] Memeriksa Instalasi Python...
set "PYTHON_CMD="

:: Cek apakah Python terinstall di PATH
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
    goto python_checked
)

:: Cek default path AppData (Python 3.11)
if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe" (
    set "PYTHON_CMD=%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe"
    goto python_checked
)

:: Cek default path AppData (Python 3.12)
if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe" (
    set "PYTHON_CMD=%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe"
    goto python_checked
)

:: Jika tidak ditemukan, download & install Python secara otomatis
echo [WARNING] Python tidak ditemukan pada sistem.
echo [INFO] Memulai download dan instalasi Python 3.11 secara silent...

:: Tentukan file installer berdasarkan arsitektur
set "PY_VER=3.11.9"
if "%OS_64BIT%"=="1" (
    set "PY_URL=https://www.python.org/ftp/python/%PY_VER%/python-%PY_VER%-amd64.exe"
) else (
    set "PY_URL=https://www.python.org/ftp/python/%PY_VER%/python-%PY_VER%.exe"
)

echo [INFO] Mengunduh Python %PY_VER% dari: %PY_URL%
curl -L -o python_installer.exe %PY_URL%
if %errorlevel% neq 0 (
    echo [ERROR] Gagal mengunduh installer Python! Silakan install Python manual.
    pause
    exit /b
)

echo [INFO] Menginstal Python %PY_VER% secara silent...
echo [INFO] Silakan tunggu sekitar 15-30 detik...
python_installer.exe /quiet InstallAllUsers=0 PrependPath=1 Include_test=0 Include_doc=0 Include_launcher=0 Include_tcltcl=0 Include_pip=1
timeout /t 20 /nobreak >nul

:: Bersihkan file installer
del python_installer.exe

:: Deteksi ulang lokasi python
if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe" (
    set "PYTHON_CMD=%USERPROFILE%\AppData\Local\Programs\Python\Python311\python.exe"
    goto python_checked
)
if exist "%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe" (
    set "PYTHON_CMD=%USERPROFILE%\AppData\Local\Programs\Python\Python312\python.exe"
    goto python_checked
)

:: Terakhir coba via cmd path lagi
python --version >nul 2>&1
if %errorlevel% equ 0 (
    set "PYTHON_CMD=python"
    goto python_checked
)

echo [ERROR] Gagal menginstal Python secara otomatis.
echo Silakan unduh dan install Python 3.11 manual dari https://python.org
pause
exit /b

:python_checked
echo [SUCCESS] Python siap digunakan:
%PYTHON_CMD% --version
echo.

:: 3. MEMBUAT VIRTUAL ENVIRONMENT
echo 📦 [3/5] Membuat Virtual Environment (.venv)...
if exist .venv (
    echo [INFO] Folder .venv sudah ada, melewatkan pembuatan...
) else (
    %PYTHON_CMD% -m venv .venv
    if %errorlevel% neq 0 (
        echo [ERROR] Gagal membuat Virtual Environment!
        pause
        exit /b
    )
    echo [SUCCESS] Virtual Environment berhasil dibuat.
)
echo.

:: 4. MENGINSTALL DEPENDENCIES
echo 📚 [4/5] Menginstall Pip & Dependensi (Requirements)...
.venv\Scripts\python.exe -m pip install --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org --upgrade pip
if %errorlevel% neq 0 (
    echo [WARNING] Gagal memperbarui pip, melanjutkan instalasi dependensi...
)

if not exist requirements.txt (
    echo [ERROR] File requirements.txt tidak ditemukan!
    pause
    exit /b
)

.venv\Scripts\pip install --no-cache-dir --trusted-host pypi.org --trusted-host pypi.python.org --trusted-host files.pythonhosted.org -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Gagal menginstall dependensi! Pastikan koneksi internet stabil.
    pause
    exit /b
)
echo [SUCCESS] Dependensi berhasil diinstal.
echo.

:: 5. MENGINSTALL BROWSER PLAYWRIGHT
echo 🌐 [5/5] Memasang Web Browser Automation (Playwright)...
set NODE_TLS_REJECT_UNAUTHORIZED=0
.venv\Scripts\playwright install chromium
if %errorlevel% neq 0 (
    echo [ERROR] Gagal memasang browser Playwright!
    pause
    exit /b
)
echo [SUCCESS] Playwright Chromium berhasil dipasang.
echo.

:: MEMBERSIHKAN LOG LAMA
if exist logs del /q logs\*
if exist bot_log.txt del bot_log.txt

echo ====================================================
echo ✅ SELURUH PROSES INSTALASI SELESAI DENGAN SUKSES!
echo ====================================================
echo.
echo Untuk menjalankan bot, silakan klik/jalankan:
echo 🚀 run_bot.bat
echo.
pause
