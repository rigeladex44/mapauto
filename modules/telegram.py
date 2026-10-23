import os
import json
import logging
import requests
from pathlib import Path
from modules.config import BOT_TOKEN, OWNER_ID, QRIS_FILE, SCRIPT_DIR, WEBAPP_URL
from modules.duration import check_user_duration
from modules.session import get_or_create_session

def tg_send(text: str, chat_id: str = None):
    """Kirim pesan ke Telegram"""
    if not chat_id:
        logging.warning("tg_send: chat_id tidak diberikan")
        return None
    try: 
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={"chat_id": chat_id, "text": text}, timeout=20)
        return r.json().get('result', {}).get('message_id')
    except Exception as e: 
        logging.warning(f"Gagal mengirim pesan TG: {e}")
        return None

def tg_send_chat_action(chat_id: str, action: str = "typing"):
    """Kirim sinyal status aksi di top bar Telegram (typing, find_location, upload_photo, dll)"""
    if not chat_id: return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendChatAction",
            data={"chat_id": str(chat_id), "action": action},
            timeout=3
        )
    except Exception:
        pass

def tg_answer_callback(callback_query_id: str, text: str = "", show_alert: bool = False):
    """Kirim Toast Notification melayang di atas layar HP saat tombol inline ditekan"""
    if not callback_query_id: return
    try:
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/answerCallbackQuery",
            data={
                "callback_query_id": str(callback_query_id),
                "text": text,
                "show_alert": show_alert
            },
            timeout=3
        )
    except Exception:
        pass

def tg_edit_message(chat_id: str, message_id: int, text: str, reply_markup: dict = None, parse_mode: str = "HTML") -> bool:
    """Edit pesan Telegram secara live (Dynamic Live Status Update)"""
    if not chat_id or not message_id:
        return False
    try:
        data = {
            "chat_id": str(chat_id),
            "message_id": int(message_id),
            "text": text,
            "parse_mode": parse_mode
        }
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText", data=data, timeout=10)
        return r.json().get("ok", False)
    except Exception as e:
        logging.warning(f"Gagal editMessageText: {e}")
        return False

def make_progress_bar(current: int, total: int, length: int = 10) -> str:
    """Membuat indikator progress bar charger/batrei live (0-100%)"""
    if total <= 0:
        return "▱▱▱▱▱▱▱▱▱▱ 0% ⚡"
    percent = min(100, int((current / total) * 100))
    filled = min(length, int((current / total) * length))
    empty = length - filled
    bar = "▰" * filled + "▱" * empty
    icon = "⚡" if percent < 100 else "🔋"
    return f"{bar} {percent}% {icon}"

def tg_send_photo(photo_path: str, caption: str = "", chat_id: str = None, reply_markup: dict = None):
    """Kirim foto ke Telegram"""
    if not chat_id:
        logging.warning("tg_send_photo: chat_id tidak diberikan")
        return None
    try:
        with open(photo_path, 'rb') as photo:
            files = {'photo': photo}
            data = {"chat_id": chat_id, "caption": caption}
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup)
            r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", files=files, data=data, timeout=20)
            return r.json().get('result', {}).get('message_id')
    except Exception as e:
        logging.warning(f"Gagal mengirim foto TG: {e}")
        return None

def tg_send_document(document_path: str, caption: str = "", chat_id: str = None):
    """Kirim dokumen ke Telegram"""
    if not chat_id:
        logging.warning("tg_send_document: chat_id tidak diberikan")
        return None
    try:
        with open(document_path, 'rb') as doc:
            files = {'document': doc}
            data = {"chat_id": chat_id, "caption": caption}
            r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument", files=files, data=data, timeout=20)
            return r.json().get('result', {}).get('message_id')
    except Exception as e:
        logging.warning(f"Gagal mengirim dokumen TG: {e}")
        return None

def tg_send_menu(text: str, chat_id: str = None, show_account_menu: bool = False, force_home: bool = False, photo_path: str = None):
    """Kirim menu dengan button keyboard yang otomatis menyesuaikan kondisi"""
    if not chat_id:
        logging.warning("tg_send_menu: chat_id tidak diberikan")
        return None
    target_chat = str(chat_id)
    session = get_or_create_session(target_chat)
    
    # Cek status durasi user
    is_owner = str(chat_id) == OWNER_ID
    is_valid_duration, dur_msg = check_user_duration(chat_id)
    
    # Auto-reset showing_account_menu jika bot tidak running dan force_home
    if force_home or (not session.run_event.is_set() and not show_account_menu):
        session.showing_account_menu = False
    
    # Prioritas 0: Auto-mode sedang berjalan
    if session.auto_mode:
        fase_str = f"Fase {session.current_phase}" if hasattr(session, 'current_phase') else "Aktif"
        rows = [
            [{"text": f"📊 STATUS AUTO ({fase_str})"}],
            [{"text": "🛑 AUTO OFF"}, {"text": "🧹 CLEAR LOG"}]
        ]
        placeholder = f"🤖 Auto {fase_str} berjalan..."
    
    # Prioritas 1: Bot sedang running (mode manual)
    elif session.run_event.is_set():
        mode_btn = "🌺 MODE KALEM" if not session.mode_kalem else "⚡ MODE NORMAL"
        filter_btn = "🏠 RT SAJA" if session.get_filter_display() == "RT SAJA" else "🏠🏢 RT & UMKM"
        rows = [
            [{"text": "INPUT NIK"}, {"text": "CEK STOK"}, {"text": "RESET NIK"}],
            [{"text": mode_btn}, {"text": filter_btn}, {"text": "LOGOUT"}],
            [{"text": "🧹 CLEAR LOG"}]
        ]
        placeholder = f"Bot jalan ({filter_btn}) — kirim NIK..."
    
    # Prioritas 2: Beranda
    else:
        session.showing_account_menu = False
        
        if is_owner:
            rows = [
                [{"text": "AKSES MAP PREMIUM"}],
                [{"text": "CEK DURASI"}, {"text": "PERPANJANG"}],
                [{"text": "👑 ADMIN PANEL"}, {"text": "🧹 CLEAR LOG"}]
            ]
            placeholder = "👑 Owner Panel"
        elif is_valid_duration:
            bottom_row = [{"text": "🧹 CLEAR LOG"}]
            if WEBAPP_URL:
                bottom_row.append({"text": "📱 DASHBOARD", "web_app": {"url": WEBAPP_URL}})
            rows = [
                [{"text": "PROSES AKUN"}, {"text": "LOGIN MANUAL"}, {"text": "CEK STOK DATA"}],
                [{"text": "INPUT AKUN"}, {"text": "HAPUS AKUN"}, {"text": "📋 NIK AUTO"}],
                [{"text": "🤖 AUTO ON"}, {"text": "CEK DURASI"}, {"text": "PERPANJANG"}],
                bottom_row
            ]
            placeholder = "Menu Premium — pilih aksi..."
            session.showing_account_menu = True
        else:
            rows = [
                [{"text": "CEK DURASI"}, {"text": "PERPANJANG"}]
            ]
            placeholder = "⚠️ Durasi Expired"
    
    kb = {"keyboard": rows, "resize_keyboard": True, "is_persistent": True, "one_time_keyboard": False, "input_field_placeholder": placeholder}
    try: 
        if photo_path and Path(photo_path).exists():
            with open(photo_path, 'rb') as f_photo:
                files = {'photo': f_photo}
                data = {"chat_id": target_chat, "caption": text[:1024], "reply_markup": json.dumps(kb)}
                r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendPhoto", files=files, data=data, timeout=20)
                return r.json().get('result', {}).get('message_id')
        else:
            if len(text) > 4000:
                chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
                last_msg_id = None
                for i, chunk in enumerate(chunks):
                    if i == len(chunks) - 1:
                        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={"chat_id": target_chat, "text": chunk, "reply_markup": json.dumps(kb)}, timeout=20)
                        last_msg_id = r.json().get('result', {}).get('message_id')
                    else:
                        requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={"chat_id": target_chat, "text": chunk}, timeout=20)
                return last_msg_id
            else:
                r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", data={"chat_id": target_chat, "text": text, "reply_markup": json.dumps(kb)}, timeout=20)
                return r.json().get('result', {}).get('message_id')
    except Exception as e: 
        logging.warning(f"Gagal mengirim menu TG: {e}")
        return None

import datetime

def send_welcome_banner(chat_id: str, user_info: dict, dur_msg: str, is_valid: bool):
    first_name = user_info.get("first_name", "")
    last_name = user_info.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip() or "User"
    username_str = f"@{user_info.get('username')}" if user_info.get('username') else "-"
    
    days_en = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    months_en = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
    now = datetime.datetime.now()
    date_str = f"{days_en[now.weekday()]}, {now.day:02d} {months_en[now.month-1]} {now.year} {now.strftime('%H:%M:%S')}"
    
    is_owner = str(chat_id) == OWNER_ID
    
    if is_owner:
        durasi_str = "Unlimited (Owner)"
        status_bot = "✅ Akses Diterima"
        footer_text = "Selamat datang di Panel Owner!"
    elif is_valid:
        durasi_str = dur_msg.split("Sisa: ")[1] if "Sisa: " in dur_msg else "Aktif"
        status_bot = "✅ Akses Diterima"
        footer_text = "Selamat datang di BOT MELON PREMIUM!"
    else:
        if "belum diaktifkan" in dur_msg:
            durasi_str = "Belum Terdaftar"
        else:
            durasi_str = "Expired"
        status_bot = "⚠️ Akses Ditolak"
        footer_text = "Hubungi admin untuk mendaftar atau perpanjang akses bot."
        
    caption = (
        f"👋 — Hello {full_name} 🐾\n\n"
        f"❝ {date_str} ❞\n\n"
        f"Informasi Pengguna\n"
        f"ID : {chat_id}\n"
        f"Username : {username_str}\n"
        f"Masa Aktif : {durasi_str}\n"
        f"Status Bot : {status_bot}\n\n"
        f"{footer_text}"
    )
    
    inline_buttons = [
        [
            {"text": "WhatsApp", "url": "https://wa.me/6285155058577?Hallo%20*ADEX%IDN*!!!%0ABot%20Telegram%20Premium."}, 
            {"text": "Telegram", "url": "https://t.me/mhengkyy"}
        ]
    ]

    banner_path = SCRIPT_DIR / "banner.png"
    if banner_path.exists():
        tg_send_photo(str(banner_path), caption, chat_id, reply_markup={"inline_keyboard": inline_buttons})
    else:
        tg_send_inline_menu(caption, inline_buttons, chat_id)

def tg_send_inline_menu(text: str, inline_buttons: list, chat_id: str = None):
    """Kirim pesan dengan inline button (bukan keyboard)"""
    if not chat_id:
        logging.warning("tg_send_inline_menu: chat_id tidak diberikan")
        return None
    reply_markup = {"inline_keyboard": inline_buttons}
    try:
        r = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage", 
                         data={"chat_id": chat_id, "text": text, "reply_markup": json.dumps(reply_markup)}, 
                         timeout=20)
        return r.json().get('result', {}).get('message_id')
    except Exception as e:
        logging.warning(f"Gagal mengirim inline menu TG: {e}")
        return None

def ensure_token_ok():
    try: requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteWebhook", params={"drop_pending_updates": True}, timeout=10)
    except Exception: pass
    r = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/getMe", timeout=10)
    if not (r.ok and r.json().get("ok")): raise ConnectionError(f"TOKEN invalid: {r.text}")

def update_batch_progress_card(session, idx: int, nik: str, status_text: str, is_final: bool = False):
    """
    Mengupdate satu kartu status utama antrian NIK secara live.
    Menghindari pengiriman puluhan pesan chat yang menumpuk.
    """
    chat_id = session.chat_id
    total_awal = getattr(session, 'total_awal', 1)
    
    # Inisialisasi kartu jika belum ada
    if not getattr(session, 'batch_card_msg_id', None):
        session.batch_results = []
        initial_text = (
            f"⏳ <b>PROSES ANTRIAN NIK</b>\n"
            f"━━━━━━━━━━━━━━━━━\n"
            f"{make_progress_bar(0, total_awal)} (0/{total_awal} NIK)\n\n"
            f"🔍 <i>Memulai proses antrian...</i>"
        )
        session.batch_card_msg_id = tg_send(initial_text, chat_id=chat_id)

    # Tambahkan hasil ke list jika ada status_text
    if status_text:
        result_entry = f"{idx}. {nik} ┆ {status_text}"
        # Cek jika idx ini sudah ada di list untuk update (menghindari duplikasi)
        exists = False
        for i, entry in enumerate(session.batch_results):
            if entry.startswith(f"{idx}."):
                session.batch_results[i] = result_entry
                exists = True
                break
        if not exists:
            session.batch_results.append(result_entry)

    progress_bar = make_progress_bar(idx, total_awal)
    
    lines = [
        f"⏳ <b>PROSES ANTRIAN NIK</b>" if not is_final else f"✅ <b>PROSES ANTRIAN SELESAI</b>",
        "━━━━━━━━━━━━━━━━━",
        f"{progress_bar} ({idx}/{total_awal} NIK)\n"
    ]
    
    if not is_final:
        lines.append(f"⚡ <i>Processing: {nik}...</i>\n")
        
    if session.batch_results:
        lines.append("📋 <b>HASIL PROSES:</b>")
        # Tampilkan maksimal 10 hasil terakhir agar tidak kepanjangan
        display_results = session.batch_results[-10:]
        lines.extend(display_results)
        if len(session.batch_results) > 10:
            lines.append(f"<i>... dan {len(session.batch_results) - 10} NIK lainnya (lihat laporan hasil)</i>")

    tg_edit_message(chat_id, session.batch_card_msg_id, "\n".join(lines))

