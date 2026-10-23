import json
import time
import logging
import threading
from pathlib import Path
from modules.config import USER_DATA_DIR

def read_lines(p: Path) -> list[str]:
    if not p.exists(): return []
    try: return [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    except Exception as e: logging.error(f"Gagal membaca file {p}: {e}"); return []

def write_lines(p: Path, lines: list[str]):
    try: p.write_text(("\n".join(lines) + ("\n" if lines else "")), encoding="utf-8")
    except Exception as e: logging.error(f"Gagal menulis ke file {p}: {e}")

class UserSession:
    def __init__(self, chat_id: str):
        self.chat_id = str(chat_id)
        self.run_event = threading.Event()
        self.nama_pangkalan = ""
        self.login_email = ""
        self.login_pin = ""
        self.waiting_cred = False
        self.waiting_input_akun = False
        self.waiting_del_akun = False
        self.waiting_input_nik = False  # Flag untuk input NIK via tombol
        self.showing_account_menu = False
        self.thread = None
        self.last_activity_time = time.time()  # Track waktu aktivitas terakhir
        self.consecutive_errors = 0  # Counter untuk error berturut-turut
        self.last_reset_time = 0  # Waktu terakhir reset untuk cooldown
        self.stop_requested = False  # Flag untuk sinyal stop ke worker thread
        self.reset_queue_flag = False  # Flag untuk menandakan reset antrian
        self.waiting_add_duration = False  # Flag untuk owner input durasi
        self.mode_kalem = False  # Mode kalem flag
        self.batch_msg_ids = []  # Menyimpan riwayat pesan tiap NIK
        
        # === AUTO-TRANSACTION STATE (ADEX V2) ===
        self.auto_mode = False           # Flag apakah auto-mode aktif
        self.current_phase = 1           # 1 = Fase 50%, 2 = Penghabisan
        self.auto_thread = None          # Thread daemon auto-transaction
        self.waiting_nik_auto_for = ""   # Nama akun yang sedang menunggu input NIK auto
        
        # Setup directory
        self.user_dir = USER_DATA_DIR / self.chat_id
        self.user_dir.mkdir(parents=True, exist_ok=True)
        self.cookies_dir = self.user_dir / "cookies"
        self.cookies_dir.mkdir(parents=True, exist_ok=True)
        
        # File paths
        self.accounts_file = self.user_dir / "accounts.json"
        self.nik_file = self.user_dir / "nik.txt"
        self.queue_file = self.user_dir / "nik.queue"
        self.cek_flag = self.user_dir / "cek.flag"
        
        # Init empty files if not exist
        if not self.accounts_file.exists():
            self.save_accounts({})
        if not self.nik_file.exists():
            write_lines(self.nik_file, [])

        self.filter_jenis_pelanggan = self._load_filter()

    def _load_filter(self) -> str:
        import os
        f_file = self.user_dir / "filter.json"
        if f_file.exists():
            try:
                data = json.loads(f_file.read_text(encoding="utf-8"))
                val = data.get("filter")
                if val: return val
            except Exception:
                pass
        return os.getenv("FILTER_JENIS_PELANGGAN", "RUMAH TANGGA,USAHA MIKRO")

    def set_filter(self, filter_val: str):
        self.filter_jenis_pelanggan = filter_val
        f_file = self.user_dir / "filter.json"
        try:
            f_file.write_text(json.dumps({"filter": filter_val}), encoding="utf-8")
        except Exception as e:
            logging.error(f"Gagal simpan filter.json: {e}")

    def get_filter_display(self) -> str:
        val = getattr(self, 'filter_jenis_pelanggan', "RUMAH TANGGA,USAHA MIKRO")
        if "USAHA MIKRO" in str(val).upper():
            return "RT & UMKM"
        return "RT SAJA"

    def _sanitize_filename(self, name: str) -> str:
        if not name: return ""
        return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name.upper())

    def get_cookie_path(self, account_name: str = "") -> Path:
        """
        Mendapatkan path file cookies JSON BERDASARKAN NAMA PANGKALAN / AKUN (Bukan Email).
        """
        name = account_name or self.nama_pangkalan
        if not name and self.login_email:
            accs = self.load_accounts()
            for acc_n, cred_str in accs.items():
                if self.login_email in cred_str:
                    name = acc_n
                    break
        if not name:
            name = "DEFAULT"
        safe_name = self._sanitize_filename(name)
        return self.cookies_dir / f"{safe_name}.json"

    def has_cookie(self, account_name: str = "") -> bool:
        """Cek apakah file cookie untuk akun ini sudah tersimpan"""
        p = self.get_cookie_path(account_name)
        return p.exists()

    def delete_cookie(self, account_name: str = "") -> bool:
        """Hapus file cookie untuk akun tertentu"""
        deleted = False
        candidates = [account_name, self.nama_pangkalan, self.login_email]
        for raw in candidates:
            s = self._sanitize_filename(raw)
            if s:
                p = self.cookies_dir / f"{s}.json"
                if p.exists():
                    try:
                        p.unlink(missing_ok=True)
                        deleted = True
                    except: pass
        return deleted

    def load_accounts(self) -> dict:
        if not self.accounts_file.exists(): return {}
        try:
            with open(self.accounts_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}

    def save_accounts(self, accounts: dict):
        try:
            with open(self.accounts_file, 'w', encoding='utf-8') as f:
                json.dump(accounts, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logging.error(f"[{self.chat_id}] Gagal save accounts: {e}")

    def add_account(self, name: str, email: str, pin: str) -> bool:
        accounts = self.load_accounts()
        # Hapus key lama dengan email yang sama untuk hindari entri duplikat
        to_del = []
        for old_name, cred_str in accounts.items():
            if email in str(cred_str):
                to_del.append(old_name)
        for k in to_del:
            del accounts[k]
            
        accounts[name.upper()] = f"{email}|{pin}"
        self.save_accounts(accounts)
        return True

    def delete_account(self, name: str) -> bool:
        accounts = self.load_accounts()
        if name.upper() in accounts:
            del accounts[name.upper()]
            self.save_accounts(accounts)
            return True
        return False

    def get_accounts_list(self) -> list:
        accounts = self.load_accounts()
        valid_accounts = []
        seen_emails = set()
        for name, cred in accounts.items():
            if cred and "|" in str(cred):
                parts = str(cred).split("|", 1)
                em = parts[0].strip()
                pn = parts[1].strip()
                if em and pn and "cookie_session" not in em and em not in seen_emails:
                    seen_emails.add(em)
                    valid_accounts.append((name, cred))
        return valid_accounts

    def delete_all_cookies(self):
        """Hapus seluruh file cookie tersimpan di folder cookies/ milik user ini"""
        try:
            if self.cookies_dir.exists():
                for f in self.cookies_dir.glob("*.json"):
                    try: f.unlink(missing_ok=True)
                    except Exception: pass
                logging.info(f"[{self.chat_id}] 🧹 Seluruh cookie sementara dihapus.")
        except Exception as e:
            logging.warning(f"[{self.chat_id}] Gagal hapus cookies: {e}")

    def reset_state(self, force=False):
        """Reset state, dengan proteksi terhadap reset berulang yang terlalu cepat"""
        current_time = time.time()
        
        # Jika ini bukan force reset dan baru saja direset (dalam 10 detik terakhir), skip
        if not force and (current_time - self.last_reset_time) < 10:
            logging.warning(f"[{self.chat_id}] Reset state diabaikan - baru saja reset {int(current_time - self.last_reset_time)} detik yang lalu")
            return
            
        logging.info(f"[{self.chat_id}] Resetting state...")
        self.stop_requested = True
        self.run_event.clear()
        self.nama_pangkalan = ""
        self.login_email = ""
        self.login_pin = ""
        self.waiting_cred = False
        self.waiting_input_akun = False
        self.waiting_del_akun = False
        self.waiting_input_nik = False
        self.showing_account_menu = False
        self.consecutive_errors = 0  # Reset error counter
        self.last_reset_time = current_time
        self.reset_queue_flag = True
        self.waiting_add_duration = False
        self.batch_msg_ids = []  # clear array pesan riwayat
        
        # Reset auto-transaction state
        self.auto_mode = False
        self.current_phase = 1
        self.waiting_nik_auto_for = ""
        
        # Hapus seluruh sisa cookie sementara
        self.delete_all_cookies()
        
        # Auto-cleanup file NIK & Queue saat logout/reset untuk hindari NIK tercampur antar session
        try:
            if self.nik_file.exists():
                self.nik_file.unlink(missing_ok=True)
                logging.info(f"[{self.chat_id}] ✅ File nik.txt dihapus saat reset session")
            if self.queue_file.exists():
                self.queue_file.unlink(missing_ok=True)
                logging.info(f"[{self.chat_id}] ✅ File nik.queue dihapus saat reset session")
            if self.cek_flag.exists():
                self.cek_flag.unlink(missing_ok=True)
        except Exception as e:
            logging.warning(f"[{self.chat_id}] ⚠️ Gagal hapus file NIK saat reset: {e}")

    def stop_all_processes(self):
        """Mati total seluruh proses bot (Worker, Auto-Transaction, Batch Cookie, Async Tasks)"""
        logging.info(f"[{self.chat_id}] 🛑 MEMATIKAN SELURUH PROSES BOT TOTAL...")
        self.stop_requested = True
        self.run_event.clear()
        self.auto_mode = False
        self.waiting_cred = False
        self.waiting_input_akun = False
        self.waiting_del_akun = False
        self.waiting_input_nik = False
        self.waiting_nik_auto_for = ""
        self.showing_account_menu = False
        self.reset_queue_flag = True
        
        # Hapus seluruh sisa cookie sementara
        self.delete_all_cookies()
        
        # Cleanup file queue, nik, & flag
        try:
            if self.nik_file.exists(): self.nik_file.unlink(missing_ok=True)
            if self.queue_file.exists(): self.queue_file.unlink(missing_ok=True)
            if self.cek_flag.exists(): self.cek_flag.unlink(missing_ok=True)
            logging.info(f"[{self.chat_id}] 🧹 File nik.txt, nik.queue, dan cek.flag dibersihkan total.")
        except Exception: pass
        
    def start_worker(self):
        self.stop_requested = False
        self.run_event.set()  # Pastikan event diset agar worker jalan/bangun
        if self.thread and self.thread.is_alive():
            logging.info(f"[{self.chat_id}] Worker thread sudah jalan, membangunkan...")
            return
        
        logging.info(f"[{self.chat_id}] Memulai worker thread baru...")
        # Import dynamically at runtime to avoid circular import issues
        from modules.pertamina import worker_loop
        self.thread = threading.Thread(target=worker_loop, args=(self,), daemon=True)
        self.thread.start()

    def stop_worker(self):
        self.run_event.clear()

# Global Sessions Storage
sessions: dict[str, UserSession] = {}

def get_or_create_session(chat_id: str) -> UserSession:
    chat_id = str(chat_id)
    if chat_id not in sessions:
        sessions[chat_id] = UserSession(chat_id)
    return sessions[chat_id]
