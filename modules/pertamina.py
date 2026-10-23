import os
import re
import time
import logging
import random
import traceback
import contextlib
import requests
from playwright.sync_api import sync_playwright
from modules.config import BASE_URL, HEADLESS, is_headless, BOT_TOKEN, IDLE_TIMEOUT_SECONDS, SCRIPT_NAME
from modules.session import read_lines, write_lines
from modules.utils import close_location_popup, close_generic_popup, clear_terminal
from modules.telegram import tg_send, tg_send_menu, tg_send_document, tg_send_inline_menu, tg_send_chat_action, update_batch_progress_card
from modules.captcha import handle_captcha_slider
from modules.stock import ambil_sisa_stok, cek_stok

def kembali_ke_beranda(page):
    """Kembali ke beranda (merchant/app) via Cookie Recovery jika ada tampilan tidak dikenal"""
    try:
        current_url = page.url
        # Cek jika sudah berada tepat di beranda
        if "/merchant/app" in current_url and "/verification-nik" not in current_url:
            time.sleep(random.uniform(3.5, 5.0))
            return  # Sudah di beranda
        
        logging.info("🔄 Tampilan/halaman tidak dikenal terdeteksi. Memuat ulang Beranda via Cookies...")
        page.goto(f"{BASE_URL}/merchant/app", timeout=25000)
        jeda = random.uniform(3.5, 5.0)
        logging.info(f"⏳ Jeda {jeda:.1f}s agar halaman beranda ter-render sempurna...")
        time.sleep(jeda)
        
        # Cek apakah di-redirect ke login (session expired)
        if 'login' in page.url:
            logging.warning("⚠️ Terdeteksi redirect ke login page (session expired). Perlu login ulang...")
            raise Exception("Server down atau session expired - perlu login ulang")
        
        close_location_popup(page, wait_time=0.3)
        close_generic_popup(page, wait_time=0.2)
    except Exception as e:
        if 'login' in str(e).lower():
            logging.error(f"❌ Server error atau session expired: {e}")
            raise  # Re-raise exception agar worker loop / re-login bisa handle
        logging.warning(f"Gagal pemulihan beranda via cookie ({e}). Mencoba reload...")
        try:
            page.reload(timeout=20000)
            time.sleep(3.5)
            if 'login' in page.url:
                raise Exception("Session expired setelah reload")
        except Exception as reload_err:
            if 'login' in str(reload_err).lower():
                raise

