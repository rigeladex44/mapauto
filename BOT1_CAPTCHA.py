import os
import sys
import time
import datetime
import logging
import threading
import traceback
import requests
import json
import ssl
import urllib3
from pathlib import Path

# --- BYPASS SSL GLOBALLY UNTUK VPS LAMA ---
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
original_request = requests.Session.request
def request_patch(self, method, url, **kwargs):
    kwargs['verify'] = False
    return original_request(self, method, url, **kwargs)
requests.Session.request = request_patch
# ------------------------------------------

# Import our custom modules
from modules.config import BOT_TOKEN, OWNER_ID, SCRIPT_NAME, SCRIPT_DIR, QRIS_FILE, BOT_NAME
from modules.duration import check_user_duration, add_user_duration, get_formatted_members_list, load_durations
from modules.session import get_or_create_session, read_lines, write_lines
from modules.utils import normalize_cmd, normalize_button_text, parse_credential_line, clear_terminal, clear_terminal_and_logs
from modules.telegram import (
    tg_send, tg_send_menu, tg_send_inline_menu, tg_send_photo, 
    tg_send_document, send_welcome_banner, ensure_token_ok,
    tg_send_chat_action, tg_answer_callback, tg_edit_message
)
from modules.stock import run_cek_stok_data
from modules.auto_transaction import (
    run_auto_transaction, get_nik_auto_file, count_nik_auto,
    load_auto_state, _account_key
)

LAST_UPDATE_ID = None

