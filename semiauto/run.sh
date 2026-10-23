#!/bin/bash
# ====================================================================
# Launcher Tools Proses NIK Semi-Manual untuk MacOS / Linux
# ====================================================================

# Pindah ke direktori script
cd "$(dirname "$0")"

echo "======================================================"
echo "    MEMULAI TOOLS PROSES NIK SEMI-MANUAL"
echo "======================================================"

# Cek virtual environment di parent directory atau folder saat ini
if [ -d "../.venv" ]; then
    echo " Menggunakan venv: ../.venv"
    PYTHON="../.venv/bin/python"
elif [ -d ".venv" ]; then
    echo " Menggunakan venv: .venv"
    PYTHON=".venv/bin/python"
else
    echo " Menggunakan Python sistem"
    PYTHON="python3"
fi

$PYTHON main.py