def login_dengan_retry(page, session, account_name: str = None, silent: bool = False):
    """Login dengan retry, stay di beranda setelah login (tidak klik Catat Penjualan)"""
    email = session.login_email
    pin = session.login_pin
    
    for attempt in range(1, 4):
        try:
            logging.info(f"[{session.chat_id}] Percobaan login ke-{attempt} untuk {email}")
            tg_send_chat_action(session.chat_id, "typing")
            page.goto(f"{BASE_URL}/merchant-login", timeout=30000)
            time.sleep(random.uniform(2.0, 3.0))
            page.get_by_role("textbox", name="Nomor ponsel atau email").fill(email)
            time.sleep(random.uniform(2.0, 3.0))
            page.get_by_role("textbox", name="PIN").fill(pin)
            time.sleep(random.uniform(3.0, 4.0))
            try:
                page.get_by_role("button", name="Masuk").click(timeout=5000)
            except Exception as click_err:
                logging.warning(f"[{session.chat_id}] Klik masuk gagal, mencoba lagi dalam 2 detik: {click_err}")
                time.sleep(2)
                page.get_by_role("button", name="Masuk").click(timeout=5000)
            
            time.sleep(2)
            error_found = False
            try:
                error_selectors = [
                    "text=Email atau PIN salah",
                    "text=Akun tidak valid",
                    "text=Login gagal",
                    "text=error"
                ]
                for error_sel in error_selectors:
                    if page.locator(error_sel).first.is_visible(timeout=1000):
                        error_text = page.locator(error_sel).first.inner_text()
                        logging.error(f"[{session.chat_id}] Login gagal: {error_text}")
                        error_found = True
                        break
            except:
                pass
            
            if error_found:
                if attempt < 3:
                    time.sleep(5)
                    continue
                else:
                    logging.error(f"[{session.chat_id}] Gagal login setelah 3x percobaan.")
                    if not silent:
                        tg_send("❌ Gagal login setelah 3x percobaan.", chat_id=session.chat_id)
                    return False
            
            max_wait = 20  # maksimal 20 detik
            start_time = time.time()
            navigated = False
            
            while time.time() - start_time < max_wait:
                try:
                    current_url = page.url
                    if "/merchant/app" in current_url and "/verification-nik" not in current_url:
                        navigated = True
                        logging.info(f"[{session.chat_id}] Navigasi ke beranda selesai")
                        break
                    if page.locator("text=Catat Penjualan").first.is_visible(timeout=1000):
                        navigated = True
                        logging.info(f"[{session.chat_id}] Elemen beranda terdeteksi")
                        break
                except:
                    pass
                time.sleep(0.5)
            
            if not navigated:
                if "/merchant/app" in page.url and "/verification-nik" not in page.url:
                    navigated = True
                    logging.info(f"[{session.chat_id}] Sudah di beranda berdasarkan URL")
                else:
                    raise Exception("Tidak berhasil navigasi ke beranda setelah login")
            
            logging.info(f"[{session.chat_id}] Login berhasil, mengambil nama pangkalan dari pojok atas kanan...")
            
            if "/merchant/app" not in page.url:
                page.goto(f"{BASE_URL}/merchant/app", timeout=20000)
            jeda = random.uniform(3.5, 5.0)
            logging.info(f"[{session.chat_id}] ⏳ Jeda {jeda:.1f}s agar halaman beranda ter-render sempurna...")
            time.sleep(jeda)
            close_location_popup(page, wait_time=0.3)
            close_generic_popup(page, wait_time=0.2)
            
            session.nama_pangkalan = email  # Default fallback
            try:
                page.wait_for_timeout(1500)
                
                nama_pangkalan = page.evaluate("""
                    () => {
                        const allElements = document.querySelectorAll('*');
                        const viewportWidth = window.innerWidth;
                        const viewportHeight = window.innerHeight;
                        
                        let topMostName = null;
                        let topMostTop = Infinity;
                        
                        for (let el of allElements) {
                            const rect = el.getBoundingClientRect();
                            if (rect.right > viewportWidth * 0.5 && rect.top < viewportHeight * 0.3 && rect.height > 0) {
                                const text = el.innerText?.trim() || '';
                                if (text && text.length >= 5 && text.length < 100) {
                                    const words = text.split(/\\s+/);
                                    if (words.length >= 2 && words.length <= 5) {
                                        if (words.every(w => /^[A-Z]/.test(w))) {
                                            if (rect.top < topMostTop) {
                                                topMostTop = rect.top;
                                                topMostName = text;
                                            }
                                        }
                                    }
                                }
                            }
                        }
                        return topMostName;
                    }
                """)
                
                if nama_pangkalan:
                    nama_pangkalan_lines = nama_pangkalan.strip().split('\n')
                    session.nama_pangkalan = nama_pangkalan_lines[0].strip()
                    logging.info(f"[{session.chat_id}] Nama pangkalan ditemukan: {session.nama_pangkalan}")
                else:
                    try:
                        header_texts = []
                        selectors_to_try = ["header", "[class*='header']", "[class*='navbar']", "[class*='user']", "[class*='profile']"]
                        for sel in selectors_to_try:
                            try:
                                elements = page.locator(sel).all()
                                for el in elements[:5]:
                                    text = el.inner_text(timeout=1000).strip() if el.is_visible() else ""
                                    if text and len(text.split()) >= 2 and len(text.split()) <= 5:
                                        words = text.split()
                                        if all(w[0].isupper() for w in words if w):
                                            header_texts.append(text)
                            except:
                                continue
                        
                        if header_texts:
                            session.nama_pangkalan = header_texts[0].strip()
                            logging.info(f"[{session.chat_id}] Nama pangkalan ditemukan (fallback): {session.nama_pangkalan}")
                    except Exception as e2:
                        logging.debug(f"[{session.chat_id}] Fallback method juga gagal: {e2}")
                        
            except Exception as e:
                logging.warning(f"[{session.chat_id}] Gagal mengambil nama pangkalan dari pojok atas kanan: {e}")
                session.nama_pangkalan = email
            
            stok_login_text = None
            try:
                stok_login_text = ambil_sisa_stok(page)
            except Exception as e:
                logging.warning(f"[{session.chat_id}] Gagal mengambil sisa stok saat login: {e}")
            finally:
                try:
                    kembali_ke_beranda(page)
                except Exception as e:
                    logging.debug(f"[{session.chat_id}] Gagal kembali ke beranda setelah cek stok login: {e}")
            
            # --- AUTO-REGISTER AKUN KE accounts.json & SIMPAN STORAGE STATE ---
            try:
                acc_name = account_name or session.nama_pangkalan or email
                if acc_name and email and pin and hasattr(session, 'add_account'):
                    session.add_account(acc_name, email, pin)
                    logging.info(f"[{session.chat_id}] 💾 Akun [{acc_name}] otomatis disimpan ke accounts.json")
                if hasattr(session, 'get_cookie_path'):
                    cookie_path = session.get_cookie_path(acc_name)
                    page.context.storage_state(path=str(cookie_path))
                    logging.info(f"[{session.chat_id}] 💾 Storage state (cookies) disimpan ke {cookie_path.name}")
            except Exception as save_err:
                logging.warning(f"[{session.chat_id}] ⚠️ Gagal simpan akun/storage state: {save_err}")
            
            stok_line = f"Sisa stok: {stok_login_text}" if stok_login_text else "Sisa stok: (gagal dibaca)"
            session.last_activity_time = time.time()
            
            if not silent:
                filter_desc = "🏠 RUMAH TANGGA SAJA" if session.get_filter_display() == "RT SAJA" else "🏠🏢 RUMAH TANGGA & USAHA MIKRO"
                msg_id = tg_send_menu(f"🟢 LOGIN BERHASIL\n━━━━━━━━━━━━━━━━━\n🏪 {session.nama_pangkalan}\n📦 {stok_line}\n🎯 Filter: {filter_desc}\n\nSilahkan input NIK untuk diproses!", chat_id=session.chat_id)
                if hasattr(session, 'queue_file') and session.queue_file.exists():
                    if msg_id: session.batch_msg_ids.append(msg_id)

                inline_filter_btns = [
                    [
                        {"text": "🏠 RT SAJA", "callback_data": "set_filter_rt"},
                        {"text": "🏠🏢 RT & UMKM", "callback_data": "set_filter_rt_um"}
                    ]
                ]
                tg_send_inline_menu(f"🎯 **Pilihan Filter Pelanggan** (Aktif: {filter_desc}):", inline_filter_btns, chat_id=session.chat_id)
            return True
        except Exception as e:
            logging.warning(f"[{session.chat_id}] Login gagal percobaan ke-{attempt}. Error: {e}")
            if "melebihi batas" in str(e).lower():
                logging.error(f"[{session.chat_id}] Terdeteksi error 'melebihi batas percobaan', menunggu 2 menit.")
                if not silent:
                    tg_send("⚠️ Login gagal karena terlalu banyak percobaan. Menunggu 2 menit...", chat_id=session.chat_id)
                time.sleep(120)
            elif attempt < 3:
                time.sleep(5)
    logging.error(f"[{session.chat_id}] Gagal login setelah 3x percobaan.")
    if not silent:
        tg_send("❌ Gagal login setelah 3x percobaan.", chat_id=session.chat_id)
    return False

def inisialisasi_sesi_akun(browser, session, account_name: str = None, is_recovery: bool = False, silent: bool = False):
    """
    Menginisialisasi Playwright Context & Page.
    - Secara default (awal run, is_recovery=False): SELALU menjalankan login_dengan_retry() (login manual 1x).
    - Saat recovery pertengahan jalan (is_recovery=True): Coba login via Storage State (Cookie sementara).
    """
    acc_name = account_name or session.nama_pangkalan or session.login_email
    cookie_path = session.get_cookie_path(acc_name) if hasattr(session, 'get_cookie_path') else None
    
    if is_recovery and cookie_path and cookie_path.exists():
        logging.info(f"[{session.chat_id}] 🍪 [Pemulihan Sesi] Mencoba masuk via Storage State ({cookie_path.name})...")
        context = None
        try:
            context = browser.new_context(storage_state=str(cookie_path), ignore_https_errors=True)
            page = context.new_page()
            page.goto(f"{BASE_URL}/merchant/app", timeout=25000)
            
            jeda_beranda = random.uniform(3.5, 5.0)
            logging.info(f"[{session.chat_id}] ⏳ Beri jeda {jeda_beranda:.1f} detik agar halaman beranda ter-render sempurna...")
            time.sleep(jeda_beranda)
            
            if 'login' not in page.url and "/merchant/app" in page.url:
                close_location_popup(page, wait_time=0.3)
                close_generic_popup(page, wait_time=0.2)
                logging.info(f"[{session.chat_id}] ✅ [Pemulihan Sesi] Masuk via Cookie BERHASIL!")
                return context, page, True
            else:
                logging.warning(f"[{session.chat_id}] ⚠️ Sesi cookie expired (redirected to login). Menutup context...")
                try: context.close()
                except: pass
        except Exception as e:
            logging.warning(f"[{session.chat_id}] ⚠️ Gagal memuat cookie pemulihan ({e}). Menutup context...")
            if context:
                try: context.close()
                except: pass

    # Fallback / Login Utama (Email & PIN)
    logging.info(f"[{session.chat_id}] 🔑 Menjalankan login (Email/PIN)...")
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    success = login_dengan_retry(page, session, account_name=account_name, silent=silent)
    return context, page, success

