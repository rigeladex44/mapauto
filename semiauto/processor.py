import os
import sys
import time
import random
import logging
import threading
from pathlib import Path
from playwright.sync_api import sync_playwright, Page, BrowserContext, Browser

try:
    from config import (
        BASE_URL, LOGIN_URL, BERANDA_URL, VERIFIKASI_NIK_URL, SALE_URL_KEYWORD,
        HEADLESS, BROWSER_VIEWPORT, COOKIES_DIR,
        SUKSES_FILE, LIMIT_FILE, TIDAK_DITEMUKAN_FILE, SKIP_FILE
    )
    from captcha_solver import handle_captcha_slider
except ImportError:
    from .config import (
        BASE_URL, LOGIN_URL, BERANDA_URL, VERIFIKASI_NIK_URL, SALE_URL_KEYWORD,
        HEADLESS, BROWSER_VIEWPORT, COOKIES_DIR,
        SUKSES_FILE, LIMIT_FILE, TIDAK_DITEMUKAN_FILE, SKIP_FILE
    )
    from .captcha_solver import handle_captcha_slider

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

def append_to_file(file_path: Path, text: str):
    """Menambahkan baris ke file riwayat"""
    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(text.strip() + "\n")
    except Exception as e:
        logging.error(f"Gagal menulis ke {file_path}: {e}")

def sanitize_name(name: str) -> str:
    if not name:
        return "UNKNOWN"
    return "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name.upper())

def find_existing_cookie(account_name: str) -> Path or None:
    """Mencari file cookie di semiauto/cookies"""
    safe_name = sanitize_name(account_name)
    local_cookie = COOKIES_DIR / f"{safe_name}.json"
    if local_cookie.exists():
        return local_cookie
    return None

def close_location_popup(page: Page):
    """Tutup popup lokasi jika muncul"""
    try:
        page.keyboard.press("Escape")
        selectors = [
            "button[aria-label*='close' i]", "button[aria-label*='tutup' i]",
            "button:has-text('×')", "button:has-text('✕')", ".close", "[class*='close']"
        ]
        for sel in selectors:
            try:
                btn = page.locator(sel).first
                if btn.is_visible(timeout=300):
                    btn.click()
                    time.sleep(0.2)
                    break
            except Exception:
                continue
    except Exception:
        pass

def close_generic_popup(page: Page):
    """Tutup modal popup generik kecuali captcha"""
    try:
        if page.locator(".rc-slider-captcha").first.is_visible(timeout=200):
            return
        page.keyboard.press("Escape")
    except Exception:
        pass

