import os
import sys
import logging
from pathlib import Path
from dotenv import load_dotenv

# setup logging console-only
def setup_logging():
    if logging.getLogger().hasHandlers():
        logging.getLogger().handlers.clear()
        
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] - %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout)
        ]
    )
    logging.info("Logging dimulai (Console Only)")

setup_logging()

# Main script detection
if sys.argv and sys.argv[0] and sys.argv[0] != "-c" and Path(sys.argv[0]).suffix == ".py":
    main_file = Path(sys.argv[0]).resolve()
else:
    main_file = Path(__file__).resolve().parents[1] / "BOT1_CAPTCHA.py"

SCRIPT_NAME = main_file.stem
SCRIPT_DIR = main_file.parent

ENV_FILE = os.getenv("ENV_FILE") or str(SCRIPT_DIR / f"{SCRIPT_NAME}.env")

OWNER_ID = "5601279587"  # ID TELEGRAM OWNER

def _clean(s: str) -> str:
    return (s or "").strip().strip('"').strip("'")

try:
    if not Path(ENV_FILE).exists():
        raise FileNotFoundError(f"File env '{ENV_FILE}' tidak ditemukan.")
    load_dotenv(ENV_FILE, override=True)
    BOT_TOKEN = _clean(os.getenv("BOT_TOKEN", ""))
    ALLOWED_CHAT_ID = _clean(os.getenv("ALLOWED_CHAT_ID", ""))  # Optional
    BOT_NAME = _clean(os.getenv("BOT_NAME", "")) or SCRIPT_NAME  # Nama bot untuk judul terminal
    WEBAPP_URL = _clean(os.getenv("WEBAPP_URL", ""))  # URL Telegram Web App dashboard (harus HTTPS)
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN belum di-set di env")
except (FileNotFoundError, ValueError) as e:
    logging.critical(f"Error konfigurasi fatal: {e}")
    sys.exit(1)

def is_headless() -> bool:
    """Membaca ulang nilai HEADLESS dari file .env secara real-time"""
    try:
        if Path(ENV_FILE).exists():
            load_dotenv(ENV_FILE, override=True)
    except:
        pass
    val = _clean(os.getenv("HEADLESS", "True")).lower()
    return val not in ("0", "false", "f", "off", "no")

# Flag bawaan (kompatibilitas)
HEADLESS = is_headless()

# Path configuration (Multi-User mode uses user_data subdirectories)
BASE_URL = "https://subsiditepatlpg.mypertamina.id"
DURATIONS_FILE = SCRIPT_DIR / "durations.json"
USER_DATA_DIR = SCRIPT_DIR / "user_data"
USER_DATA_DIR.mkdir(parents=True, exist_ok=True)

# QRIS file location (case-insensitive check)
QRIS_FILE = None
for qris_name in ["qris.png", "QRIS.png", "qris.PNG", "QRIS.PNG"]:
    qris_path = SCRIPT_DIR / qris_name
    if qris_path.exists():
        QRIS_FILE = qris_path
        break
if QRIS_FILE is None:
    QRIS_FILE = SCRIPT_DIR / "qris.png"  # Default fallback

IDLE_TIMEOUT_SECONDS = 180