# ===================== POLLING THREAD =====================
def bot_polling_loop():
    global LAST_UPDATE_ID
    base = f"https://api.telegram.org/bot{BOT_TOKEN}"
    consecutive_timeouts = 0
    max_consecutive_timeouts = 5
    
    while True:
        try:
            r = requests.get(
                f"{base}/getUpdates", 
                params={
                    "timeout": 50, 
                    "offset": (LAST_UPDATE_ID + 1) if LAST_UPDATE_ID else None
                }, 
                timeout=70
            )
            consecutive_timeouts = 0
            data = r.json() if 'application/json' in r.headers.get('content-type', '') else {}
            for upd in data.get("result", []):
                LAST_UPDATE_ID = upd.get("update_id", LAST_UPDATE_ID)
                
                # Handle callback query
                callback_query = upd.get("callback_query")
                if callback_query:
                    cb_id = callback_query.get("id")
                    callback_data = callback_query.get("data", "")
                    from_user = callback_query.get("from", {})
                    callback_chat_id = str(from_user.get("id", ""))
                    session = get_or_create_session(callback_chat_id)
                    
                    if callback_data == "sudah_transfer":
                        tg_answer_callback(cb_id, "📨 Konfirmasi terkirim ke admin!")
                        tg_send(f"📨 Konfirmasi pembayaran dari user {callback_chat_id}\n\nSilakan verifikasi dan tambah durasi dengan:\n/add_duration {callback_chat_id} DAYS", chat_id=OWNER_ID)
                        tg_send_menu("✅ Konfirmasi pembayaran telah dikirim ke owner. Durasi akan ditambahkan setelah verifikasi.", chat_id=callback_chat_id)
                    elif callback_data == "show_accounts_list":
                        tg_answer_callback(cb_id, "📋 Memuat daftar akun...")
                        accounts_list = session.get_accounts_list()
                        if accounts_list:
                            inline_buttons = [
                                [
                                    {"text": "WhatsApp", "url": "https://wa.me/6285155058577?Hallo%20*ADEX%IDN*!!!%0ABot%20Telegram%20Premium."}, 
                                    {"text": "Telegram", "url": "https://t.me/mhengkyy"}
                                ]
                            ]
                            for name, _ in accounts_list:
                                has_cookie = session.has_cookie(name)
                                cookie_badge = "🍪 Cookie (Bypassed Login)" if has_cookie else "🔑 Login Manual"
                                inline_buttons.append([{"text": f"👤 {name} ({cookie_badge})", "callback_data": f"select_account_{name}"}])
                            
                            try:
                                message_id = upd.get("callback_query", {}).get("message", {}).get("message_id")
                                if message_id:
                                    requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageReplyMarkup",
                                                data={"chat_id": callback_chat_id, "message_id": message_id, "reply_markup": json.dumps({"inline_keyboard": inline_buttons})},
                                                timeout=10)
                            except:
                                pass
                    elif callback_data.startswith("select_account_"):
                        account_name = callback_data.replace("select_account_", "")
                        tg_answer_callback(cb_id, f"🔑 Memproses [{account_name}]...")
                        tg_send_chat_action(callback_chat_id, "typing")
                        accounts_list = session.get_accounts_list()
                        accounts_map = {name.upper(): (name, cred) for (name, cred) in accounts_list}
                        if account_name.upper() in accounts_map:
                            actual_name, cred = accounts_map[account_name.upper()]
                            em, pn = parse_credential_line(cred)
                            if em and pn:
                                is_valid, dur_msg = check_user_duration(callback_chat_id)
                                if not is_valid:
                                    tg_send_menu(dur_msg, chat_id=callback_chat_id)
                                else:
                                    session.nama_pangkalan = actual_name
                                    session.login_email = em
                                    session.login_pin = pn
                                    session.waiting_cred = False
                                    session.showing_account_menu = False
                                    
                                    # Pastikan file antrian lama dibersihkan total untuk akun baru ini
                                    try:
                                        if session.nik_file.exists(): session.nik_file.unlink(missing_ok=True)
                                        if session.queue_file.exists(): session.queue_file.unlink(missing_ok=True)
                                    except Exception: pass
                                    session.reset_queue_flag = True
                                    
                                    login_msg = f"🔑 Memulai login [{actual_name}]...\n(Mengisi Email & PIN...)"
                                    
                                    try:
                                        message_id = upd.get("callback_query", {}).get("message", {}).get("message_id")
                                        if message_id:
                                            requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessage",
                                                        data={"chat_id": callback_chat_id, "message_id": message_id},
                                                        timeout=10)
                                    except Exception as e:
                                        logging.debug(f"Gagal menghapus pesan pemilihan akun: {e}")
                                    
                                    tg_send_menu(login_msg, chat_id=callback_chat_id)
                                    session.start_worker()
                    elif callback_data == "admin_list_members":
                        if callback_chat_id == OWNER_ID:
                            msg_list = get_formatted_members_list()
                            tg_send(msg_list, chat_id=OWNER_ID)
                    elif callback_data == "admin_add_duration":
                        if callback_chat_id == OWNER_ID:
                            session.waiting_add_duration = True
                            tg_send("➕ Kirim ID User dan Durasi (Hari).\nContoh: `123456789 30`\n\nKetik 'CANCEL' untuk batal.", chat_id=OWNER_ID)
                    elif callback_data == "admin_clear_terminal":
                        if callback_chat_id == OWNER_ID:
                            clear_terminal_and_logs()
                            tg_send("🧹 Terminal VPS & Log berhasil dibersihkan!", chat_id=OWNER_ID)
                    elif callback_data.startswith("set_nik_auto_"):
                        # ── Menu Pilihan Opsi untuk Satu Akun Auto ──
                        account_name = callback_data.replace("set_nik_auto_", "", 1)
                        is_valid, _ = check_user_duration(callback_chat_id)
                        if not is_valid and callback_chat_id != OWNER_ID:
                            tg_send("❌ Durasi expired.", chat_id=callback_chat_id)
                        else:
                            nik_count = count_nik_auto(session.user_dir, account_name)
                            has_cookie = session.has_cookie(account_name)
                            cookie_status = "🟢 Active (Bypassed Login)" if has_cookie else "⚠️ Belum Ada / Expired"
                            
                            sub_buttons = [
                                [{"text": "➕ Tambah NIK Auto", "callback_data": f"add_nik_auto_{account_name}"}],
                                [{"text": "🗑️ Reset NIK Auto", "callback_data": f"reset_nik_auto_{account_name}"}],
                                [{"text": "🍪 Reset Cookie Akun", "callback_data": f"reset_cookie_{account_name}"}],
                                [{"text": "🔙 Kembali ke Daftar Akun", "callback_data": "back_to_accounts"}]
                            ]
                            
                            message_id = callback_query.get("message", {}).get("message_id")
                            text = (
                                f"⚙️ **MENU AKUN AUTO**: {account_name}\n"
                                f"━━━━━━━━━━━━━━━━━\n"
                                f"📦 Jumlah NIK : {nik_count} entri\n"
                                f"🍪 Status Sesi : {cookie_status}\n\n"
                                f"Pilih tindakan di bawah ini:"
                            )
                            if message_id:
                                tg_edit_message(callback_chat_id, message_id, text, reply_markup={"inline_keyboard": sub_buttons})
                            else:
                                tg_send_inline_menu(text, sub_buttons, callback_chat_id)
                    elif callback_data == "back_to_accounts":
                        tg_answer_callback(cb_id, "🔙 Kembali...")
                        accounts_list = session.get_accounts_list()
                        if accounts_list:
                            inline_buttons = []
                            for acc_name, _ in accounts_list:
                                nik_count = count_nik_auto(session.user_dir, acc_name)
                                cookie_icon = "🍪" if session.has_cookie(acc_name) else "🔑"
                                status_nik = f"{nik_count} NIK" if nik_count > 0 else "Belum ada NIK"
                                inline_buttons.append([
                                    {"text": f"👤 {acc_name} ({cookie_icon} | {status_nik})",
                                     "callback_data": f"set_nik_auto_{acc_name}"}
                                ])
                            message_id = callback_query.get("message", {}).get("message_id")
                            if message_id:
                                text = (
                                    "📋 **PILIH AKUN AUTO-TRANSACTION**\n"
                                    "━━━━━━━━━━━━━━━━━\n"
                                    " Indikator:\n"
                                    "🍪 = Cookie Sesi Aktif (Direct Login)\n"
                                    "🔑 = Login Manual (Pin/Email)\n\n"
                                    "Tap nama akun di bawah untuk kelola NIK & Cookie:"
                                )
                                tg_edit_message(callback_chat_id, message_id, text, reply_markup={"inline_keyboard": inline_buttons})
                    elif callback_data.startswith("add_nik_auto_"):
                        account_name = callback_data.replace("add_nik_auto_", "", 1)
                        session.waiting_nik_auto_for = account_name
                        nik_count = count_nik_auto(session.user_dir, account_name)
                        tg_send(
                            f"📋 Input NIK Auto untuk akun:\n"
                            f"👤 {account_name}\n"
                            f"NIK saat ini: {nik_count} entri\n\n"
                            f"Kirim NIK (satu per baris, min 12 digit).\n"
                            f"NIK baru akan DITAMBAHKAN ke list yang ada.",
                            chat_id=callback_chat_id
                        )
                    elif callback_data.startswith("reset_nik_auto_"):
                        account_name = callback_data.replace("reset_nik_auto_", "", 1)
                        tg_answer_callback(cb_id, "🗑️ NIK Auto direset!")
                        nik_file = get_nik_auto_file(session.user_dir, account_name)
                        write_lines(nik_file, [])
                        state = load_auto_state(session.user_dir)
                        key = _account_key(account_name)
                        if key in state:
                            state[key]["pointer"] = 0
                            from modules.auto_transaction import save_auto_state
                            save_auto_state(session.user_dir, state)
                        session.waiting_nik_auto_for = ""
                        message_id = callback_query.get("message", {}).get("message_id")
                        if message_id:
                            has_cookie = session.has_cookie(account_name)
                            cookie_status = "🟢 Active (Bypassed Login)" if has_cookie else "⚠️ Belum Ada / Expired"
                            sub_buttons = [
                                [{"text": "➕ Tambah NIK Auto", "callback_data": f"add_nik_auto_{account_name}"}],
                                [{"text": "🗑️ Reset NIK Auto", "callback_data": f"reset_nik_auto_{account_name}"}],
                                [{"text": "🍪 Reset Cookie Akun", "callback_data": f"reset_cookie_{account_name}"}],
                                [{"text": "🔙 Kembali ke Daftar Akun", "callback_data": "back_to_accounts"}]
                            ]
                            text = (
                                f"⚙️ **MENU AKUN AUTO**: {account_name}\n"
                                f"━━━━━━━━━━━━━━━━━\n"
                                f"📦 Jumlah NIK : 0 entri\n"
                                f"🍪 Status Sesi : {cookie_status}\n\n"
                                f"Pilih tindakan di bawah ini:"
                            )
                            tg_edit_message(callback_chat_id, message_id, text, reply_markup={"inline_keyboard": sub_buttons})
                    elif callback_data.startswith("reset_cookie_"):
                        account_name = callback_data.replace("reset_cookie_", "", 1)
                        deleted = session.delete_cookie(account_name)
                        tg_answer_callback(cb_id, "🍪 Cookie dihapus!" if deleted else "ℹ️ Belum ada cookie")
                        message_id = callback_query.get("message", {}).get("message_id")
                        if message_id:
                            nik_count = count_nik_auto(session.user_dir, account_name)
                            sub_buttons = [
                                [{"text": "➕ Tambah NIK Auto", "callback_data": f"add_nik_auto_{account_name}"}],
                                [{"text": "🗑️ Reset NIK Auto", "callback_data": f"reset_nik_auto_{account_name}"}],
                                [{"text": "🍪 Reset Cookie Akun", "callback_data": f"reset_cookie_{account_name}"}],
                                [{"text": "🔙 Kembali ke Daftar Akun", "callback_data": "back_to_accounts"}]
                            ]
                            text = (
                                f"⚙️ **MENU AKUN AUTO**: {account_name}\n"
                                f"━━━━━━━━━━━━━━━━━\n"
                                f"📦 Jumlah NIK : {nik_count} entri\n"
                                f"🍪 Status Sesi : ⚠️ Belum Ada / Expired\n\n"
                                f"Pilih tindakan di bawah ini:"
                            )
                            tg_edit_message(callback_chat_id, message_id, text, reply_markup={"inline_keyboard": sub_buttons})
                    elif callback_data == "set_filter_rt":
                        session.set_filter("RUMAH TANGGA")
                        tg_answer_callback(cb_id, "✅ Filter: 🏠 RT SAJA")
                        message_id = callback_query.get("message", {}).get("message_id")
                        if message_id:
                            inline_filter_btns = [
                                [
                                    {"text": "🏠 RT SAJA", "callback_data": "set_filter_rt"},
                                    {"text": "🏠🏢 RT & UMKM", "callback_data": "set_filter_rt_um"}
                                ]
                            ]
                            tg_edit_message(
                                callback_chat_id,
                                message_id,
                                f"🎯 **Pilihan Filter Pelanggan** (Aktif: 🏠 RUMAH TANGGA SAJA):",
                                reply_markup={"inline_keyboard": inline_filter_btns}
                            )
                    elif callback_data == "set_filter_rt_um":
                        session.set_filter("RUMAH TANGGA,USAHA MIKRO")
                        tg_answer_callback(cb_id, "✅ Filter: 🏠🏢 RT & UMKM")
                        message_id = callback_query.get("message", {}).get("message_id")
                        if message_id:
                            inline_filter_btns = [
                                [
                                    {"text": "🏠 RT SAJA", "callback_data": "set_filter_rt"},
                                    {"text": "🏠🏢 RT & UMKM", "callback_data": "set_filter_rt_um"}
                                ]
                            ]
                            tg_edit_message(
                                callback_chat_id,
                                message_id,
                                f"🎯 **Pilihan Filter Pelanggan** (Aktif: 🏠🏢 RUMAH TANGGA & USAHA MIKRO):",
                                reply_markup={"inline_keyboard": inline_filter_btns}
                            )
                    continue
                
                msg = upd.get("message") or upd.get("edited_message") or {}
                text_raw = (msg.get("text") or "").strip()
                chat_id = str((msg.get("chat") or {}).get("id") or "")
                if not chat_id: continue
                
                session = get_or_create_session(chat_id)
                text = normalize_cmd(text_raw)
                low = text.lower()
                
                # Anti-spam check
                if chat_id != OWNER_ID:
                    durations = load_durations()
                    if chat_id not in durations:
                        username = (msg.get("from") or {}).get("username") or "No Username"
                        send_welcome_banner(chat_id, msg.get("from", {}), "❌ Durasi belum diaktifkan.", False)
                        tg_send(f"🚨 User tidak terdaftar mencoba akses bot:\nID: {chat_id}\nUsername: @{username}\nPesan: {text_raw[:100]}", chat_id=OWNER_ID)
                        continue
                
                if chat_id == OWNER_ID and low.startswith("/add_duration"):
                    parts = text_raw.split()
                    if len(parts) >= 3:
                        try:
                            target_user_id = parts[1]
                            days = int(parts[2])
                            add_user_duration(target_user_id, days)
                            tg_send(f"✅ Durasi {days} hari ditambahkan untuk user {target_user_id}", chat_id=OWNER_ID)
                            is_valid, dur_msg = check_user_duration(target_user_id)
                            tg_send(f"✅ Durasi Anda telah diperpanjang!\n\n{dur_msg}", chat_id=target_user_id)
                        except Exception as e:
                            tg_send(f"❌ Error: {e}", chat_id=OWNER_ID)
                    else:
                        tg_send("Format: /add_duration USER_ID DAYS", chat_id=OWNER_ID)
                    continue
                
                if chat_id == OWNER_ID and session.waiting_add_duration:
                    if low == "cancel" or low == "kembali":
                        session.waiting_add_duration = False
                        tg_send_menu("Batal tambah durasi.", chat_id=OWNER_ID)
                        continue
                        
                    parts = text_raw.split()
                    if len(parts) >= 2:
                        try:
                            target_user_id = parts[0]
                            days = int(parts[1])
                            add_user_duration(target_user_id, days)
                            session.waiting_add_duration = False
                            tg_send(f"✅ Durasi {days} hari ditambahkan untuk user {target_user_id}", chat_id=OWNER_ID)
                            is_valid, dur_msg = check_user_duration(target_user_id)
                            tg_send(f"✅ Durasi Anda telah diperpanjang oleh Admin!\n\n{dur_msg}", chat_id=target_user_id)
                        except ValueError:
                            tg_send("❌ Format salah. Harusnya angka semua.\nContoh: `123456789 30`", chat_id=OWNER_ID)
                        except Exception as e:
                            tg_send(f"❌ Error: {e}", chat_id=OWNER_ID)
                    else:
                        tg_send("❌ Format salah. Kirim: ID HARI\nContoh: `123456789 30`", chat_id=OWNER_ID)
                    continue

                if chat_id == OWNER_ID and text_raw.strip() == "👑 ADMIN PANEL":
                    buttons = [
                        [{"text": "👥 List Member", "callback_data": "admin_list_members"}],
                        [{"text": "➕ Tambah Durasi", "callback_data": "admin_add_duration"}],
                        [{"text": "🧹 Clear Terminal VPS", "callback_data": "admin_clear_terminal"}],
                    ]
                    tg_send_inline_menu("👑 **ADMIN PANEL**\nPilih menu:", buttons, chat_id=OWNER_ID)
                    continue
                
                if text_raw.strip().upper() == "SUDAH TRANSFER":
                    tg_send(f"📨 Ada yang transfer nih, ID: {chat_id}\n\nCek mutasi terus kasih durasi ya:\n/add_duration {chat_id} HARI", chat_id=OWNER_ID)
                    tg_send_menu("✅ Sip! Konfirmasi udah dikirim ke owner. Tunggu bentar ya, nanti dikabarin kalau durasi udah nambah.", chat_id=chat_id)
                    continue
                
                allowed_without_duration = [
                    "cek durasi", "perpanjang", "lanjut proses botmap",
                    "refresh/reset bot", "/start", "/status", "status", "/add_duration", "kembali",
                    "/clear", "/clear_log", "/clear_terminal", "clear terminal", "clear log"
                ]
                if not any(cmd in low for cmd in allowed_without_duration) and not session.waiting_input_akun and not session.waiting_del_akun:
                    is_valid, dur_msg = check_user_duration(chat_id)
                    if not is_valid:
                        username = (msg.get("from") or {}).get("username") or "No Username"
                        tg_send(f"⏰ User durasi EXPIRED mencoba akses:\nID: {chat_id}\nUsername: @{username}\nStatus: {dur_msg}", chat_id=OWNER_ID)
                        tg_send_menu(dur_msg, chat_id=chat_id)
                        continue
                
                if (session.waiting_input_akun or session.waiting_del_akun) and (low.startswith("/cancel") or text_raw.strip().upper() == "CANCEL" or text_raw.strip().upper() == "KEMBALI"):
                    session.waiting_input_akun = False
                    session.waiting_del_akun = False
                    session.showing_account_menu = True
                    tg_send_menu("Oke, batal.", chat_id=chat_id, show_account_menu=True)
                    continue
                
                if session.waiting_del_akun and not low.startswith("/"):
                    name_to_delete = text_raw.strip().upper()
                    if session.delete_account(name_to_delete):
                        session.waiting_del_akun = False
                        tg_send_menu(f"🗑️ Akun '{name_to_delete}' udah dihapus!", chat_id=chat_id, show_account_menu=True)
                    else:
                        tg_send("❌ Gak nemu nama akun itu. Coba lagi atau ketik KEMBALI.", chat_id=chat_id)
                    continue
                
                if session.waiting_input_akun and not low.startswith("/"):
                    lines = text_raw.splitlines()
                    added_count = 0
                    parsed_items = []
                    failed_lines = []
                    
                    for line in lines:
                        line = line.strip()
                        if not line: continue
                        
                        parts = line.rsplit(None, 1)
                        if len(parts) == 2:
                            name_part = parts[0].strip()
                            cred_part = parts[1].strip()
                            
                            if "|" in cred_part:
                                em, pn = parse_credential_line(cred_part)
                                if em and pn:
                                    session.add_account(name_part, em, pn)
                                    parsed_items.append((name_part, em, pn))
                                    added_count += 1
                                else:
                                    failed_lines.append(line)
                            else:
                                failed_lines.append(line)
                        elif "|" in line:
                            em, pn = parse_credential_line(line)
                            if em and pn:
                                auto_name = em.split("@")[0].upper()
                                session.add_account(auto_name, em, pn)
                                parsed_items.append((auto_name, em, pn))
                                added_count += 1
                            else:
                                failed_lines.append(line)
                        else:
                            failed_lines.append(line)
                    
                    if added_count > 0:
                        session.waiting_input_akun = False
                        fail_msg = f"\n⚠️ Skip {len(failed_lines)} baris karena format salah." if failed_lines else ""
                        tg_send_menu(
                            f"✅ **{added_count} AKUN BERHASIL DISIMPAN!**\n"
                            f"━━━━━━━━━━━━━━━━━\n"
                            f"Data akun telah tersimpan di sistem.{fail_msg}\n\n"
                            f"Gunakan menu 'PROSES AKUN' untuk mulai menjalankan transaksi.",
                            chat_id=chat_id,
                            show_account_menu=True
                        )
                    else:
                        tg_send("❌ Gagal menyimpan. Pastikan formatnya benar:\nNAMA email|pin\natau\nemail|pin", chat_id=chat_id)
                    continue
                
                if "|" in text and not low.startswith("/") and not session.waiting_input_akun and not session.waiting_del_akun:
                    em, pn = parse_credential_line(text)
                    if em and pn:
                        if session.run_event.is_set():
                            tg_send("🔴 Bot lagi jalan nih. LOGOUT dulu kalau mau ganti akun.", chat_id=chat_id)
                        else:
                            is_valid, dur_msg = check_user_duration(chat_id)
                            if not is_valid:
                                tg_send_menu(dur_msg, chat_id=chat_id, show_account_menu=True)
                                continue
                            session.login_email = em
                            session.login_pin = pn
                            session.waiting_cred = False
                            session.showing_account_menu = False
                            tg_send("✅ Data diterima!\n🔄 Memulai proses login...", chat_id=chat_id)
                            session.start_worker()
                    continue

                if session.waiting_cred and not low.startswith("/"):
                    em, pn = parse_credential_line(text)
                    if em and pn:
                        is_valid, dur_msg = check_user_duration(chat_id)
                        if not is_valid:
                            tg_send_menu(dur_msg, chat_id=chat_id, show_account_menu=True)
                            session.waiting_cred = False
                            continue
                        session.login_email = em
                        session.login_pin = pn
                        session.waiting_cred = False
                        session.showing_account_menu = False
                        tg_send("✅ Data diterima!\n🔄 Memulai proses login...", chat_id=chat_id)
                        session.start_worker()
                    else:
                        tg_send("❌ Format salah!\n📝 Harusnya: email|pin", chat_id=chat_id)
                    continue

                # Handler input NIK via button keyboard
                if session.waiting_input_nik and not low.startswith("/"):
                    lines = text_raw.splitlines()
                    if lines:
                        nik_list = ["".join(c for c in ln if c.isdigit()) for ln in lines if len("".join(c for c in ln if c.isdigit())) >= 12]
                        if nik_list:
                            with session.nik_file.open("a", encoding="utf-8") as f:
                                f.write("\n".join(nik_list) + "\n")
                            session.last_activity_time = time.time()
                            session.waiting_input_nik = False
                            tg_send(f"✅ Mantap, {len(nik_list)} NIK masuk antrian.", chat_id=chat_id)
                        else:
                            tg_send("❌ Tidak ada NIK yang valid. Pastikan NIK minimal 12 digit.", chat_id=chat_id)
                    else:
                        tg_send("❌ Tidak ada NIK yang dikirim.", chat_id=chat_id)
                    continue

                # ── Handler input NIK auto per akun ──────────────────────────────────────
                if session.waiting_nik_auto_for and not low.startswith("/"):
                    account_name = session.waiting_nik_auto_for
                    nik_file = get_nik_auto_file(session.user_dir, account_name)
                    
                    if text_raw.strip().upper() == "RESET_NIK_AUTO":
                        # Reset list NIK auto untuk akun ini
                        write_lines(nik_file, [])
                        # Reset pointer di state
                        state = load_auto_state(session.user_dir)
                        key = _account_key(account_name)
                        if key in state:
                            state[key]["pointer"] = 0
                            from modules.auto_transaction import save_auto_state
                            save_auto_state(session.user_dir, state)
                        session.waiting_nik_auto_for = ""
                        tg_send_menu(f"🗑️ NIK auto untuk [{account_name}] sudah direset.", chat_id=chat_id)
                    elif text_raw.strip().upper() in ["CANCEL", "KEMBALI", "BATAL"]:
                        session.waiting_nik_auto_for = ""
                        tg_send_menu("Batal input NIK auto.", chat_id=chat_id)
                    else:
                        lines_nik = text_raw.splitlines()
                        nik_list = ["".join(c for c in ln if c.isdigit()) 
                                    for ln in lines_nik 
                                    if len("".join(c for c in ln if c.isdigit())) >= 12]
                        if nik_list:
                            with nik_file.open("a", encoding="utf-8") as f:
                                f.write("\n".join(nik_list) + "\n")
                            total = count_nik_auto(session.user_dir, account_name)
                            session.waiting_nik_auto_for = ""
                            tg_send_menu(
                                f"✅ {len(nik_list)} NIK ditambahkan untuk [{account_name}].\n"
                                f"Total NIK auto: {total} entri.",
                                chat_id=chat_id
                            )
                        else:
                            tg_send("❌ Tidak ada NIK valid. NIK minimal 12 digit.\nCoba lagi atau ketik KEMBALI.", chat_id=chat_id)
                    continue

                btn_text = normalize_button_text(text_raw)
                
                if btn_text == "CEK DURASI":
                    is_valid, dur_msg = check_user_duration(chat_id)
                    if not is_valid:
                        send_welcome_banner(chat_id, msg.get("from", {}), dur_msg, is_valid)
                    else:
                        tg_send_menu(dur_msg, chat_id=chat_id)
                elif btn_text == "PERPANJANG":
                    if QRIS_FILE and QRIS_FILE.exists():
                        reply_markup = {
                            "inline_keyboard": [[{"text": "✅ SUDAH TRANSFER", "callback_data": "sudah_transfer"}]]
                        }
                        tg_send_photo(str(QRIS_FILE), "📸 Nih QRIS-nya.\n\nKalau udah transfer, klik tombol '✅ SUDAH TRANSFER' di bawah ya.", chat_id=chat_id, reply_markup=reply_markup)
                    else:
                        tg_send_menu("❌ Waduh, file QRIS gak ketemu. Hubungi owner deh.", chat_id=chat_id)
                elif btn_text == "AKSES MAP PREMIUM":
                    is_valid, dur_msg = check_user_duration(chat_id)
                    if not is_valid:
                        send_welcome_banner(chat_id, msg.get("from", {}), dur_msg, is_valid)
                    else:
                        session.showing_account_menu = True
                        tg_send_menu(f"{dur_msg}\n\n⭐ Pilih menu di bawah!", chat_id=chat_id, show_account_menu=True)
                elif btn_text == "KEMBALI":
                    session.showing_account_menu = False
                    tg_send_menu("◀️ Oke, balik ke menu utama.", chat_id=chat_id, force_home=True)
                elif btn_text == "PROSES AKUN":
                    accounts_list = session.get_accounts_list()
                    if accounts_list:
                        user_info = msg.get("from", {})
                        first_name = user_info.get("first_name", "")
                        last_name = user_info.get("last_name", "")
                        full_name = f"{first_name} {last_name}".strip() or "User"
                        username_str = f"@{user_info.get('username')}" if user_info.get('username') else "-"
                        
                        days_en = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
                        months_en = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
                        now = datetime.datetime.now()
                        date_str = f"{days_en[now.weekday()]}, {now.day:02d} {months_en[now.month-1]} {now.year} {now.strftime('%H:%M:%S')}"
                        
                        is_valid, dur_msg = check_user_duration(chat_id)
                        durasi_str = dur_msg.split("Sisa: ")[1] if "Sisa: " in dur_msg else "Unlimited"
                        if str(chat_id) == OWNER_ID:
                            durasi_str = "Unlimited (Owner)"
                            
                        try:
                            st_ping = time.time()
                            requests.get(f"https://api.telegram.org", timeout=2)
                            ping_ms = int((time.time() - st_ping) * 1000)
                            if ping_ms < 150: speed_str = f"🚀 {ping_ms}ms (Super Fast)"
                            elif ping_ms < 400: speed_str = f"⚡ {ping_ms}ms (Fast)"
                            else: speed_str = f"🏃 {ping_ms}ms (Normal)"
                        except:
                            speed_str = "🚀 Super Fast"
                            
                        caption = (
                            f"👋 — Hello {full_name} 🐾\n\n"
                            f"❝ {date_str} ❞\n\n"
                            f"Informasi Pengguna\n"
                            f"ID : {chat_id}\n"
                            f"Username : {username_str}\n"
                            f"Masa Aktif : {durasi_str}\n"
                            f"Status Bot : {speed_str}\n\n"
                        )
                        
                        inline_buttons = [
                            [
                                {"text": "WhatsApp", "url": "https://wa.me/6285155058577?Hallo%20*ADEX%IDN*!!!%0ABot%20Telegram%20Premium."}, 
                                {"text": "Telegram", "url": "https://t.me/mhengkyy"}
                            ],
                            [
                                {"text": "👤 PILIH AKUN", "callback_data": "show_accounts_list"}
                            ]
                        ]
                            
                        tg_send_inline_menu(caption, inline_buttons, chat_id)
                    else:
                        tg_send_menu("📭 Belum ada akun tersimpan. Input dulu gih.", chat_id=chat_id, show_account_menu=True)
                elif btn_text == "LOGIN MANUAL":
                    if session.run_event.is_set():
                        tg_send_menu("🔴 Bot lagi jalan. LOGOUT dulu.", chat_id=chat_id, show_account_menu=True)
                    else:
                        session.waiting_cred = True
                        tg_send_menu("🔑 Kirim akunnya:\nemail|pin", chat_id=chat_id, show_account_menu=True)
                elif btn_text == "INPUT AKUN":
                    session.waiting_input_akun = True
                    tg_send_menu(
                        "📋 Kirim data akun (satu per baris):\n"
                        "Format: NAMA email|pin\n\n"
                        "Contoh:\n"
                        "HENGKYY hengkly@email.com|123456\n"
                        "RIYANTO riyanto@gmail.com|140225\n\n"
                        "*(Data akun akan disimpan ke sistem)*",
                        chat_id=chat_id, show_account_menu=True
                    )
                elif btn_text == "HAPUS AKUN":
                    accounts_list = session.get_accounts_list()
                    if accounts_list:
                        lines = ["🗑️ Pilih akun yang mau dihapus:", "━━━━━━━━━━━━━━━━━"]
                        for i, (name, _) in enumerate(accounts_list, 1):
                            lines.append(f"{i}. {name}")
                        tg_send_menu("\n".join(lines) + "\n\nKetik nama akun yang mau dihapus:", chat_id=chat_id, show_account_menu=True)
                        session.waiting_del_akun = True
                    else:
                        tg_send_menu("📭 Gak ada akun yang bisa dihapus.", chat_id=chat_id, show_account_menu=True)
                elif btn_text == "CEK STOK DATA":
                    def _run_cek_stok():
                        run_cek_stok_data(session)
                    threading.Thread(target=_run_cek_stok, daemon=True).start()
                elif btn_text in ["AUTO ON", "🤖 AUTO ON"] or low.startswith("/auto_on"):
                    # ── Tombol / Perintah: Aktifkan Auto-Transaction ──────────────────────
                    if session.auto_mode:
                        tg_send_menu("⚠️ Auto-Mode sudah aktif!", chat_id=chat_id)
                    elif session.run_event.is_set():
                        tg_send_menu("⚠️ Bot sedang jalan (mode manual). LOGOUT dulu.", chat_id=chat_id)
                    else:
                        is_valid, dur_msg = check_user_duration(chat_id)
                        if not is_valid and chat_id != OWNER_ID:
                            tg_send_menu(dur_msg, chat_id=chat_id)
                        else:
                            accounts_list = session.get_accounts_list()
                            if not accounts_list:
                                tg_send_menu("📭 Belum ada akun tersimpan. Input akun dulu.", chat_id=chat_id)
                            else:
                                session.auto_mode = True
                                session.current_phase = 1
                                def _run_auto():
                                    run_auto_transaction(session)
                                session.auto_thread = threading.Thread(target=_run_auto, daemon=True)
                                session.auto_thread.start()
                elif btn_text in ["AUTO OFF", "🛑 AUTO OFF"] or low.startswith("/auto_off"):
                    # ── Tombol / Perintah: Hentikan Auto-Transaction ──────────────────────
                    if session.auto_mode:
                        session.auto_mode = False
                        tg_send_menu("🛑 Auto-Mode sedang dihentikan... Tunggu akun yang sedang berjalan selesai.", chat_id=chat_id, force_home=True)
                    else:
                        tg_send_menu("ℹ️ Auto-Mode tidak sedang aktif.", chat_id=chat_id)
                elif btn_text in ["STATUS AUTO"] or low.startswith("/auto_status"):
                    # ── Status Auto-Transaction ───────────────────────────────────────────
                    if session.auto_mode:
                        fase_str = f"Fase {session.current_phase}" if hasattr(session, 'current_phase') else "?"
                        tg_send_menu(f"🤖 Auto-Transaction AKTIF\nFase saat ini: {fase_str}\n\nKirim '🛑 AUTO OFF' untuk berhenti.", chat_id=chat_id)
                    else:
                        tg_send_menu("ℹ️ Auto-Transaction tidak aktif.", chat_id=chat_id)
                elif btn_text in ["SET NIK AUTO", "NIK AUTO", "📋 NIK AUTO"] or low.startswith("/set_nik_auto"):
                    # ── Tampilkan pilihan akun untuk input NIK auto ───────────────────────
                    accounts_list = session.get_accounts_list()
                    if not accounts_list:
                        tg_send_menu("📭 Belum ada akun tersimpan.", chat_id=chat_id)
                    else:
                        inline_buttons = []
                        for acc_name, _ in accounts_list:
                            nik_count = count_nik_auto(session.user_dir, acc_name)
                            cookie_icon = "🍪" if session.has_cookie(acc_name) else "🔑"
                            status_nik = f"{nik_count} NIK" if nik_count > 0 else "Belum ada NIK"
                            inline_buttons.append([
                                {"text": f"👤 {acc_name} ({cookie_icon} | {status_nik})",
                                 "callback_data": f"set_nik_auto_{acc_name}"}
                            ])
                        tg_send_inline_menu(
                            "📋 **PILIH AKUN AUTO-TRANSACTION**\n"
                            "━━━━━━━━━━━━━━━━━\n"
                            " Indikator:\n"
                            "🍪 = Cookie Sesi Aktif (Direct Login)\n"
                            "🔑 = Login Manual (Pin/Email)\n\n"
                            "Tap nama akun di bawah untuk kelola NIK & Cookie:",
                            inline_buttons,
                            chat_id
                        )
                elif low.startswith("/start"):
                    session.showing_account_menu = False
                    is_valid, dur_msg = check_user_duration(chat_id)
                    send_welcome_banner(chat_id, msg.get("from", {}), dur_msg, is_valid)
                elif low.startswith("/login"):
                    if session.run_event.is_set():
                        tg_send_menu("🟢 Bot sedang jalan.", chat_id=chat_id)
                    else:
                        session.waiting_cred = True
                        tg_send_menu("🔑 Kirim: email|pin", chat_id=chat_id, show_account_menu=True)
                elif low.startswith("/stop") or btn_text in ["STOP", "LOGOUT", "AUTO OFF", "STOP AUTO"] or "AUTO OFF" in btn_text or "STOP" in btn_text:
                    if hasattr(session, 'stop_all_processes'):
                        session.stop_all_processes()
                    session.reset_state(force=True)
                    session.stop_worker()
                    session.delete_all_cookies()
                    clear_terminal_and_logs()
                    tg_send_menu("🛑 Semua proses dihentikan.\nBot, browser, dan auto-mode dimatikan, sisa cookie dibersihkan.", chat_id=chat_id, force_home=True)
                elif low.startswith("/del") or btn_text == "RESET NIK":
                    write_lines(session.nik_file, [])
                    if session.queue_file.exists():
                        session.queue_file.unlink(missing_ok=True)
                    session.reset_queue_flag = True
                    tg_send_menu("🗑️ Sip, data NIK & antrian udah bersih.", chat_id=chat_id)
                elif low.startswith("/cek") or btn_text == "CEK STOK":
                    if session.run_event.is_set():
                        session.cek_flag.touch()
                        tg_send_menu("📦 Proses cek stok...", chat_id=chat_id)
                    else:
                        tg_send_menu("🔴 Bot belum jalan. Login dulu dong.", chat_id=chat_id)
                elif btn_text == "INPUT NIK":
                    if session.run_event.is_set():
                        session.waiting_input_nik = True
                        tg_send("📝 Kirim NIK (satu per baris, min 12 digit):", chat_id=chat_id)
                    else:
                        tg_send_menu("🔴 Bot belum jalan. Login dulu.", chat_id=chat_id)
                elif btn_text in ["MODE KALEM", "MODE NORMAL", "🌺 MODE KALEM", "⚡ MODE NORMAL"]:
                    if session.run_event.is_set():
                        session.mode_kalem = not session.mode_kalem
                        status_mode = "KALEM 🪷 (Lambat & Aman/Banyak Jeda)" if session.mode_kalem else "NORMAL ⚡ (Cepat)"
                        tg_send_menu(f"✅ Mode berhasil diubah ke: {status_mode}", chat_id=chat_id)
                    else:
                        tg_send_menu("🔴 Bot belum jalan. Login dulu dong.", chat_id=chat_id)
                elif btn_text in ["🏠 RT SAJA", "🏠🏢 RT & UMKM", "RT SAJA", "RT & UMKM"]:
                    if session.get_filter_display() == "RT SAJA":
                        session.set_filter("RUMAH TANGGA,USAHA MIKRO")
                        tg_send_menu("✅ Filter diubah ke: 🏠🏢 RUMAH TANGGA & USAHA MIKRO", chat_id=chat_id)
                    else:
                        session.set_filter("RUMAH TANGGA")
                        tg_send_menu("✅ Filter diubah ke: 🏠 RUMAH TANGGA SAJA", chat_id=chat_id)
                elif btn_text in ["CLEAR TERMINAL", "CLEAR LOG", "CLEAR TERMINAL VPS", "CLEAR LOG TERMINAL", "CLEAR LOG"] or low in ["/clear", "/clear_log", "/clear_terminal"]:
                    clear_terminal_and_logs()
                    tg_send_menu("🧹 Terminal & log dibersihkan.", chat_id=chat_id)
                elif low.startswith("/status"):
                    antre_in, antre_q = len(read_lines(session.nik_file)), len(read_lines(session.queue_file))
                    status_text = '🟢 RUNNING' if session.run_event.is_set() else '🔴 STOPPED'
                    is_valid, dur_msg = check_user_duration(chat_id)
                    tg_send_menu(f"📊 STATUS BOT\n━━━━━━━━━━━━━━━━━\nStatus: {status_text}\nPangkalan: {session.nama_pangkalan or '-'}\nAntrian: {antre_in} input, {antre_q} queue\n\n{dur_msg}", chat_id=chat_id)
                elif low.startswith("/nik"):
                    lines = text_raw.splitlines()[1:] if "\n" in text_raw else []
                    if lines:
                        nik_list = ["".join(c for c in ln if c.isdigit()) for ln in lines if len("".join(c for c in ln if c.isdigit())) >= 12]
                        if nik_list:
                            with session.nik_file.open("a", encoding="utf-8") as f:
                                f.write("\n".join(nik_list) + "\n")
                            session.last_activity_time = time.time()
                            tg_send(f"✅ Mantap, {len(nik_list)} NIK masuk antrian.", chat_id=chat_id)

        except requests.exceptions.Timeout:
            consecutive_timeouts += 1
            if consecutive_timeouts >= max_consecutive_timeouts:
                logging.warning(f"Terlalu banyak timeout berturut-turut ({consecutive_timeouts}x). Tunggu lebih lama...")
                time.sleep(30)
                consecutive_timeouts = 0
            else:
                logging.debug("Polling timeout (normal untuk long polling). Coba lagi...")
                time.sleep(2)
        except requests.exceptions.RequestException as e:
            consecutive_timeouts = 0
            logging.warning(f"Koneksi polling error: {e}. Coba lagi...")
            time.sleep(10)
        except Exception:
            consecutive_timeouts = 0
            logging.error(f"!!! ERROR KRITIS bot_polling_loop !!!\n{traceback.format_exc()}")
            time.sleep(5)

# ===================== MAIN =====================
def set_terminal_title(title: str):
    """Set judul window terminal — cross-platform (Windows CMD & Linux/Mac)"""
    try:
        if os.name == 'nt':  # Windows
            os.system(f'title {title}')
        else:  # Linux / macOS
            sys.stdout.write(f'\033]0;{title}\007')
            sys.stdout.flush()
    except Exception:
        pass

def acquire_lock():
    lock_file = SCRIPT_DIR / f"{SCRIPT_NAME}.lock"
    if lock_file.exists():
        try:
            old_pid = int(lock_file.read_text().strip())
            try:
                os.kill(old_pid, 0)
                logging.critical(f"⚠️ Bot sudah berjalan dengan PID {old_pid}. Membatalkan eksekusi ganda.")
                print(f"⚠️ Bot sudah berjalan dengan PID {old_pid}. Menutup instance ganda ini...")
                sys.exit(0)
            except OSError:
                pass # Process lama sudah mati, bisa dilanjut
        except Exception:
            pass
    try:
        lock_file.write_text(str(os.getpid()))
    except Exception as e:
        logging.error(f"Gagal membuat lock file: {e}")

def release_lock():
    lock_file = SCRIPT_DIR / f"{SCRIPT_NAME}.lock"
    try:
        if lock_file.exists():
            lock_file.unlink()
    except Exception:
        pass

if __name__ == "__main__":
    # Set judul terminal dari BOT_NAME di .env (beda tiap instance bot)
    set_terminal_title(f"{BOT_NAME}")
    acquire_lock()
    try:
        # Loop untuk retry koneksi Telegram saat baru startup agar tidak crash
        while True:
            try:
                ensure_token_ok()
                break
            except Exception as e:
                logging.warning(f"Gagal terhubung ke Telegram saat startup ({e}). Coba lagi dalam 10 detik...")
                time.sleep(10)
        
        # Update title setelah berhasil online
        set_terminal_title(f"{BOT_NAME} 🟢 ONLINE")
        threading.Thread(target=bot_polling_loop, daemon=True).start()
        tg_send_menu(f"🤖 BOT MAP PREMIUM ONLINE v7.0.", chat_id=OWNER_ID)
        while True:
            time.sleep(1)
    except (KeyboardInterrupt, SystemExit):
        clear_terminal()
        logging.info("Skrip dihentikan.")
        release_lock()
        sys.exit(0)
    except Exception:
        logging.critical(f"!!! ERROR FATAL startup !!!\n{traceback.format_exc()}")
        release_lock()
        sys.exit(1)