def handle_nib_popup(page):
    try:
        # Cek jika ada popup Segera Lengkapi NIB
        lengkapi_btn = page.get_by_role("button", name="LENGKAPI NIB").first
        if lengkapi_btn.is_visible(timeout=1500):
            logging.info("   ✅ Terdeteksi popup NIB. Klik 'LENGKAPI NIB'")
            lengkapi_btn.click()
            time.sleep(1)
            
            # Cek popup MENGERTI
            mengerti_btn = page.get_by_role("button", name="MENGERTI").first
            if mengerti_btn.is_visible(timeout=2000):
                logging.info("   ✅ Klik 'MENGERTI'")
                mengerti_btn.click()
                time.sleep(1)
                
            # Cek halaman Kriteria
            lanjut_perbarui_btn = page.get_by_role("button", name="LANJUT PERBARUI DATA PELANGGAN").first
            if lanjut_perbarui_btn.is_visible(timeout=2000):
                logging.info("   ✅ Klik 'LANJUT PERBARUI DATA PELANGGAN'")
                lanjut_perbarui_btn.click()
                time.sleep(1)
                
            # Isi NIB 13 angka acak
            nib_input = page.get_by_placeholder("Masukkan nomor induk berusaha")
            if not nib_input.is_visible(timeout=3000):
                nib_input = page.locator("input[type='text'], input[type='number']").last
                
            if nib_input.is_visible(timeout=5000):
                random_nib = "".join([str(random.randint(0, 9)) for _ in range(13)])
                logging.info(f"   ✅ Memasukkan NIB acak: {random_nib}")
                nib_input.fill(random_nib)
                time.sleep(1)
                
                cek_nib_btn = page.get_by_role("button", name="CEK NIB").first
                if cek_nib_btn.is_visible(timeout=1000):
                    logging.info("   ✅ Klik 'CEK NIB'")
                    cek_nib_btn.click()
                    time.sleep(2)
                    
                    lanjut_transaksi_btn = page.get_by_role("button", name="LANJUT TRANSAKSI").first
                    if lanjut_transaksi_btn.is_visible(timeout=3000):
                        logging.info("   ✅ Klik 'LANJUT TRANSAKSI' (Abaikan NIB tidak ditemukan)")
                        lanjut_transaksi_btn.click()
                        time.sleep(1.5)
            return

        # Fallback lama jika ada NANTI SAJA
        nib_btn = page.get_by_role("button", name="NANTI SAJA, LANJUT TRANSAKSI").first
        if nib_btn.is_visible(timeout=1000):
            logging.info("   ✅ Terdeteksi popup NIB (fallback). Klik 'NANTI SAJA, LANJUT TRANSAKSI'")
            nib_btn.click()
            time.sleep(1)
            
    except Exception as e:
        logging.warning(f"   ⚠️ Gagal proses popup NIB: {e}")

def cek_valid_nik_dan_jenis_pelanggan(page, nik, session=None):
    """Cek valid NIK dan handle jenis pelanggan"""
    try:
        selected_type = None
        logging.info("   📝 Input NIK...")
        page.get_by_role("combobox", name="Masukkan 16 digit NIK").fill(nik)
        time.sleep(0.5)
        
        try:
            lanjut_btn = page.get_by_role("button", name="LANJUTKAN PENJUALAN").first
            if lanjut_btn.is_visible(timeout=2000):
                lanjut_btn.click()
                logging.info("   ✅ Klik 'LANJUTKAN PENJUALAN'")
            else:
                page.get_by_test_id("btnCheckNik").first.click()
                logging.info("   ✅ Klik btnCheckNik")
        except:
            page.get_by_test_id("btnCheckNik").first.click()
            logging.info("   ✅ Klik btnCheckNik (fallback)")
        
        time.sleep(2)
        
        filter_raw = (session.filter_jenis_pelanggan if session and hasattr(session, 'filter_jenis_pelanggan') else None) or os.getenv("FILTER_JENIS_PELANGGAN", "RUMAH TANGGA,USAHA MIKRO")
        allowed_types = [t.strip().upper() for t in filter_raw.split(",")]
        if "USAHA MIKRO" in allowed_types:
            allowed_types.remove("USAHA MIKRO")
            allowed_types.insert(0, "USAHA MIKRO")
        all_possible_types = ["USAHA MIKRO", "RUMAH TANGGA", "NELAYAN SASARAN", "PETANI SASARAN", "PENGECER"]
        
        # 1. Cek Apakah Muncul MODAL "Pelanggan Terdaftar" (Pilihan Ganda)
        if page.locator("text=jenis pelanggan di bawah ini").is_visible(timeout=2000):
            logging.info("   ℹ️ Terdeteksi NIK Multi-Type (Modal Pilihan). Mencari opsi yang sesuai filter...")
        
            ada_rumah_tangga = False
            ada_usaha_mikro = False
            try:
                ada_rumah_tangga = page.locator("text=Rumah Tangga").first.is_visible(timeout=500)
            except:
                pass
            try:
                ada_usaha_mikro = page.locator("text=Usaha Mikro").first.is_visible(timeout=500)
            except:
                pass
            is_dual_type = ada_rumah_tangga and ada_usaha_mikro
            if is_dual_type:
                logging.info("   🏠🏢 NIK terdaftar DUAL TYPE (Rumah Tangga + Usaha Mikro)")
 
            pilihan_sukses = False
            tipe_dipilih = None
            for tipe in allowed_types:
                try:
                    el_opsi = page.locator(f"text={tipe}").first
                    if el_opsi.is_visible(timeout=500):
                        logging.info(f"   ✅ Opsi DIIZINKAN ditemukan: '{tipe}'. Memilih...")
                        el_opsi.click()
                        logging.info("   ⏳ Menunggu 2 detik untuk memeriksa notifikasi limit...")
                        time.sleep(2)
                        
                        is_modal_limit = False
                        for limit_msg in ["text=Tidak dapat transaksi", "text=melebihi batas kewajaran"]:
                            try:
                                if page.locator(limit_msg).first.is_visible(timeout=500):
                                    is_modal_limit = True
                                    logging.warning(f"   ⚠️ NIK {nik} ({tipe}) - LIMIT terdeteksi di modal!")
                                    break
                            except:
                                pass
                                
                        if is_modal_limit:
                            try:
                                page.get_by_role("button", name="TUTUP").click()
                            except:
                                pass
                            return False, "LIMIT", tipe.upper()
                            
                        btn_lanjut = page.get_by_role("button", name="LANJUTKAN TRANSAKSI")
                        if btn_lanjut.is_visible(timeout=1000):
                            btn_lanjut.click()
                            logging.info("   ✅ Klik tombol 'LANJUTKAN TRANSAKSI'")
                            time.sleep(1.5)
                            
                            handle_nib_popup(page)
                            
                            pilihan_sukses = True
                            tipe_dipilih = tipe.upper()
                            break
                except:
                    continue
            
            if not pilihan_sukses:
                logging.warning(f"   ⚠️ Modal muncul tapi TIDAK ADA opsi yang sesuai filter ({filter_raw}). SKIP.")
                try:
                    page.get_by_role("button", name="TUTUP").click()
                except:
                    pass
                return False, "Skip Ruwet_TIDAK_TERSEDIA", None
            
            if is_dual_type:
                return True, "OK_DUAL_TYPE", tipe_dipilih
            return True, "OK", tipe_dipilih
                
        else:
            # 2. Modal tidak muncul — cek LIMIT / NOT FOUND
            if page.locator("text=melebihi batas kewajaran").is_visible(timeout=2000) or \
               page.locator("text=kuota").is_visible(timeout=500):
                logging.warning(f"   ⚠️ NIK {nik} - LIMIT")
                return False, "LIMIT", None
            
            if page.locator("text=tidak ditemukan").is_visible(timeout=500) or \
               page.locator("text=tidak terdaftar").is_visible(timeout=500):
                logging.warning(f"   ⚠️ NIK {nik} - DATA TIDAK DITEMUKAN/TIDAK TERDAFTAR")
                return False, "TIDAK_DITEMUKAN", None
            
            detected_allowed = None
            for tipe in allowed_types:
                if page.get_by_text(tipe).first.is_visible(timeout=200):
                    detected_allowed = tipe
                    break
            
            if detected_allowed:
                 logging.info(f"   ✅ Terdeteksi Jenis Pelanggan: '{detected_allowed}' (Sesuai Filter). Lanjut.")
                 selected_type = detected_allowed.upper()
            else:
                forbidden_types = [t for t in all_possible_types if t not in allowed_types]
                for tipe in forbidden_types:
                     if page.get_by_text(tipe).first.is_visible(timeout=200):
                          logging.warning(f"   ⚠️ Terdeteksi Jenis Pelanggan TERLARANG: '{tipe}'. SKIP.")
                          return False, f"Skip Ruwet_{tipe.replace(' ', '_')}", None
                
                logging.info("   ℹ️ Jenis pelanggan tidak terdeteksi spesifik, melanjutkan proses...")
        
        try:
            lanjut_modal_selectors = [
                "button:has-text('LANJUTKAN TRANSAKSI')",
                page.get_by_role("button", name="LANJUTKAN TRANSAKSI"),
                page.locator("text=LANJUTKAN TRANSAKSI").first
            ]
            clicked_modal = False
            for selector in lanjut_modal_selectors:
                try:
                    if isinstance(selector, str):
                        element = page.locator(selector).first
                    else:
                        element = selector
                    if element.is_visible(timeout=1500):
                        element.click()
                        clicked_modal = True
                        logging.info("   ✅ Klik tombol 'LANJUTKAN TRANSAKSI' (modal)")
                        time.sleep(1)
                        break
                except:
                    continue
            if not clicked_modal:
                logging.debug("   ℹ️ Tombol 'LANJUTKAN TRANSAKSI' modal tidak ditemukan")
        except:
            pass
        
        try:
            lanjut_page_btn = page.get_by_role("button", name="Lanjut Transaksi")
            if lanjut_page_btn.is_visible(timeout=2000):
                lanjut_page_btn.click()
                logging.info("   ✅ Klik 'Lanjut Transaksi' (halaman)")
                time.sleep(1.5)
        except:
            pass
        
        handle_nib_popup(page)

        if page.locator("text=stok tabung yang dapat dijual kosong").is_visible(timeout=2000):
            logging.error("   ❌ Stok habis!")
            return False, "STOK_HABIS", selected_type
        
        return True, "OK", selected_type
        
    except Exception as e:
        logging.error(f"   ❌ Error cek NIK: {e}")
        return False, "ERROR", None

def kembali_ke_beranda_verification(page):
    """Kembali ke halaman input NIK (verification-nik)"""
    try:
        if "/verification-nik" in page.url:
            try:
                if page.locator("[data-testid='btnCheckNik']").is_visible(timeout=2000):
                    logging.info("Sudah di halaman verification-nik")
                    return True
            except:
                pass
        
        logging.info("Navigasi ke halaman input NIK...")
        page.goto(f"{BASE_URL}/merchant/app", timeout=20000)
        time.sleep(2)
        close_location_popup(page, wait_time=0.3)
        close_generic_popup(page, wait_time=0.2)
        
        catat_selectors = [
            "text=Catat Penjualan",
            "button:has-text('Catat Penjualan')",
            "div:has-text('Catat Penjualan')",
            "a:has-text('Catat Penjualan')"
        ]
        
        clicked = False
        for selector in catat_selectors:
            try:
                element = page.locator(selector).first
                if element.is_visible(timeout=3000):
                    element.click()
                    logging.info(f"✅ Klik 'Catat Penjualan'")
                    clicked = True
                    time.sleep(2)
                    break
            except:
                continue
        
        if not clicked:
            page.goto(f"{BASE_URL}/merchant/app/verification-nik", timeout=20000)
        
        page.wait_for_selector("[data-testid='btnCheckNik']", timeout=10000)
        logging.info("✅ Sampai di halaman input NIK")
        return True
        
    except Exception as e:
        logging.error(f"Error kembali ke beranda: {e}")
        return False

def cek_hasil_transaksi(page, nik, session=None):
    """Cek hasil transaksi dengan berbagai indikator"""
    try:
        logging.info("   🔍 Cek hasil transaksi...")
        
        try:
            if page.locator("text=Ke Beranda").is_visible(timeout=5000):
                logging.info(f"   ✅✅✅ NIK {nik} - BERHASIL! (tombol 'Ke Beranda' muncul)")
                page.get_by_role("link", name="Ke Beranda").click()
                time.sleep(2)
                return True
        except:
            pass
        
        try:
            success_texts = [
                "text=berhasil", "text=Berhasil", "text=sukses",
                "text=Sukses", "text=Success", "text=transaksi berhasil",
                "text=pembayaran berhasil"
            ]
            for text_selector in success_texts:
                try:
                    if page.locator(text_selector).first.is_visible(timeout=1000):
                        logging.info(f"   ✅✅✅ NIK {nik} - BERHASIL! (text: {text_selector})")
                        return True
                except:
                    pass
        except:
            pass
        
        try:
            if "/success" in page.url or "/berhasil" in page.url:
                logging.info(f"   ✅✅✅ NIK {nik} - BERHASIL! (URL: {page.url})")
                return True
        except:
            pass
        
        try:
            captcha_visible = page.locator(".rc-slider-captcha").is_visible(timeout=1000)
            error_visible = page.locator("text=gagal").is_visible(timeout=500) or page.locator("text=error").is_visible(timeout=500)
            
            if not captcha_visible and not error_visible:
                logging.info(f"   ✅✅✅ NIK {nik} - BERHASIL! (captcha hilang, tidak ada error)")
                return True
        except:
            pass
        
        logging.warning(f"   ⚠️ Status tidak jelas untuk NIK {nik}")
        logging.warning(f"   📍 URL saat ini: {page.url}")
        
        try:
            # Simpan ke folder user agar tidak mencemari root project
            screenshot_dir = session.user_dir if session and hasattr(session, 'user_dir') else None
            screenshot_path = str(screenshot_dir / f"status_unclear_{nik}.png") if screenshot_dir else f"status_unclear_{nik}.png"
            page.screenshot(path=screenshot_path)
            logging.info(f"   📸 Screenshot disimpan: {screenshot_path}")
        except:
            pass
        
        return False
        
    except Exception as e:
        logging.error(f"   ❌ Error cek hasil transaksi: {e}")
        return False

def proses_nik(page, nik, idx, session) -> tuple:
    """Proses satu NIK lengkap"""
    try:
        logging.info(f"\n{'='*60}")
        logging.info(f"[{session.chat_id}] 📝 PROSES NIK {idx}: {nik}")
        logging.info(f"{'='*60}")
        
        if getattr(session, 'mode_kalem', False):
            logging.info(f"[{session.chat_id}] 🪷 Mode Kalem aktif: Menambah jeda 3 detik sebelum proses NIK...")
            time.sleep(3)
        
        if "/verification-nik" not in page.url:
            kembali_ke_beranda_verification(page)
        
        valid, status, selected_type = cek_valid_nik_dan_jenis_pelanggan(page, nik, session)
        if status == "OK_DUAL_TYPE" or (not valid and status == "DUAL_LIMIT"):
            batch_dual = getattr(session, '_batch_dual_types', None)
            if batch_dual is not None and nik not in batch_dual:
                batch_dual.append(nik)
                tg_send(f"🏢 NIK {nik} terdaftar RT+UM", chat_id=session.chat_id)
        if not valid:
            status_desc = "❌ Limit Bos" if status == "LIMIT" else f"❌ Gagal ({status})"
            update_batch_progress_card(session, idx, nik, status_desc)
            kembali_ke_beranda(page)
            return False, status
        
        if getattr(session, 'mode_kalem', False):
            time.sleep(2)
            
        checkout_success = False
        qty_transaksi = 1
        is_usaha_mikro = (selected_type == "USAHA MIKRO")
        
        if is_usaha_mikro:
            logging.info(f"[{session.chat_id}] 🏢 NIK adalah USAHA MIKRO. Mencoba kuantitas dari 5 down to 1...")
            try:
                page.wait_for_selector("[data-testid='btnCheckOrder']", timeout=10000)
                target_qty = 5
                
                while target_qty >= 2:
                    logging.info(f"[{session.chat_id}] Mencoba kuantitas {target_qty} tabung...")
                    adjust_success = False
                    try:
                        current_qty = page.evaluate("""
                            () => {
                                const minus = document.querySelector('[data-testid="actionIcon1"]');
                                const plus = document.querySelector('[data-testid="actionIcon2"]');
                                if (!minus || !plus) return null;
                                
                                const parent = minus.parentElement;
                                if (!parent) return null;
                                
                                const inputs = parent.querySelectorAll('input');
                                for (let input of inputs) {
                                    const val = parseInt(input.value);
                                    if (!isNaN(val) && val >= 1 && val <= 10) return val;
                                }
                                
                                const children = Array.from(parent.children);
                                for (let child of children) {
                                    if (child === minus || child === plus) continue;
                                    const val = parseInt(child.textContent?.trim() || '');
                                    if (!isNaN(val) && val >= 1 && val <= 10) return val;
                                }
                                return null;
                            }
                        """)
                        
                        if current_qty is None:
                            logging.warning(f"[{session.chat_id}] ⚠️ Tidak bisa membaca kuantitas awal, default ke 1.")
                            current_qty = 1
                            
                        logging.info(f"[{session.chat_id}] Kuantitas saat ini di page: {current_qty}, target: {target_qty}")
                        
                        plus_btn = page.get_by_test_id("actionIcon2")
                        minus_btn = page.get_by_test_id("actionIcon1")
                        
                        if target_qty > current_qty:
                            clicks = target_qty - current_qty
                            logging.info(f"[{session.chat_id}] Menaikkan kuantitas sebanyak {clicks} kali...")
                            for _ in range(clicks):
                                try:
                                    plus_btn.click(force=True, timeout=1000)
                                except Exception as err:
                                    logging.warning(f"[{session.chat_id}] Gagal klik plus standard/force: {err}. Coba via JS.")
                                    try:
                                        page.evaluate("() => { const el = document.querySelector('[data-testid=\"actionIcon2\"]'); if (el) el.click(); }")
                                    except Exception as js_err:
                                        logging.error(f"[{session.chat_id}] Gagal klik plus via JS: {js_err}")
                                time.sleep(0.25)
                        elif target_qty < current_qty:
                            clicks = current_qty - target_qty
                            logging.info(f"[{session.chat_id}] Menurunkan kuantitas sebanyak {clicks} kali...")
                            for _ in range(clicks):
                                try:
                                    minus_btn.click(force=True, timeout=1000)
                                except Exception as err:
                                    logging.warning(f"[{session.chat_id}] Gagal klik minus standard/force: {err}. Coba via JS.")
                                    try:
                                        page.evaluate("() => { const el = document.querySelector('[data-testid=\"actionIcon1\"]'); if (el) el.click(); }")
                                    except Exception as js_err:
                                        logging.error(f"[{session.chat_id}] Gagal klik minus via JS: {js_err}")
                                time.sleep(0.25)
                                
                        new_qty = page.evaluate("""
                            () => {
                                const minus = document.querySelector('[data-testid="actionIcon1"]');
                                const parent = minus ? minus.parentElement : null;
                                if (!parent) return null;
                                
                                const inputs = parent.querySelectorAll('input');
                                for (let input of inputs) {
                                    const val = parseInt(input.value);
                                    if (!isNaN(val) && val >= 1 && val <= 10) return val;
                                }
                                return null;
                            }
                        """)
                        logging.info(f"[{session.chat_id}] Kuantitas setelah penyesuaian: {new_qty}")
                        adjust_success = True
                    except Exception as click_err:
                        logging.error(f"[{session.chat_id}] Gagal menyesuaikan kuantitas via test-id: {click_err}")
                        
                    if not adjust_success:
                        break
                    
                    page.get_by_test_id("btnCheckOrder").click()
                    time.sleep(2)
                    
                    is_limit = False
                    # 1. Cek limit setelah CEK PESANAN
                    for sel in ["text=Melebihi Batas Kewajaran", "text=melebihi batas", "text=kuota", "text=tidak mencukupi", "text=maksimal", "text=melebihi"]:
                        try:
                            if page.locator(sel).first.is_visible(timeout=1000):
                                is_limit = True
                                err_text = page.locator(sel).first.inner_text()
                                logging.warning(f"[{session.chat_id}] Limit terdeteksi setelah CEK PESANAN pada qty {target_qty}: {err_text}")
                                break
                        except:
                            pass

                    # 2. Jika tidak ada limit, klik PROSES PENJUALAN untuk memicu limit sesungguhnya
                    if not is_limit:
                        try:
                            page.get_by_test_id("btnPay").click(timeout=3000)
                            time.sleep(2)
                            for sel in ["text=Melebihi Batas Kewajaran", "text=melebihi batas", "text=kuota", "text=tidak mencukupi", "text=maksimal", "text=melebihi"]:
                                if page.locator(sel).first.is_visible(timeout=1000):
                                    is_limit = True
                                    err_text = page.locator(sel).first.inner_text()
                                    logging.warning(f"[{session.chat_id}] Limit terdeteksi setelah PROSES PENJUALAN pada qty {target_qty}: {err_text}")
                                    break
                        except Exception as e:
                            logging.warning(f"[{session.chat_id}] Gagal klik PROSES PENJUALAN di dalam loop: {e}")
                    
                    if is_limit:
                        logging.info(f"[{session.chat_id}] Menutup popup limit kuantitas...")
                        close_generic_popup(page)
                        for btn_name in ["TUTUP", "Tutup", "OK", "Ok", "ok", "BATAL", "Batal", "OKE", "Oke"]:
                            try:
                                btn = page.get_by_role("button", name=btn_name).first
                                if btn.is_visible(timeout=300):
                                    btn.click(force=True)
                                    logging.info(f"[{session.chat_id}] Klik tombol '{btn_name}' (force) untuk menutup popup limit.")
                                    time.sleep(0.5)
                                    break
                            except:
                                pass
                                
                        try:
                            page.evaluate("""
                                () => {
                                    document.querySelectorAll('.modal-backdrop, .overlay, [class*="backdrop"]').forEach(el => el.remove());
                                    document.body.classList.remove('modal-open');
                                    document.body.style.overflow = '';
                                }
                            """)
                        except:
                            pass
                            
                        # Klik UBAH PESANAN jika berada di halaman Cek Penjualan
                        try:
                            ubah_btn = page.get_by_role("button", name="UBAH PESANAN").first
                            if ubah_btn.is_visible(timeout=2000):
                                logging.info(f"[{session.chat_id}] Klik 'UBAH PESANAN' untuk menyesuaikan kuantitas...")
                                ubah_btn.click()
                                time.sleep(1.5)
                        except:
                            pass
                            
                        time.sleep(1)
                        target_qty -= 1
                        if target_qty < 2:
                            break
                    else:
                        logging.info(f"[{session.chat_id}] ✅ Berhasil checkout dengan kuantitas: {target_qty} Tabung")
                        checkout_success = True
                        qty_transaksi = target_qty
                        break
                        
            except Exception as e:
                logging.error(f"[{session.chat_id}] Error saat memproses step-down qty Usaha Mikro: {e}")
        
        if not checkout_success:
            if is_usaha_mikro:
                logging.warning(f"[{session.chat_id}] ⚠️ Usaha Mikro gagal checkout hingga 2 tabung. Melewati NIK.")
                update_batch_progress_card(session, idx, nik, "❌ Gagal (Limit Usaha Mikro)")
                kembali_ke_beranda(page)
                return False, "LIMIT"
                
            logging.info(f"[{session.chat_id}] 💳 Checkout standar (1 Tabung)...")
            try:
                page.get_by_test_id("btnCheckOrder").click(timeout=8000)
                time.sleep(1.5)
                
                # Untuk checkout standar, kita juga harus klik PROSES PENJUALAN (btnPay) untuk melihat limit sesungguhnya
                try:
                    page.get_by_test_id("btnPay").click(timeout=3000)
                    time.sleep(1.5)
                except:
                    pass
                    
                is_limit = False
                for sel in ["text=Melebihi Batas Kewajaran", "text=melebihi batas", "text=kuota", "text=tidak mencukupi", "text=maksimal", "text=melebihi"]:
                    try:
                        if page.locator(sel).first.is_visible(timeout=1000):
                            is_limit = True
                            break
                    except:
                        pass
                
                if is_limit:
                    logging.error(f"[{session.chat_id}] Checkout standar LIMIT!")
                    update_batch_progress_card(session, idx, nik, "❌ Gagal (Limit Kuantitas)")
                    kembali_ke_beranda(page)
                    return False, "LIMIT"
                
                checkout_success = True
                qty_transaksi = 1
            except Exception as e:
                logging.error(f"[{session.chat_id}] Gagal klik Checkout standar: {e}")
                update_batch_progress_card(session, idx, nik, "❌ Gagal (Checkout Error)")
                kembali_ke_beranda(page)
                return False, "CHECKOUT_FAIL"
        
        logging.info(f"[{session.chat_id}] 🔄 Reset mouse state sebelum handle captcha...")
        for i in range(3):
            try:
                page.mouse.up()
                time.sleep(0.2)
            except:
                pass
        logging.info(f"[{session.chat_id}] ✅ Mouse state sudah di-reset")
        
        logging.info(f"[{session.chat_id}] 🔐 Handle captcha...")
        captcha_result = False
        max_captcha_attempts = 3
        
        for captcha_attempt in range(1, max_captcha_attempts + 1):
            logging.info(f"\n   {'─'*50}")
            logging.info(f"   [{session.chat_id}] 🔄 Captcha attempt {captcha_attempt}/{max_captcha_attempts}...")
            logging.info(f"   {'─'*50}")
            
            try:
                page.mouse.up()
                time.sleep(0.15)
                page.mouse.up()
                time.sleep(0.15)
            except:
                pass
            
            captcha_result = handle_captcha_slider(page)
            if captcha_result:
                logging.info(f"\n   {'='*50}")
                logging.info(f"   [{session.chat_id}] ✅✅✅ CAPTCHA BERHASIL DI ATTEMPT {captcha_attempt}")
                logging.info(f"   {'='*50}")
                break
            else:
                logging.warning(f"\n   {'='*50}")
                logging.warning(f"   [{session.chat_id}] ❌ CAPTCHA GAGAL DI ATTEMPT {captcha_attempt}")
                logging.warning(f"   {'='*50}")
                
                if captcha_attempt < max_captcha_attempts:
                    logging.info(f"   [{session.chat_id}] 🔄 Mencoba lagi dalam 2 detik...")
                    time.sleep(2)
                else:
                    logging.error(f"   [{session.chat_id}] ❌ Sudah mencoba {max_captcha_attempts}x, semua gagal")
        
        if not captcha_result:
            logging.error(f"   [{session.chat_id}] ❌ Captcha gagal setelah {max_captcha_attempts}x percobaan untuk NIK {nik}")
            update_batch_progress_card(session, idx, nik, "❌ Gagal Captcha")
            kembali_ke_beranda(page)
            return False, "CAPTCHA_GAGAL"
        
        logging.info(f"[{session.chat_id}] ⏳ Tunggu hasil transaksi...")
        time.sleep(3)
        
        transaksi_sukses = cek_hasil_transaksi(page, nik, session=session)
        if transaksi_sukses:
            qty_suffix = f" ({qty_transaksi} Tabung)" if qty_transaksi > 1 else ""
            update_batch_progress_card(session, idx, nik, f"✅ Sukses{qty_suffix}")
            kembali_ke_beranda(page)
            return True, "OK"
        else:
            logging.warning(f"   [{session.chat_id}] ⚠️ Status tidak jelas untuk NIK {nik}, anggap berhasil")
            qty_suffix = f" ({qty_transaksi} Tabung)" if qty_transaksi > 1 else ""
            update_batch_progress_card(session, idx, nik, f"✅ Sukses{qty_suffix} (Unclear)")
            kembali_ke_beranda(page)
            return True, "OK"
            
    except Exception as e:
        logging.error(f"   [{session.chat_id}] ❌ Error proses NIK {nik}: {e}")
        logging.error(traceback.format_exc())
        update_batch_progress_card(session, idx, nik, "❌ Gagal (Error)")
        kembali_ke_beranda(page)
        return False, "ERROR"
    finally:
        try:
            if page.locator("text=telah transaksi 10 NIK").is_visible():
                logging.info(f"[{session.chat_id}] Server butuh jeda 1 menit setelah 10 NIK.")
                tg_send("☕️ Istirahat bentar ya, server lagi capek (limit 10 NIK). Tunggu 1 menit...", chat_id=session.chat_id)
                time.sleep(60)
        except:
            pass
        try:
            kembali_ke_beranda(page)
        except Exception as e:
            logging.warning(f"[{session.chat_id}] Gagal kembali ke beranda di finally: {e}")

def worker_loop(session):
    import requests # imported again to be thread safe if needed
    while True:
        session.run_event.wait()
        if not session.run_event.is_set(): continue
        session.stop_requested = False

        logging.info(f"[{session.chat_id}] Worker diaktifkan, memulai sesi Playwright...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=is_headless())
                is_batch = session.queue_file.exists() or session.nik_file.exists()
                context, page, success = inisialisasi_sesi_akun(browser, session, silent=is_batch)
                try:
                    if not success:
                        session.consecutive_errors += 1
                        logging.warning(f"[{session.chat_id}] Login gagal (error ke-{session.consecutive_errors})")
                        
                        if session.consecutive_errors >= 3:
                            logging.error(f"[{session.chat_id}] Login gagal 3x berturut-turut, reset state")
                            session.reset_state(force=True)
                            tg_send_menu("❌ Login gagal 3x berturut-turut. Bot di-reset. Coba lagi nanti.", chat_id=session.chat_id)
                        else:
                            tg_send("⚠️ Login gagal, akan coba lagi dalam 10 detik...", chat_id=session.chat_id)
                            time.sleep(10)
                        continue
                    
                    session.consecutive_errors = 0

                    while session.run_event.is_set():
                        idle_duration = time.time() - session.last_activity_time
                        if idle_duration > IDLE_TIMEOUT_SECONDS:
                            logging.warning(f"[{session.chat_id}] ⏱️ Bot nganggur selama {int(idle_duration)} detik. Auto-logout untuk hindari bot error...")
                            session.reset_state(force=True)
                            clear_terminal()
                            tg_send_menu(f"😴 Bot nganggur {int(idle_duration//60)} menit.\n\nSilahkan login ulang.", chat_id=session.chat_id, force_home=True)
                            break
                        
                        if session.cek_flag.exists():
                            session.cek_flag.unlink(missing_ok=True)
                            session.last_activity_time = time.time()
                            cek_stok(page, session)
                        
                        daftar = read_lines(session.queue_file) if session.queue_file.exists() else []
                        if not daftar:
                            if session.reset_queue_flag:
                                logging.info(f"[{session.chat_id}] ⚠️ RESET FLAG terdeteksi, skip membaca nik_file")
                                session.reset_queue_flag = False
                                continue
                            
                            incoming = read_lines(session.nik_file)
                            if incoming:
                                logging.info(f"[{session.chat_id}] Memindahkan {len(incoming)} NIK ke antrian.")
                                session.last_activity_time = time.time()
                                try: session.nik_file.replace(session.queue_file)
                                except Exception: write_lines(session.queue_file, incoming); write_lines(session.nik_file, [])
                                daftar = read_lines(session.queue_file)

                        if daftar:
                            session.last_activity_time = time.time()
                            total_awal = len(daftar)
                            processed_ok, processed_fail, processed_limit = [], [], []
                            session._batch_dual_types = []
                            session.total_awal = total_awal
                            session.batch_card_msg_id = None
                            session.batch_results = []
                            logging.info(f"[{session.chat_id}] Memproses {total_awal} NIK dari antrian...")

                            while session.run_event.is_set() and daftar:
                                if getattr(session, 'stop_requested', False) or not session.run_event.is_set():
                                    logging.info(f"[{session.chat_id}] 🛑 Stop terdeteksi! Membatalkan sisa {len(daftar)} NIK di antrian...")
                                    daftar = []
                                    try:
                                        if session.queue_file.exists(): session.queue_file.unlink(missing_ok=True)
                                        if session.nik_file.exists(): session.nik_file.unlink(missing_ok=True)
                                    except Exception: pass
                                    break
                                    
                                if session.reset_queue_flag:
                                    logging.info(f"[{session.chat_id}] ⚠️ RESET ANTRIAN terdeteksi! Membaca ulang queue file...")
                                    session.reset_queue_flag = False
                                    
                                    daftar = read_lines(session.queue_file) if session.queue_file.exists() else []
                                    if not daftar:
                                        logging.info(f"[{session.chat_id}] ✅ Queue sudah kosong, menghentikan batch.")
                                        break
                                    else:
                                        logging.info(f"[{session.chat_id}] Masih ada {len(daftar)} NIK di queue setelah reload, melanjutkan...")
                                        total_awal = len(daftar)
                                
                                nik = daftar.pop(0)
                                idx = total_awal - len(daftar)

                                if page.is_closed() or 'login' in page.url:
                                    logging.warning(f"[{session.chat_id}] Sesi/halaman terputus, memuat ulang sesi...")
                                    daftar.insert(0, nik)
                                    if page.is_closed():
                                        with contextlib.suppress(Exception): context.close()
                                        context, page, success = inisialisasi_sesi_akun(browser, session, is_recovery=True, silent=True)
                                        if not success:
                                            logging.error(f"[{session.chat_id}] Gagal inisialisasi ulang sesi, menghentikan batch.")
                                            break
                                    elif not login_dengan_retry(page, session, silent=True):
                                        logging.error(f"[{session.chat_id}] Gagal login ulang, menghentikan batch.")
                                        break
                                    continue
                                
                                ok, status = proses_nik(page, nik, idx, session)
                                session.last_activity_time = time.time()
                                if ok:
                                    session.consecutive_errors = 0
                                    processed_ok.append(nik)
                                elif status == "LIMIT":
                                    processed_limit.append(nik)
                                else: 
                                    processed_fail.append(nik)
                                    if page.is_closed():
                                        logging.warning(f"[{session.chat_id}] Browser/Halaman tertutup saat proses NIK. Memulihkan sesi...")
                                        with contextlib.suppress(Exception): context.close()
                                        context, page, success = inisialisasi_sesi_akun(browser, session, is_recovery=True, silent=True)
                                        if not success:
                                            logging.error(f"[{session.chat_id}] Gagal pemulihan sesi Playwright.")
                                            break
                                    else:
                                        try:
                                            logging.info(f"[{session.chat_id}] Gagal/ERROR (Status: {status}). Merefresh halaman...")
                                            page.reload(timeout=20000)
                                            time.sleep(3.5)
                                        except Exception as refresh_err:
                                            logging.warning(f"[{session.chat_id}] Gagal reload halaman: {refresh_err}")
                                            if page.is_closed() or "closed" in str(refresh_err).lower():
                                                with contextlib.suppress(Exception): context.close()
                                                context, page, success = inisialisasi_sesi_akun(browser, session, is_recovery=True, silent=True)
                                                if not success:
                                                    break
                                        if 'login' in page.url:
                                            logging.warning(f"[{session.chat_id}] Terdeteksi logout setelah refresh. Relogin...")
                                            if not login_dengan_retry(page, session, silent=True):
                                                logging.error(f"[{session.chat_id}] Relogin gagal. Membatalkan sisa antrian.")
                                                daftar.insert(0, nik)
                                                break
                                write_lines(session.queue_file, daftar)
                                time.sleep(1)

                            if not daftar and session.queue_file.exists():
                                session.queue_file.unlink(missing_ok=True)
                                dual_type_all = getattr(session, '_batch_dual_types', [])
                                total = len(processed_ok) + len(processed_fail) + len(processed_limit)
                                if total > 0:
                                    update_batch_progress_card(session, total, "", "", is_final=True)
                                    stok_akhir_text = "Tidak diketahui"
                                    try:
                                        kembali_ke_beranda(page)
                                        time.sleep(1)
                                        stok_akhir_text = ambil_sisa_stok(page)
                                    except:
                                        pass

                                    dual_type_all = getattr(session, '_batch_dual_types', [])
                                    
                                    emoji_prefix = "🪷" if getattr(session, 'mode_kalem', False) else "✅"
                                    lines = [
                                        f"{emoji_prefix} [{session.nama_pangkalan}]\nNIK Sudah Diproses",
                                        "━━━━━━━━━━━━━━━━━",
                                        f"Total         : {total}",
                                        f"Sukses        : {len(processed_ok)}",
                                        f"Usaha Mikro   : {len(dual_type_all)}",
                                        f"Gagal/Limit   : {len(processed_fail) + len(processed_limit)}",
                                        f"Stok akhir    : {stok_akhir_text}"
                                    ]
                                        
                                    logging.info(f"[{session.chat_id}] Laporan batch dikirim.")
                                    tg_send_menu("\n".join(lines), chat_id=session.chat_id)
                                    
                                    file_laporan = session.user_dir / "laporan_hasil.txt"
                                    txt_lines = []
                                    if processed_ok:
                                        txt_lines.append("✅ NIK Sukses:")
                                        txt_lines.extend(processed_ok)
                                        txt_lines.append("")
                                    if dual_type_all:
                                        txt_lines.append("🏢 NIK Terdaftar Usaha Mikro:")
                                        txt_lines.extend(dual_type_all)
                                        txt_lines.append("")
                                    all_fails = processed_fail + processed_limit
                                    if all_fails:
                                        txt_lines.append("❌ NIK Gagal/Limit:")
                                        txt_lines.extend(all_fails)
                                    
                                    if txt_lines:
                                        write_lines(file_laporan, txt_lines)
                                        tg_send_document(str(file_laporan), "Laporan NIK", chat_id=session.chat_id)
                                        try:
                                            file_laporan.unlink(missing_ok=True)
                                        except:
                                            pass
                                    
                                    if session.batch_msg_ids:
                                        logging.info(f"[{session.chat_id}] Coba menghapus {len(session.batch_msg_ids)} pesan riwayat NIK...")
                                        try:
                                            for b_idx in range(0, len(session.batch_msg_ids), 100):
                                                chunk = session.batch_msg_ids[b_idx:b_idx+100]
                                                requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/deleteMessages", json={
                                                    "chat_id": session.chat_id,
                                                    "message_ids": chunk
                                                }, timeout=10)
                                        except Exception as e:
                                            logging.warning(f"Gagal menghapus pesan {e}")
                                        session.batch_msg_ids = []
                            
                            # Hapus cookie sementara setelah seluruh batch selesai
                            if hasattr(session, 'delete_all_cookies'):
                                session.delete_all_cookies()
                            
                            try:
                                kembali_ke_beranda(page)
                            except Exception as e:
                                logging.warning(f"[{session.chat_id}] Gagal kembali ke beranda setelah batch: {e}")
                        time.sleep(2)
                
                except Exception as browser_error:
                    session.consecutive_errors += 1
                    logging.error(f"[{session.chat_id}] Error di browser (error ke-{session.consecutive_errors}): {browser_error}")
                    
                    if session.consecutive_errors >= 3:
                        logging.critical(f"[{session.chat_id}] !!! ERROR KRITIS 3x berturut-turut di dalam sesi browser !!!\n{traceback.format_exc()}")
                        tg_send(f"⚠️ Waduh error parah 3x berturut-turut di [{SCRIPT_NAME}]. Bot di-reset, coba lagi nanti.", chat_id=session.chat_id)
                        session.reset_state(force=True)
                    else:
                        logging.warning(f"[{session.chat_id}] Error di browser, akan retry dalam 5 detik...")
                        tg_send(f"⚠️ Ada error, akan coba lagi otomatis dalam 5 detik...", chat_id=session.chat_id)
                        time.sleep(5)
                finally:
                    logging.info(f"[{session.chat_id}] Menutup sesi browser & membersihkan cookie & queue temporary...")
                    if hasattr(session, 'delete_all_cookies'):
                        session.delete_all_cookies()
                    try:
                        if session.nik_file.exists(): session.nik_file.unlink(missing_ok=True)
                        if session.queue_file.exists(): session.queue_file.unlink(missing_ok=True)
                    except Exception: pass
                    try:
                        context.close()
                        browser.close()
                    except:
                        pass
        
        except Exception as playwright_error:
            session.consecutive_errors += 1
            if session.consecutive_errors >= 3:
                logging.critical(f"[{session.chat_id}] !!! ERROR FATAL 3x berturut-turut pada Playwright/Worker !!!\n{traceback.format_exc()}")
                tg_send(f"⚠️ Error fatal 3x berturut-turut pada worker [{SCRIPT_NAME}]. Bot di-reset.", chat_id=session.chat_id)
                session.reset_state(force=True)
            else:
                logging.error(f"[{session.chat_id}] Error pada Playwright/Worker (error ke-{session.consecutive_errors}): {playwright_error}")
                tg_send(f"⚠️ Ada error pada worker, akan coba lagi otomatis...", chat_id=session.chat_id)
                time.sleep(5)