class SemiAutoProcessor:
    def __init__(self, account_name: str, email: str, pin: str, allowed_types: list = None):
        self.account_name = account_name
        self.email = email
        self.pin = pin
        self.allowed_types = allowed_types or ["USAHA MIKRO", "RUMAH TANGGA"]
        self.playwright = None
        self.browser: Browser = None
        self.context: BrowserContext = None
        self.page: Page = None
        self.is_running = False
        self.stop_requested = False

    def start_browser(self) -> bool:
        """Membuka browser Playwright dengan tampilan UI (headed)"""
        logging.info("🚀 Membuka browser Chromium (Mode Semi-Manual Tampil di Layar)...")
        self.playwright = sync_playwright().start()
        
        cookie_path = find_existing_cookie(self.account_name)
        storage_state = str(cookie_path) if (cookie_path and cookie_path.exists()) else None

        self.browser = self.playwright.chromium.launch(
            headless=HEADLESS,
            args=[
                "--start-maximized",
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox"
            ]
        )

        context_kwargs = {
            "no_viewport": True,
            "ignore_https_errors": True
        }
        if storage_state:
            logging.info(f"🍪 Memuat session cookies tersimpan: {cookie_path}")
            context_kwargs["storage_state"] = storage_state

        self.context = self.browser.new_context(**context_kwargs)
        self.page = self.context.new_page()
        return True

    def login(self) -> bool:
        """Login ke akun merchant Pertamina atau verifikasi cookie"""
        try:
            logging.info("🌐 Mengecek status sesi akun...")
            self.page.goto(BERANDA_URL, timeout=30000)
            time.sleep(3)
            close_location_popup(self.page)
            close_generic_popup(self.page)

            # Cek apakah sudah di beranda
            if "login" not in self.page.url and "/merchant/app" in self.page.url:
                logging.info(f"✅ Sesi cookie aktif! Berhasil masuk sebagai: {self.account_name}")
                self.save_cookies()
                return True

            logging.info("🔑 Melakukan login menggunakan Email & PIN...")
            self.page.goto(LOGIN_URL, timeout=30000)
            time.sleep(2)

            self.page.get_by_role("textbox", name="Nomor ponsel atau email").fill(self.email)
            time.sleep(1)
            self.page.get_by_role("textbox", name="PIN").fill(self.pin)
            time.sleep(1)

            try:
                self.page.get_by_role("button", name="Masuk").click(timeout=5000)
            except Exception:
                self.page.get_by_role("button", name="Masuk").click(force=True)

            logging.info("⏳ Menunggu verifikasi login...")
            start_time = time.time()
            while time.time() - start_time < 25:
                time.sleep(1)
                curr_url = self.page.url
                if "/merchant/app" in curr_url and "login" not in curr_url:
                    logging.info(f"✅ Login Berhasil untuk {self.account_name}!")
                    time.sleep(2)
                    self.save_cookies()
                    return True
                
                # Cek teks error login
                for err_text in ["Email atau PIN salah", "Akun tidak valid", "Login gagal"]:
                    if self.page.locator(f"text={err_text}").first.is_visible(timeout=300):
                        logging.error(f"❌ Login Gagal: {err_text}")
                        return False

            logging.warning("⚠️ Timeout menunggu beranda setelah login, periksa tampilan browser.")
            return False

        except Exception as e:
            logging.error(f"❌ Error saat login: {e}")
            return False

    def save_cookies(self):
        """Menyimpan session cookies"""
        try:
            safe_name = sanitize_name(self.account_name)
            target_path = COOKIES_DIR / f"{safe_name}.json"
            self.context.storage_state(path=str(target_path))
            logging.info(f"💾 Storage state disimpan ke {target_path}")
        except Exception as e:
            logging.warning(f"⚠️ Gagal menyimpan cookie: {e}")

    def buka_halaman_input_nik(self) -> bool:
        """Navigasi ke halaman verifikasi NIK melalui Beranda -> Klik Catat Penjualan"""
        try:
            # Jika sudah di halaman input NIK dan elemennya ada
            if "/verification-nik" in self.page.url:
                try:
                    if self.page.locator("[data-testid='btnCheckNik']").is_visible(timeout=2000):
                        return True
                except Exception:
                    pass

            # Cek jika ada layar "Halaman Tidak Ditemukan", klik "KEMBALI KE BERANDA"
            try:
                kembali_btn = self.page.locator("text=KEMBALI KE BERANDA").first
                if kembali_btn.is_visible(timeout=1000):
                    logging.info("🔄 Terdeteksi layar 'Halaman Tidak Ditemukan', mengklik 'KEMBALI KE BERANDA'...")
                    kembali_btn.click()
                    time.sleep(2)
            except Exception:
                pass

            logging.info("📄 Masuk ke Beranda untuk klik 'Catat Penjualan'...")
            self.page.goto(BERANDA_URL, timeout=25000)
            time.sleep(2.5)
            close_location_popup(self.page)
            close_generic_popup(self.page)

            catat_selectors = [
                "text=Catat Penjualan",
                "button:has-text('Catat Penjualan')",
                "div:has-text('Catat Penjualan')",
                "a:has-text('Catat Penjualan')",
                "[data-testid='btnSale']"
            ]

            clicked = False
            for sel in catat_selectors:
                try:
                    el = self.page.locator(sel).first
                    if el.is_visible(timeout=2500):
                        el.click()
                        logging.info("✅ Berhasil klik 'Catat Penjualan'")
                        clicked = True
                        time.sleep(2)
                        break
                except Exception:
                    continue

            if not clicked:
                logging.info("Mencoba navigasi langsung ke verification-nik...")
                self.page.goto(VERIFIKASI_NIK_URL, timeout=20000)
                time.sleep(2)

            self.page.wait_for_selector("[data-testid='btnCheckNik']", timeout=12000)
            logging.info("✅ Siap di halaman Catat Penjualan (Input NIK)")
            return True
        except Exception as e:
            logging.error(f"❌ Gagal membuka halaman input NIK: {e}")
            return False

    def handle_nib_popup(self):
        """Handle popup NIB bila muncul"""
        try:
            lengkapi_btn = self.page.get_by_role("button", name="LENGKAPI NIB").first
            if lengkapi_btn.is_visible(timeout=1500):
                logging.info("   ℹ️ Terdeteksi popup Lengkapi NIB, melakukan bypass otomatis...")
                lengkapi_btn.click()
                time.sleep(1)

                mengerti_btn = self.page.get_by_role("button", name="MENGERTI").first
                if mengerti_btn.is_visible(timeout=1500):
                    mengerti_btn.click()
                    time.sleep(1)

                lanjut_perbarui = self.page.get_by_role("button", name="LANJUT PERBARUI DATA PELANGGAN").first
                if lanjut_perbarui.is_visible(timeout=1500):
                    lanjut_perbarui.click()
                    time.sleep(1)

                nib_input = self.page.get_by_placeholder("Masukkan nomor induk berusaha")
                if not nib_input.is_visible(timeout=2000):
                    nib_input = self.page.locator("input[type='text'], input[type='number']").last
                
                if nib_input.is_visible(timeout=3000):
                    random_nib = "".join([str(random.randint(0, 9)) for _ in range(13)])
                    nib_input.fill(random_nib)
                    time.sleep(0.5)
                    cek_btn = self.page.get_by_role("button", name="CEK NIB").first
                    if cek_btn.is_visible(timeout=1000):
                        cek_btn.click()
                        time.sleep(1.5)
                    lanjut_btn = self.page.get_by_role("button", name="LANJUT TRANSAKSI").first
                    if lanjut_btn.is_visible(timeout=2000):
                        lanjut_btn.click()
                        time.sleep(1)
                return

            # Fallback Nanti Saja
            nanti_btn = self.page.get_by_role("button", name="NANTI SAJA, LANJUT TRANSAKSI").first
            if nanti_btn.is_visible(timeout=1000):
                nanti_btn.click()
                time.sleep(1)
        except Exception:
            pass

    def input_nik_dan_periksa(self, nik: str) -> tuple[bool, str]:
        """
        Input NIK dan proses sampai masuk ke halaman /merchant/app/sale.
        Return: (sukses_ke_sale: bool, status_code: str)
        status_code: 'SALE_READY', 'LIMIT', 'TIDAK_DITEMUKAN', 'ERROR'
        """
        try:
            if "/verification-nik" not in self.page.url:
                self.buka_halaman_input_nik()

            logging.info(f"📝 [Auto] Memasukkan NIK: {nik}")
            input_box = self.page.get_by_role("combobox", name="Masukkan 16 digit NIK")
            input_box.fill("")
            time.sleep(0.2)
            input_box.fill(nik)
            time.sleep(0.5)

            # Klik tombol cek / lanjutkan penjualan
            try:
                lanjut_btn = self.page.get_by_role("button", name="LANJUTKAN PENJUALAN").first
                if lanjut_btn.is_visible(timeout=2000):
                    lanjut_btn.click()
                else:
                    self.page.get_by_test_id("btnCheckNik").first.click()
            except Exception:
                self.page.get_by_test_id("btnCheckNik").first.click()

            time.sleep(2)

            # Cek modal pilihan jenis pelanggan
            if self.page.locator("text=jenis pelanggan di bawah ini").is_visible(timeout=2000):
                logging.info("   ℹ️ Terdeteksi Multi-Type Pelanggan. Memilih tipe sesuai preferensi...")
                pilihan_sukses = False
                for tipe in self.allowed_types:
                    try:
                        el_opsi = self.page.locator(f"text={tipe}").first
                        if el_opsi.is_visible(timeout=500):
                            logging.info(f"   👉 Memilih opsi: {tipe}")
                            el_opsi.click()
                            time.sleep(1.5)

                            # Cek apakah limit setelah pilih opsi
                            is_limit = False
                            for msg in ["text=Tidak dapat transaksi", "text=melebihi batas kewajaran"]:
                                if self.page.locator(msg).first.is_visible(timeout=500):
                                    is_limit = True
                                    break
                            if is_limit:
                                logging.warning(f"   ⚠️ NIK {nik} ({tipe}) terdeteksi LIMIT.")
                                try:
                                    self.page.get_by_role("button", name="TUTUP").click()
                                except Exception:
                                    pass
                                return False, "LIMIT"

                            btn_lanjut = self.page.get_by_role("button", name="LANJUTKAN TRANSAKSI")
                            if btn_lanjut.is_visible(timeout=1000):
                                btn_lanjut.click()
                                time.sleep(1.5)
                                self.handle_nib_popup()
                                pilihan_sukses = True
                                break
                    except Exception:
                        continue

                if not pilihan_sukses:
                    logging.warning(f"   ⚠️ Tidak ada opsi jenis pelanggan yang cocok untuk NIK {nik}.")
                    try:
                        self.page.get_by_role("button", name="TUTUP").click()
                    except Exception:
                        pass
                    return False, "TIDAK_COCOK"

            else:
                # Cek jika tidak muncul modal: apakah LIMIT atau TIDAK DITEMUKAN
                if self.page.locator("text=melebihi batas kewajaran").is_visible(timeout=1500) or \
                   self.page.locator("text=kuota").is_visible(timeout=500):
                    logging.warning(f"   ⚠️ NIK {nik} terdeteksi LIMIT.")
                    return False, "LIMIT"

                if self.page.locator("text=tidak ditemukan").is_visible(timeout=500) or \
                   self.page.locator("text=tidak terdaftar").is_visible(timeout=500):
                    logging.warning(f"   ⚠️ NIK {nik} TIDAK DITEMUKAN / TIDAK TERDAFTAR.")
                    return False, "TIDAK_DITEMUKAN"

                # Klik Lanjutkan Transaksi jika ada tombol modal/halaman
                for btn_name in ["LANJUTKAN TRANSAKSI", "Lanjut Transaksi"]:
                    try:
                        b = self.page.get_by_role("button", name=btn_name).first
                        if b.is_visible(timeout=1000):
                            b.click()
                            time.sleep(1)
                            break
                    except Exception:
                        continue

                self.handle_nib_popup()

            # Tunggu transisi ke halaman sale
            start_wait = time.time()
            while time.time() - start_wait < 15:
                if SALE_URL_KEYWORD in self.page.url:
                    return True, "SALE_READY"
                time.sleep(0.5)

            if SALE_URL_KEYWORD in self.page.url:
                return True, "SALE_READY"

            logging.warning(f"   ⚠️ Halaman sale belum terbuka (URL: {self.page.url})")
            return False, "TIMEOUT_SALE"

        except Exception as e:
            logging.error(f"❌ Error saat input & verifikasi NIK: {e}")
            return False, "ERROR"

    def tunggu_proses_manual_di_sale(self, nik: str) -> str:
        """
        1. Menunggu user manual mengatur kuantitas & klik 'CEK PESANAN' (atau tekan ENTER).
        2. Setelah itu, Bot OTOMATIS:
           - Klik 'PROSES PENJUALAN'
           - Menangani popup limit jika ada
           - Menyelesaikan Slider Captcha secara otomatis
           - Menunggu status berhasil & klik 'Ke Beranda'
        Return status: 'SUKSES', 'LIMIT', 'SKIP', 'STOP'
        """
        print("\a", end="")  # Bunyi beep terminal
        print("\n" + "="*70)
        print(f"👉 [MANUAL TIME] NIK: {nik}")
        print("💡 Silakan atur KUANTITAS tabung di layar browser:")
        print("   - Atur jumlah tabung [-] / [+]")
        print("   - Klik tombol hijau 'CEK PESANAN' (atau tekan [ENTER] di sini)")
        print("----------------------------------------------------------------------")
        print("⚡ Setelah 'Cek Pesanan' selesai, Bot akan OTOMATIS:")
        print("   🤖 Klik 'PROSES PENJUALAN'")
        print("   🧩 Selesaikan SLIDER CAPTCHA secara otomatis")
        print("   🎉 Pastikan transaksi sukses lalu lanjut NIK berikutnya!")
        print("⌨️  Perintah di Terminal:")
        print("   [ENTER]        : Lanjut / Bantu klik Cek Pesanan")
        print("   Ketik 's' + ↵ : SKIP NIK ini")
        print("   Ketik 'q' + ↵ : STOP seluruh proses antrean")
        print("="*70 + "\n")

        user_input_command = [None]

        def input_listener():
            try:
                cmd = input().strip().lower()
                user_input_command[0] = cmd if cmd else "next"
            except Exception:
                pass

        listener_thread = threading.Thread(target=input_listener, daemon=True)
        listener_thread.start()

        # FASE 1: Tunggu User Mengatur Kuantitas / Klik CEK PESANAN
        cek_pesanan_selesai = False
        while not cek_pesanan_selesai:
            if user_input_command[0] is not None:
                cmd = user_input_command[0]
                if cmd == "q":
                    logging.info("🛑 User meminta berhenti (STOP).")
                    return "STOP"
                elif cmd == "s":
                    logging.info(f"⏭️ User memilih SKIP NIK {nik}.")
                    return "SKIP"
                else:
                    # User tekan ENTER di terminal, bot bantu klik CEK PESANAN jika belum diklik
                    logging.info("⏩ User menekan [ENTER], melanjutkan proses...")
                    try:
                        btn_cek = self.page.locator("[data-testid='btnCheckOrder']").first
                        if not btn_cek.is_visible(timeout=500):
                            btn_cek = self.page.get_by_role("button", name="CEK PESANAN").first
                        if btn_cek.is_visible(timeout=1000):
                            btn_cek.click()
                            time.sleep(1.5)
                    except Exception:
                        pass
                    cek_pesanan_selesai = True
                    break

            try:
                if self.page.is_closed():
                    return "STOP"

                # Cek jika tombol PROSES PENJUALAN sudah muncul (artinya CEK PESANAN sudah diklik oleh user di browser)
                btn_pay_selectors = [
                    "[data-testid='btnPay']",
                    "button:has-text('PROSES PENJUALAN')",
                    "button:has-text('Proses Penjualan')",
                    "text=PROSES PENJUALAN"
                ]
                for p_sel in btn_pay_selectors:
                    if self.page.locator(p_sel).first.is_visible(timeout=300):
                        logging.info("✅ 'CEK PESANAN' terdeteksi telah diklik oleh user di browser!")
                        cek_pesanan_selesai = True
                        break

                # Cek jika tombol CEK PESANAN sudah tidak ada dan halaman sudah masuk captcha/berhasil
                if not cek_pesanan_selesai:
                    if self.page.locator(".rc-slider-captcha").first.is_visible(timeout=200):
                        cek_pesanan_selesai = True
                        break
                    if self.page.locator("text=Ke Beranda").first.is_visible(timeout=200):
                        return "SUKSES"

            except Exception:
                pass

            time.sleep(0.5)

        time.sleep(1)

        # FASE 2: OTOMATIS KLIK PROSES PENJUALAN
        logging.info("🤖 [Otomatis] Mendeteksi tombol 'PROSES PENJUALAN'...")
        try:
            btn_pay_clicked = False
            for p_sel in ["[data-testid='btnPay']", "button:has-text('PROSES PENJUALAN')", "button:has-text('Proses Penjualan')"]:
                try:
                    pay_btn = self.page.locator(p_sel).first
                    if pay_btn.is_visible(timeout=3000):
                        pay_btn.click()
                        logging.info("✅ [Otomatis] Berhasil klik 'PROSES PENJUALAN'!")
                        btn_pay_clicked = True
                        time.sleep(1.5)
                        break
                except Exception:
                    continue

            # Cek apakah limit kuantitas muncul setelah klik bayar
            for limit_sel in ["text=Melebihi Batas Kewajaran", "text=melebihi batas", "text=kuota", "text=tidak mencukupi"]:
                if self.page.locator(limit_sel).first.is_visible(timeout=800):
                    logging.warning(f"⚠️ NIK {nik} terdeteksi LIMIT pada kuantitas ini!")
                    close_generic_popup(self.page)
                    return "LIMIT"

        except Exception as e:
            logging.warning(f"⚠️ Error saat klik proses penjualan: {e}")

        # FASE 3: OTOMATIS SELESAIKAN CAPTCHA SLIDER
        logging.info("🤖 [Otomatis] Menunggu kemunculan Slider Captcha...")
        captcha_visible = False
        wait_start = time.time()
        while time.time() - wait_start < 10:
            if self.page.locator(".rc-slider-captcha").first.is_visible(timeout=400):
                captcha_visible = True
                break
            if self.page.locator("text=Ke Beranda").first.is_visible(timeout=400):
                # Sudah langsung berhasil tanpa captcha
                break
            time.sleep(0.5)

        if captcha_visible:
            logging.info("🧩 [Otomatis] Slider Captcha terdeteksi! Memulai penyelesaian otomatis...")
            max_attempts = 4
            for attempt in range(1, max_attempts + 1):
                logging.info(f"   🔄 Captcha attempt {attempt}/{max_attempts}...")
                success = handle_captcha_slider(self.page)
                if success:
                    logging.info("   ✅✅✅ CAPTCHA BERHASIL DISELESAIKAN SECARA OTOMATIS!")
                    break
                time.sleep(2)

        # FASE 4: MENUNGGU TRANSAKSI BERHASIL
        logging.info("⏳ [Otomatis] Menunggu konfirmasi transaksi berhasil...")
        success_wait_start = time.time()
        while time.time() - success_wait_start < 15:
            try:
                # Tombol "Ke Beranda"
                if self.page.locator("text=Ke Beranda").first.is_visible(timeout=500):
                    logging.info("🎉 Transaksi BERHASIL! (Tombol 'Ke Beranda' terdeteksi)")
                    try:
                        self.page.get_by_role("link", name="Ke Beranda").click()
                        time.sleep(1.5)
                    except Exception:
                        pass
                    return "SUKSES"

                # Teks transaksi berhasil
                for txt in ["text=transaksi berhasil", "text=pembayaran berhasil", "text=Transaksi Berhasil", "text=Berhasil!"]:
                    if self.page.locator(txt).first.is_visible(timeout=500):
                        logging.info(f"🎉 Transaksi BERHASIL ({txt})!")
                        time.sleep(1.5)
                        return "SUKSES"

                # Sudah keluar dari URL sale
                if SALE_URL_KEYWORD not in self.page.url and ("merchant/app" in self.page.url or "success" in self.page.url):
                    logging.info(f"🎉 Transaksi BERHASIL! (URL berubah ke: {self.page.url})")
                    return "SUKSES"

            except Exception:
                pass
            time.sleep(0.5)

        logging.warning("⚠️ Status transaksi tidak jelas setelah timeout, namun dianggap selesai.")
        return "SUKSES"

    def close(self):
        """Menutup browser dan playwright"""
        try:
            if self.context:
                self.context.close()
            if self.browser:
                self.browser.close()
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass
