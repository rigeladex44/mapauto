"""
Auto-Transaction Module — ADEX V2
==================================
Sistem Auto-Transaction dua fase dengan NIK Circular Loop per akun.

Fase 1 : Transaksi 50% stok tiap akun (urut terbanyak → tersedikit).
Fase 2 : Penghabisan stok sampai 0.

File NIK per akun : user_dir / nik_auto_{ACCOUNT_KEY}.txt
State pointer     : user_dir / state_auto.json
"""

import re
import time
import json
import logging
import asyncio
import subprocess
import traceback
from html import escape
from pathlib import Path
from playwright.sync_api import sync_playwright
from playwright.async_api import async_playwright

from modules.config import BASE_URL, HEADLESS, is_headless, SCRIPT_DIR
from modules.session import read_lines, write_lines
from modules.telegram import (
    tg_send, tg_send_menu, tg_send_chat_action, 
    tg_edit_message, make_progress_bar
)
from modules.utils import parse_credential_line
from modules.stock import ambil_sisa_stok, cek_stok_satu_async

# ─────────────────────────────────────────────────────────
#  Konstanta
# ─────────────────────────────────────────────────────────

STATE_FILE_NAME = "state_auto.json"
JEDA_ANTAR_TRANSAKSI = 5   # detik jeda antar transaksi (sesuai planning)
JEDA_ANTAR_AKUN = 3        # detik jeda saat pindah akun
JEDA_TRANSISI_FASE = 10    # detik jeda antara Fase 1 → 2
MAX_CONSECUTIVE_FAILS = 3  # batas gagal berturut-turut (hanya notifikasi, tetap lanjut)


# ─────────────────────────────────────────────────────────
#  Helper: NIK File & Key
# ─────────────────────────────────────────────────────────

def _account_key(account_name: str) -> str:
    """Normalize nama akun menjadi key aman untuk filename."""
    return account_name.upper().replace(" ", "_").replace("/", "_")


def get_nik_auto_file(user_dir: Path, account_name: str) -> Path:
    """Return path file NIK auto untuk satu akun (global di user_data/data_nik/)."""
    from modules.config import USER_DATA_DIR
    target_dir = USER_DATA_DIR / "data_nik"
    target_dir.mkdir(parents=True, exist_ok=True)
    return target_dir / f"nik_auto_{_account_key(account_name)}.txt"


def count_nik_auto(user_dir: Path, account_name: str) -> int:
    """Hitung jumlah NIK yang tersedia untuk akun di auto-mode."""
    return len(read_lines(get_nik_auto_file(user_dir, account_name)))


# ─────────────────────────────────────────────────────────
#  Helper: State Pointer (Persistence)
# ─────────────────────────────────────────────────────────

def load_auto_state(user_dir: Path) -> dict:
    """Load pointer state dari state_auto.json."""
    state_file = user_dir / STATE_FILE_NAME
    if state_file.exists():
        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"[Auto] Gagal load state: {e}")
    return {}


def save_auto_state(user_dir: Path, state: dict):
    """Simpan pointer state ke state_auto.json (untuk resume setelah crash)."""
    state_file = user_dir / STATE_FILE_NAME
    try:
        with open(state_file, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"[Auto] Gagal save state: {e}")


def get_next_nik(account_name: str, user_dir: Path, state: dict) -> str | None:
    """
    Ambil NIK berikutnya dari file NIK akun (Circular Pointer).
    Pointer otomatis wrap ke index 0 jika sudah mencapai akhir list.
    State di-update in-place; panggil save_auto_state() setelah ini.
    Return None jika file kosong / tidak ada.
    """
    nik_file = get_nik_auto_file(user_dir, account_name)
    niks = read_lines(nik_file)
    if not niks:
        return None

    key = _account_key(account_name)
    pointer = state.get(key, {}).get("pointer", 0)

    # Guard: reset jika pointer out-of-range
    if pointer >= len(niks):
        pointer = 0

    nik = niks[pointer]

    # Advance pointer (circular wrap)
    if key not in state:
        state[key] = {}
    state[key]["pointer"] = (pointer + 1) % len(niks)

    return nik


# ─────────────────────────────────────────────────────────
#  Push Data Stok ke GitHub Pages (webapp/data.json)
# ─────────────────────────────────────────────────────────

def _push_stok_to_github(results: list):
    """Simpan hasil scan ke webapp/data.json lalu push ke GitHub (background)."""
    try:
        webapp_dir = SCRIPT_DIR / "webapp"
        data_file = webapp_dir / "data.json"
        payload = [{"name": n, "stok": s} for n, _, _, s in results]
        data_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        # Push ke GitHub Pages
        subprocess.run(
            ["git", "-C", str(webapp_dir.parent), "add", "webapp/data.json"],
            capture_output=True, timeout=10
        )
        subprocess.run(
            ["git", "-C", str(webapp_dir.parent), "commit", "-m", "📊 Update stok dashboard", "--allow-empty"],
            capture_output=True, timeout=10
        )
        subprocess.run(
            ["git", "-C", str(webapp_dir.parent), "push", "origin", "main"],
            capture_output=True, timeout=30
        )
        logging.info("[Dashboard] data.json berhasil di-push ke GitHub")
    except Exception as e:
        logging.warning(f"[Dashboard] Gagal push data.json: {e}")

# ─────────────────────────────────────────────────────────
#  Scan Stok — Live Edit Single Message Card (Battery 0-100%)
# ─────────────────────────────────────────────────────────

def scan_stok_semua_akun(accounts_list: list, session) -> list:
    """
    Scan stok semua akun secara sequential via Playwright login 1x per akun.
    Menggunakan 1 Pesan Tunggal yang Di-Edit Live (Live Card Update) 
    dengan animasi progress bar charger (0-100%).
    """
    session.stop_requested = False
    chat_id = session.chat_id
    total_acc = len(accounts_list)
    if total_acc == 0:
        return []

    from modules.pertamina import inisialisasi_sesi_akun
    from modules.stock import ambil_sisa_stok

    # Kirim 1 pesan awal yang akan di-edit live
    initial_text = (
        f"<b>📊 SCAN STOK REAL-TIME</b>\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"{make_progress_bar(0, total_acc)} (0/{total_acc} Akun)\n\n"
        f"🔍 <i>Mempersiapkan browser Playwright...</i>"
    )
    msg_id = tg_send(initial_text, chat_id=chat_id)
    results = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=is_headless())
            try:
                for idx, (account_name, cred_str) in enumerate(accounts_list, 1):
                    if getattr(session, 'stop_requested', False):
                        logging.info(f"[{session.chat_id}] Stop terdeteksi saat scan stok, membatalkan...")
                        break
                    em, pn = parse_credential_line(cred_str)
                    if not em or not pn:
                        continue
                    
                    # Update live card: scanning current account
                    if msg_id:
                        temp_results = sorted(results, key=lambda x: x[3], reverse=True)
                        lines = [
                            f"<b>📊 SCAN STOK REAL-TIME</b>",
                            "━━━━━━━━━━━━━━━━━",
                            f"{make_progress_bar(idx - 1, total_acc)} ({idx - 1}/{total_acc} Akun)\n",
                            f"⚡ <i>Scanning: {escape(account_name)}...</i>"
                        ]
                        if temp_results:
                            lines.append("")
                            for i, (nama, _, _, stok) in enumerate(temp_results, 1):
                                icon = "🟢" if stok > 0 else "⬜"
                                status = f"<b>{stok} Tabung</b>" if stok > 0 else "Kosong"
                                lines.append(f"{i}. {icon} {escape(nama)}: {status}")
                        tg_edit_message(chat_id, msg_id, "\n".join(lines))
                    
                    stok_int = 0
                    auto_sess = _AutoSession(chat_id, account_name, em, pn, user_dir=session.user_dir)
                    context, page, success = inisialisasi_sesi_akun(browser, auto_sess, account_name=account_name, silent=True)
                    try:
                        if success:
                            stok_text = ambil_sisa_stok(page)
                            m = re.search(r'(\d+)', stok_text or "")
                            stok_int = int(m.group(1)) if m else 0
                            logging.info(f"[Scan] [{account_name}] Stok live = {stok_int} Tabung")
                    except Exception as e:
                        logging.warning(f"[Scan] [{account_name}] Gagal baca stok: {e}")
                    finally:
                        auto_sess.delete_all_cookies()
                        try: context.close()
                        except Exception: pass

                    results.append((account_name, em, pn, stok_int))

                    # Update live card: account completed
                    if msg_id:
                        temp_results = sorted(results, key=lambda x: x[3], reverse=True)
                        lines = [
                            f"<b>📊 SCAN STOK REAL-TIME</b>",
                            "━━━━━━━━━━━━━━━━━",
                            f"{make_progress_bar(idx, total_acc)} ({idx}/{total_acc} Akun)\n"
                        ]
                        for i, (nama, _, _, stok) in enumerate(temp_results, 1):
                            icon = "🟢" if stok > 0 else "⬜"
                            status = f"<b>{stok} Tabung</b>" if stok > 0 else "Kosong"
                            lines.append(f"{i}. {icon} {escape(nama)}: {status}")
                        tg_edit_message(chat_id, msg_id, "\n".join(lines))
            finally:
                try: browser.close()
                except Exception: pass
    except Exception as e:
        logging.error(f"[Scan] Error scan_stok_semua_akun: {e}")

    # Final update to 100% 🔋 (Edit pesan live yang sama)
    if msg_id:
        results.sort(key=lambda x: x[3], reverse=True)
        lines = [
            f"<b>📊 SCAN STOK SELESAI</b>",
            "━━━━━━━━━━━━━━━━━",
            f"{make_progress_bar(total_acc, total_acc)} ({total_acc}/{total_acc} Akun SELESAI)\n"
        ]
        for i, (nama, _, _, stok) in enumerate(results, 1):
            icon = "🟢" if stok > 0 else "⬜"
            status = f"<b>{stok} Tabung</b>" if stok > 0 else "Kosong"
            lines.append(f"{i}. {icon} {escape(nama)}: {status}")
        tg_edit_message(chat_id, msg_id, "\n".join(lines))

    # Simpan & push data.json ke GitHub Pages (background, tidak blocking)
    if results:
        import threading
        threading.Thread(target=_push_stok_to_github, args=(results,), daemon=True).start()

    # Return hanya akun yang punya stok > 0
    return [(n, e, p, s) for n, e, p, s in results if s > 0]


# ─────────────────────────────────────────────────────────
#  Session Tiruan untuk proses_nik & login_dengan_retry
# ─────────────────────────────────────────────────────────

class _AutoSession:
    """
    Objek session minimal yang kompatibel dengan proses_nik() dan
    login_dengan_retry() di pertamina.py — digunakan di auto-mode
    agar tidak bentrok dengan session utama user.
    """
    def __init__(self, chat_id: str, account_name: str, email: str, pin: str, user_dir: Path = None):
        self.chat_id = chat_id
        self.login_email = email
        self.login_pin = pin
        self.nama_pangkalan = account_name
        self.consecutive_errors = 0
        self.last_activity_time = time.time()
        self.batch_msg_ids = []
        self.mode_kalem = False
        self._batch_dual_types = []
        self.user_dir = user_dir
        if self.user_dir:
            self.cookies_dir = self.user_dir / "cookies"
            self.cookies_dir.mkdir(parents=True, exist_ok=True)
        self.filter_jenis_pelanggan = self._load_filter()

    def _load_filter(self) -> str:
        import os
        if self.user_dir:
            f_file = self.user_dir / "filter.json"
            if f_file.exists():
                try:
                    data = json.loads(f_file.read_text(encoding="utf-8"))
                    val = data.get("filter")
                    if val: return val
                except Exception:
                    pass
        return os.getenv("FILTER_JENIS_PELANGGAN", "RUMAH TANGGA,USAHA MIKRO")

    def get_filter_display(self) -> str:
        val = getattr(self, 'filter_jenis_pelanggan', "RUMAH TANGGA,USAHA MIKRO")
        if "USAHA MIKRO" in str(val).upper():
            return "RT & UMKM"
        return "RT SAJA"

    def get_cookie_path(self, account_name: str = "") -> Path:
        name = account_name or self.nama_pangkalan or "default"
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name.upper())
        if hasattr(self, 'cookies_dir') and self.cookies_dir:
            return self.cookies_dir / f"{safe_name}.json"
        from modules.config import USER_DATA_DIR
        return USER_DATA_DIR / self.chat_id / "cookies" / f"{safe_name}.json"

    def delete_all_cookies(self):
        try:
            if hasattr(self, 'cookies_dir') and self.cookies_dir and self.cookies_dir.exists():
                for f in self.cookies_dir.glob("*.json"):
                    try: f.unlink(missing_ok=True)
                    except Exception: pass
        except Exception: pass

    def delete_cookie(self, account_name: str = ""):
        try:
            p = self.get_cookie_path(account_name)
            if p.exists(): p.unlink(missing_ok=True)
        except Exception: pass


# ─────────────────────────────────────────────────────────
#  Proses Satu Akun (Fase 1 atau Fase 2)
# ─────────────────────────────────────────────────────────

def proses_akun_auto(
    account_name: str,
    email: str,
    pin: str,
    target_proses: int,
    session,           # UserSession asli (untuk auto_mode flag & user_dir)
    state: dict,
    phase: int
) -> dict:
    """
    Proses satu akun dalam auto-mode (Fase 1 atau Fase 2).

    phase=1 : berhenti setelah processed_count >= target_proses
    phase=2 : berhenti setelah stok = 0 (target_proses = perkiraan awal)

    Safety   : jika gagal/limit 3x berturut-turut → tetap lanjut proses, notifikasi TG.
    Jeda     : 5 detik antar transaksi.

    Return dict: {"sukses": N, "gagal": N, "limit": N, "stok_akhir": "X Tabung"}
    """
    chat_id = session.chat_id
    user_dir = session.user_dir
    result = {"sukses": 0, "gagal": 0, "limit": 0, "stok_akhir": "?"}

    # ── Cek ketersediaan NIK ──────────────────────────────
    nik_count = count_nik_auto(user_dir, account_name)
    if nik_count == 0:
        tg_send(
            f"⚠️ [{account_name}] File NIK auto kosong / tidak ada!\n"
            f"Tambah NIK via tombol '📋 SET NIK AUTO'. Akun di-skip.",
            chat_id=chat_id
        )
        return result

    phase_icon = "🔵" if phase == 1 else "🔴"
    phase_label = "50%" if phase == 1 else "Penghabisan"
    tg_send(
        f"{phase_icon} [{account_name}] Fase {phase} ({phase_label})\n"
        f"Target   : ≈{target_proses if target_proses < 9999 else 'Maksimal'} transaksi\n"
        f"NIK file : {nik_count} entri",
        chat_id=chat_id
    )

    consecutive_fails = 0
    processed_count = 0
    idx = 0

    # ── Import di dalam fungsi untuk hindari circular import ──
    from modules.pertamina import login_dengan_retry, inisialisasi_sesi_akun, proses_nik, kembali_ke_beranda

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=is_headless())
            auto_sess = _AutoSession(chat_id, account_name, email, pin, user_dir=user_dir)
            context, page, success = inisialisasi_sesi_akun(browser, auto_sess, account_name=account_name)

            try:
                # Login / Cookie init check
                if not success:
                    tg_send(f"❌ [{account_name}] Login gagal. Skip akun ini.", chat_id=chat_id)
                    return result

                # Baca sisa stok langsung dari beranda/dashboard setelah login
                from modules.stock import ambil_sisa_stok
                stok_login_text = None
                current_stok = 0
                try:
                    stok_login_text = ambil_sisa_stok(page)
                    m = re.search(r'(\d+)', stok_login_text or "")
                    current_stok = int(m.group(1)) if m else 0
                except Exception as e:
                    logging.warning(f"[Auto] [{account_name}] Gagal membaca stok dashboard: {e}")

                if current_stok <= 0 and "tabung" not in str(stok_login_text).lower():
                    logging.info(f"[Auto] [{account_name}] Stok kosong ({stok_login_text or '0 Tabung'}). Skip akun ini.")
                    tg_send(f"📦 [{account_name}] Stok kosong ({stok_login_text or '0 Tabung'}). Skip.", chat_id=chat_id)
                    result["stok_akhir"] = stok_login_text or "0 Tabung"
                    return result

                # Jika target_proses == 0 (Fase 1), tentukan target 50% stok secara dinamis dari dashboard
                if target_proses == 0:
                    target_proses = max(1, current_stok // 2)
                    logging.info(f"[Auto] [{account_name}] Target 50% dinamis: {target_proses} transaksi (Stok: {current_stok})")

                # ── Loop transaksi ────────────────────────────
                while session.auto_mode:

                    # Cek target Fase 1
                    if phase == 1 and processed_count >= target_proses:
                        logging.info(f"[Auto] [{account_name}] Target Fase 1 tercapai ({processed_count}/{target_proses})")
                        break

                    # Cek stok real-time setiap 10 transaksi
                    if idx > 0 and idx % 10 == 0:
                        try:
                            kembali_ke_beranda(page)
                            stok_text = ambil_sisa_stok(page)
                            m = re.search(r'(\d+)', stok_text or "")
                            current_stok = int(m.group(1)) if m else 0
                            if current_stok == 0:
                                result["stok_akhir"] = "0 Tabung"
                                logging.info(f"[Auto] [{account_name}] Stok sudah 0, berhenti.")
                                break
                        except Exception as e:
                            logging.warning(f"[Auto] [{account_name}] Gagal cek stok real-time: {e}")

                    # Ambil NIK berikutnya (Circular Pointer)
                    nik = get_next_nik(account_name, user_dir, state)
                    if nik is None:
                        tg_send(f"⚠️ [{account_name}] NIK habis (file kosong). Stop.", chat_id=chat_id)
                        break

                    # Simpan state pointer SEBELUM proses (recovery dari crash)
                    save_auto_state(user_dir, state)

                    # Proses NIK
                    idx += 1
                    ok, status = proses_nik(page, nik, idx, auto_sess)

                    if ok:
                        result["sukses"] += 1
                        processed_count += 1
                        consecutive_fails = 0
                    elif status == "LIMIT":
                        result["limit"] += 1
                        consecutive_fails += 1
                    elif status == "STOK_HABIS":
                        result["stok_akhir"] = "0 Tabung"
                        break
                    else:
                        result["gagal"] += 1
                        consecutive_fails += 1
                        try:
                            logging.info(f"[{account_name}] Gagal/ERROR (Status: {status}). Merefresh halaman...")
                            page.reload(timeout=20000)
                            time.sleep(3)
                            if 'login' in page.url:
                                logging.warning(f"[{account_name}] Terdeteksi logout setelah refresh. Relogin...")
                                if not login_dengan_retry(page, auto_sess):
                                    logging.error(f"[{account_name}] Relogin gagal. Lanjut ke akun berikutnya.")
                                    break
                        except Exception as e:
                            logging.warning(f"[{account_name}] Gagal reload halaman: {e}")

                    # Safety: 3x gagal berturut → tetap lanjut sesuai target
                    if consecutive_fails >= MAX_CONSECUTIVE_FAILS:
                        tg_send(
                            f"⚠️ [{account_name}] Gagal/Limit {MAX_CONSECUTIVE_FAILS}x berturut-turut!\n"
                            f"Tetap melanjutkan proses akun hingga sesuai target awal.",
                            chat_id=chat_id
                        )
                        consecutive_fails = 0

                    # Jeda antar transaksi
                    time.sleep(JEDA_ANTAR_TRANSAKSI)

                # ── Ambil stok akhir setelah loop selesai ────
                try:
                    kembali_ke_beranda(page)
                    stok_akhir_text = ambil_sisa_stok(page)
                    result["stok_akhir"] = stok_akhir_text
                except Exception:
                    pass

            finally:
                try:
                    auto_sess.delete_all_cookies()
                    context.close()
                    browser.close()
                except Exception:
                    pass

    except Exception as e:
        logging.error(f"[Auto] [{account_name}] Error tak terduga: {e}\n{traceback.format_exc()}")
        tg_send(f"❌ [{account_name}] Error: {e}", chat_id=chat_id)

    # Simpan state pointer setelah selesai
    save_auto_state(user_dir, state)

    # ── Kirim laporan per akun ke Telegram ───────────────
    lines = [
        f"📋 LAPORAN [{account_name}] — Fase {phase}",
        "━━━━━━━━━━━━━━━━━",
        f"✅ Sukses     : {result['sukses']}",
        f"❌ Gagal      : {result['gagal']}",
        f"⛔ Limit      : {result['limit']}",
        f"📦 Stok Akhir : {result['stok_akhir']}",
    ]
    tg_send("\n".join(lines), chat_id=chat_id)

    return result


# ─────────────────────────────────────────────────────────
#  Orkestrator Utama
# ─────────────────────────────────────────────────────────

def run_auto_transaction(session):
    """
    Orkestrator utama Auto-Transaction dua fase (ADEX V2).
    Dipanggil di background daemon thread dari BOT1_CAPTCHA.py.

    Alur:
      Fase 1 (50%) → notif → Fase 2 (Penghabisan) → selesai.
    """
    chat_id = session.chat_id
    user_dir = session.user_dir

    try:
        # Load state pointer (resume dari crash jika ada)
        state = load_auto_state(user_dir)

        # Ambil semua akun user
        accounts_list = session.get_accounts_list()
        if not accounts_list:
            tg_send_menu("📭 Belum ada akun tersimpan. Auto-mode batal.", chat_id=chat_id)
            session.auto_mode = False
            return

        # ══════════════════════════════════════════════════
        #  SCAN STOK AWAL
        # ══════════════════════════════════════════════════
        accounts_with_stok = scan_stok_semua_akun(accounts_list, session)

        if not accounts_with_stok:
            tg_send_menu(
                "📦 Tidak ada akun yang memiliki stok.\nAuto-mode selesai.",
                chat_id=chat_id
            )
            session.auto_mode = False
            return

        # ══════════════════════════════════════════════════
        #  FASE 1: 50% STOK PER AKUN
        # ══════════════════════════════════════════════════
        session.current_phase = 1
        tg_send(
            f"▶️ FASE 1 DIMULAI (Target 50% Stok)\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"Akun dengan stok : {len(accounts_with_stok)} akun",
            chat_id=chat_id
        )

        for account_name, email, pin, stok in accounts_with_stok:
            if not session.auto_mode:
                break

            target = max(1, stok // 2)
            proses_akun_auto(account_name, email, pin, target_proses=target, session=session, state=state, phase=1)

            if not session.auto_mode:
                break
            time.sleep(JEDA_ANTAR_AKUN)

        # Cek apakah dibatalkan user
        if not session.auto_mode:
            tg_send_menu("🛑 Auto-Transaction dibatalkan oleh user.", chat_id=chat_id)
            session.current_phase = 1
            return

        # ── Transisi Fase 1 → Fase 2 ─────────────────────
        tg_send(
            f"✅ FASE 1 SELESAI!\n\n"
            f"⏳ Memulai Fase 2 (Penghabisan)\n"
            f"dalam {JEDA_TRANSISI_FASE} detik...",
            chat_id=chat_id
        )
        time.sleep(JEDA_TRANSISI_FASE)

        # ══════════════════════════════════════════════════
        #  FASE 2: PENGHABISAN STOK
        # ══════════════════════════════════════════════════
        session.current_phase = 2
        tg_send("▶️ FASE 2 DIMULAI (Penghabisan Stok)", chat_id=chat_id)

        # Re-scan stok real-time sebelum Fase 2
        accounts_f2 = scan_stok_semua_akun(accounts_list, session)

        for account_name, email, pin, stok in accounts_f2:
            if not session.auto_mode:
                break

            proses_akun_auto(account_name, email, pin, target_proses=9999, session=session, state=state, phase=2)

            if not session.auto_mode:
                break
            time.sleep(JEDA_ANTAR_AKUN)

        if not session.auto_mode:
            tg_send_menu("🛑 Auto-Transaction dibatalkan di Fase 2.", chat_id=chat_id)
            session.current_phase = 1
            return

        # ══════════════════════════════════════════════════
        #  SELESAI
        # ══════════════════════════════════════════════════
        session.auto_mode = False
        session.current_phase = 1
        tg_send_menu(
            "╔══════════════════════╗\n"
            "║ ✅ AUTO-TRANSACTION  ║\n"
            "║      SELESAI!        ║\n"
            "║  Stok habis (0).     ║\n"
            "╚══════════════════════╝",
            chat_id=chat_id
        )

    except Exception as e:
        logging.error(f"[Auto] run_auto_transaction error: {e}\n{traceback.format_exc()}")
        tg_send_menu(f"❌ Auto-Transaction error: {e}", chat_id=chat_id)
        session.auto_mode = False
        session.current_phase = 1
