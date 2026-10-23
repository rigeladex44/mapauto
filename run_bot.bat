@echo off
:: Ambil nama script Python yang akan dijalankan (bisa diubah untuk clone bot)
set BOT_SCRIPT=BOT1_CAPTCHA.py
set BOT_NAME=%BOT_SCRIPT:.py=%

title [%BOT_NAME%] - BOT MAP PREMIUM

echo ====================================================
echo  BOT: %BOT_NAME%
echo ====================================================

:: Cek apakah venv ada
if not exist .venv (
    echo [ERROR] Virtual Environment belum dibuat!
    echo Silakan jalankan install_windows.bat terlebih dahulu.
    pause
    exit /b
)

:: Jalankan bot dengan auto-restart loop
:loop
echo.
echo [INFO] Memulai %BOT_NAME%...
echo ----------------------------------------
.venv\Scripts\python.exe %BOT_SCRIPT%
echo ----------------------------------------
echo [WARNING] %BOT_NAME% berhenti/crash. Restarting in 5 seconds...
timeout /t 5
goto loop
