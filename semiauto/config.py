import os
import sys
from pathlib import Path

# Base Directory: Mandiri di dalam folder semiauto
SEMIAUTO_DIR = Path(__file__).resolve().parent

# File Akun & NIK
AKUN_FILE = SEMIAUTO_DIR / "akun.txt"
NIK_FILE = SEMIAUTO_DIR / "nik.txt"

# Cookies Directory
COOKIES_DIR = SEMIAUTO_DIR / "cookies"
COOKIES_DIR.mkdir(parents=True, exist_ok=True)

# Riwayat Directory & Files
RIWAYAT_DIR = SEMIAUTO_DIR / "riwayat"
RIWAYAT_DIR.mkdir(parents=True, exist_ok=True)

SUKSES_FILE = RIWAYAT_DIR / "sukses.txt"
LIMIT_FILE = RIWAYAT_DIR / "limit.txt"
TIDAK_DITEMUKAN_FILE = RIWAYAT_DIR / "tidak_ditemukan.txt"
SKIP_FILE = RIWAYAT_DIR / "skip.txt"

# URL Pertamina
BASE_URL = "https://subsiditepatlpg.mypertamina.id"
LOGIN_URL = f"{BASE_URL}/merchant-login"
BERANDA_URL = f"{BASE_URL}/merchant/app"
VERIFIKASI_NIK_URL = f"{BASE_URL}/merchant/app/verification-nik"
SALE_URL_KEYWORD = "/merchant/app/sale"

# Filter Pelanggan Default
DEFAULT_ALLOWED_TYPES = ["USAHA MIKRO", "RUMAH TANGGA"]

# Browser Settings (Headed mode agar tampil di layar untuk kontrol manual di halaman sale)
HEADLESS = False
BROWSER_VIEWPORT = {"width": 1280, "height": 850}
