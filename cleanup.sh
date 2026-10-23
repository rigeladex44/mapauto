#!/bin/bash

# Script untuk membersihkan file cache, temporary, dan log files
# Jalankan dengan: bash cleanup.sh

echo "🧹 Memulai pembersihan..."

# Hapus Python cache
echo "📦 Menghapus Python cache..."
find . -type f -name "*.pyc" -delete
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# Hapus temporary files dari captcha detection
echo "🗑️  Menghapus temporary files..."
rm -f temp_bg.jpg temp_piece.png piece_detection.png status_unclear_*.png

# Hapus log files
echo "📝 Menghapus log files..."
rm -f *.log
find user_data -name "*.log" -type f -delete 2>/dev/null || true

# Hapus logs directory jika ada
if [ -d "logs" ]; then
    echo "📂 Menghapus logs directory..."
    rm -rf logs
fi

# Opsional: Hapus virtual environment (uncomment jika ingin rebuild)
# echo "🔄 Menghapus virtual environment..."
# rm -rf .venv

echo ""
echo "✅ Pembersihan selesai!"
echo ""
echo "📊 Sisa file di direktori:"
ls -lh | grep -v "^d" | grep -v "total"
