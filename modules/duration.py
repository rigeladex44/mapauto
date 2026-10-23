import time
import json
import logging
from modules.config import DURATIONS_FILE, OWNER_ID

def load_durations() -> dict:
    """Load durasi user dari file JSON"""
    if not DURATIONS_FILE.exists():
        return {}
    try:
        with open(DURATIONS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logging.error(f"Gagal load durations: {e}")
        return {}

def save_durations(durations: dict):
    """Simpan durasi ke file JSON"""
    try:
        with open(DURATIONS_FILE, 'w', encoding='utf-8') as f:
            json.dump(durations, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"Gagal save durations: {e}")

def check_user_duration(user_id: str) -> tuple[bool, str]:
    """Cek durasi user, return (is_valid, message)"""
    if str(user_id) == OWNER_ID:
        return True, "✅ Owner Access (Unlimited)"
        
    durations = load_durations()
    if user_id not in durations:
        return False, "❌ Durasi belum diaktifkan. Silakan perpanjang terlebih dahulu."
    
    expiry_timestamp = durations[user_id]
    current_time = time.time()
    
    if current_time > expiry_timestamp:
        days_expired = int((current_time - expiry_timestamp) / 86400)
        return False, f"❌ Durasi sudah expired {days_expired} hari yang lalu. Silakan perpanjang."
    
    days_left = int((expiry_timestamp - current_time) / 86400)
    hours_left = int(((expiry_timestamp - current_time) % 86400) / 3600)
    return True, f"✅ Durasi aktif. Sisa: {days_left} hari {hours_left} jam"

def add_user_duration(user_id: str, days: int):
    """Tambah durasi user (hanya owner yang bisa)"""
    durations = load_durations()
    current_time = time.time()
    if user_id in durations and durations[user_id] > current_time:
        # Tambah ke durasi yang ada
        durations[user_id] += (days * 86400)
    else:
        # Set durasi baru
        durations[user_id] = current_time + (days * 86400)
    save_durations(durations)

def get_formatted_members_list():
    """Format daftar member dan sisa durasi"""
    durations = load_durations()
    if not durations:
        return "Belum ada member aktif."
    
    lines = ["👥 DAFTAR MEMBER:", ""]
    current_time = time.time()
    # Sort by expiry (yang paling lama expired di bawah)
    sorted_users = sorted(durations.items(), key=lambda x: x[1])
    
    active_count = 0
    for uid, exp in sorted_users:
        days_left = (exp - current_time) / 86400
        if days_left > 0:
            status = "✅"
            active_count += 1
            lines.append(f"{status} `{uid}` : {days_left:.1f} hari")
        else:
            status = "❌"
            lines.append(f"{status} `{uid}` : EXPIRED ({abs(days_left):.1f} hari lalu)")
            
    lines.append(f"\nTotal Member Aktif: {active_count}")
    return "\n".join(lines)
