@echo off
REM Script untuk membersihkan file cache, temporary, dan log files (Windows)
REM Jalankan dengan: cleanup.bat

echo ====================================
echo   Membersihkan file cache...
echo ====================================
echo.

echo [1/4] Menghapus Python cache...
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
del /s /q *.pyc 2>nul

echo [2/4] Menghapus temporary files...
del /q temp_bg.jpg 2>nul
del /q temp_piece.png 2>nul
del /q piece_detection.png 2>nul
del /q status_unclear_*.png 2>nul

echo [3/4] Menghapus log files...
del /q *.log 2>nul
for /r user_data %%f in (*.log) do del /q "%%f" 2>nul

echo [4/4] Menghapus logs directory...
if exist logs rd /s /q logs

echo.
echo ====================================
echo   Pembersihan selesai!
echo ====================================
echo.

REM Opsional: Hapus virtual environment (uncomment jika ingin rebuild)
REM echo Menghapus virtual environment...
REM rd /s /q .venv

pause
