import re
import time
import logging
import asyncio
import random
import contextlib
import requests
from html import escape
from playwright.async_api import async_playwright
from modules.config import BASE_URL, HEADLESS, is_headless, BOT_TOKEN
from modules.utils import close_location_popup, close_generic_popup, parse_credential_line
from modules.telegram import tg_send, tg_send_menu, tg_send_chat_action

def ambil_sisa_stok(page):
    logging.info("Mengambil informasi sisa stok...")
    page.goto(f"{BASE_URL}/merchant/app/manage-product", timeout=20000)
    page.wait_for_timeout(random.randint(3500, 5000))
    close_location_popup(page, wait_time=0.3)
    close_generic_popup(page, wait_time=0.2)
    
    stok_text = None
    
    # Method 1: Cari elemen yang mengandung "Stok Tabung per" dan ambil teks di container yang sama
    try:
        stok_label = page.locator("text=/Stok Tabung per/i").first
        if stok_label.is_visible(timeout=3000):
            full_text = stok_label.evaluate("""
                (el) => {
                    let current = el;
                    for (let i = 0; i < 10; i++) {
                        if (!current) break;
                        const text = current.innerText || '';
                        if (text.match(/Stok Tabung per/i) && text.match(/\\d+\\s*Tabung/i)) {
                            return text;
                        }
                        current = current.parentElement;
                    }
                    return '';
                }
            """)
            
            if full_text:
                match = re.search(r'(\d+)\s*Tabung', full_text)
                if match:
                    stok_text = f"{match.group(1)} Tabung"
    except Exception as e1:
        logging.debug(f"Method 1 gagal: {e1}")
    
    # Method 2: Gunakan JavaScript untuk mencari container yang mengandung "Stok Tabung per" dan "Tabung"
    if not stok_text:
        try:
            stok_text = page.evaluate("""
                () => {
                    const allElements = document.querySelectorAll('*');
                    for (let el of allElements) {
                        const text = el.innerText || '';
                        if (text.match(/Stok Tabung per/i) && text.match(/\\d+\\s*Tabung/i)) {
                            const match = text.match(/(\\d+)\\s*Tabung/i);
                            if (match) {
                                return match[1] + ' Tabung';
                            }
                        }
                    }
                    return null;
                }
            """)
        except Exception as e2:
            logging.debug(f"Method 2 gagal: {e2}")
    
    # Method 3: Cari sibling atau child
    if not stok_text:
        try:
            stok_text = page.evaluate("""
                () => {
                    const allElements = document.querySelectorAll('*');
                    for (let el of allElements) {
                        const text = el.innerText || '';
                        if (text.match(/Stok Tabung per/i)) {
                            let parent = el.parentElement;
                            for (let i = 0; i < 5; i++) {
                                if (!parent) break;
                                const parentText = parent.innerText || '';
                                const match = parentText.match(/(\\d+)\\s*Tabung/i);
                                if (match) {
                                    return match[1] + ' Tabung';
                                }
                                parent = parent.parentElement;
                            }
                            
                            let sibling = el.nextElementSibling;
                            for (let i = 0; i < 3; i++) {
                                if (!sibling) break;
                                const siblingText = sibling.innerText || '';
                                const match = siblingText.match(/(\\d+)\\s*Tabung/i);
                                if (match) {
                                    return match[1] + ' Tabung';
                                }
                                sibling = sibling.nextElementSibling;
                            }
                        }
                    }
                    return null;
                }
            """)
        except Exception as e3:
            logging.debug(f"Method 3 gagal: {e3}")
    
    if not stok_text:
        raise Exception("Teks stok tidak ditemukan di sebelah 'Stok Tabung per'")

    logging.info(f"Stok ditemukan: {stok_text}")
    return stok_text

def cek_stok(page, session):
    try:
        stok_text = ambil_sisa_stok(page)
        tg_send_menu(f"⚠️ SISA STOK SAAT INI\n[{session.nama_pangkalan or 'Pangkalan'}]\n❯ {stok_text}", chat_id=session.chat_id)
    except Exception as e:
        logging.error(f"[{session.chat_id}] Gagal cek stok: {e}")
        tg_send_menu(f"❌ Gagal cek stok: {e}", chat_id=session.chat_id)
    finally:
        from modules.pertamina import kembali_ke_beranda
        try:
            kembali_ke_beranda(page)
        except Exception as e:
            logging.warning(f"Gagal kembali ke beranda setelah cek stok: {e}")

async def cek_stok_satu_async(browser, account_name: str, cookie_path_str: str):
    """Cek stok untuk satu akun MURNI menggunakan file Cookie tersimpan (tanpa login manual)"""
    context = None
    page = None
    try:
        from pathlib import Path
        cookie_file = Path(cookie_path_str)
        if not cookie_file.exists():
            logging.warning(f"Akun [{account_name}]: ❌ File cookie {cookie_file.name} tidak ditemukan.")
            return None

        logging.info(f"Akun [{account_name}]: 🍪 Memuat stok via Cookie ({cookie_file.name})...")
        context = await browser.new_context(storage_state=str(cookie_file), ignore_https_errors=True)
        page = await context.new_page()
        await page.goto(f"{BASE_URL}/merchant/app", wait_until="domcontentloaded", timeout=25000)
        
        jeda_ms = random.randint(3500, 5000)
        logging.info(f"Akun [{account_name}]: ⏳ Jeda {jeda_ms/1000:.1f}s agar halaman beranda ter-render sempurna...")
        await page.wait_for_timeout(jeda_ms)
        
        # Cek apakah ter-redirect ke login (cookie expired)
        if "login" in page.url:
            logging.warning(f"Akun [{account_name}]: ⚠️ Cookie expired/invalid. Pengecekan stok dilewati.")
            await context.close()
            return None

        # Ambil stok
        stok = "0"
        for stok_attempt in range(5):
            try:
                stok_text_el = page.locator("text=/\\b\\d+\\s+Tabung\\b/i").first
                await stok_text_el.wait_for(state="visible", timeout=1000)
                stok_text = await stok_text_el.inner_text()
                m = re.search(r"(\d+)", stok_text)
                stok = m.group(1) if m else "0"
                if stok != "0":
                    break
            except Exception:
                pass
            if stok_attempt < 4:
                await page.wait_for_timeout(1000)
        
        logging.info(f"Akun [{account_name}]: {account_name} | Stok = {stok} Tabung")
        await context.close()
        return (account_name, f"{stok} Tabung")

    except Exception as e:
        logging.warning(f"Akun [{account_name}] gagal cek stok via cookie: {e}")
        if context:
            with contextlib.suppress(Exception): await context.close()
        return None

def angka_awal(s: str) -> int:
    m = re.search(r"(\d+)", s or "")
    return int(m.group(1)) if m else -1

def format_one_result(nama: str, stok: str) -> str:
    jumlah = angka_awal(stok)
    body = "✅Done" if jumlah == 0 else stok
    return f"{escape(nama)} | {escape(body)}"

async def process_batch_async(cookie_items: list, max_workers: int = 3):
    if not cookie_items:
        return [], []

    results = []
    failures = []
    sem = asyncio.Semaphore(max_workers)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=is_headless(), 
            slow_mo=0,
        )

        async def one_account(account_name: str, cookie_path_str: str):
            try:
                async with sem:
                    res = await asyncio.wait_for(
                        cek_stok_satu_async(browser, account_name, cookie_path_str),
                        timeout=120
                    )
                if res:
                    results.append(res)
                    return
            except Exception as e:
                logging.warning(f"Error cek stok cookie {account_name}: {e}")
            failures.append(account_name)

        tasks = [asyncio.create_task(one_account(acc_n, ck_p)) for (acc_n, ck_p) in cookie_items]
        await asyncio.gather(*tasks, return_exceptions=True)
        await browser.close()

    return results, failures

def send_stok_report(results: list, chat_id: str):
    if not results:
        tg_send_menu("Tidak ada hasil stok yang berhasil diambil dari cookie.", chat_id=chat_id, show_account_menu=True)
        return
    
    results.sort(key=lambda x: angka_awal(x[1]), reverse=True)
    lines = [f"{i}. {format_one_result(nm, sk)}" for i, (nm, sk) in enumerate(results, 1)]
    
    try:
        html_text = "<b>📊 Laporan Stok Tabung (Via Cookies)</b>\n\n" + "\n".join(lines)
        requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            data={"chat_id": chat_id, "text": html_text, "parse_mode": "HTML"},
            timeout=20
        )
    except Exception as e:
        logging.error(f"Gagal kirim laporan: {e}")
        tg_send_menu("❌ Gagal mengirim laporan stok.", chat_id=chat_id, show_account_menu=True)

def run_cek_stok_data(session):
    """Cek stok real-time seluruh akun tersimpan di accounts.json via Playwright login senyap"""
    accounts_list = session.get_accounts_list()
    if not accounts_list:
        tg_send_menu("📭 Belum ada akun tersimpan.", chat_id=session.chat_id, show_account_menu=True)
        return

    try:
        from modules.auto_transaction import scan_stok_semua_akun
        scan_stok_semua_akun(accounts_list, session)
    except Exception as e:
        logging.error(f"[{session.chat_id}] Error run_cek_stok_data: {e}")
        tg_send_menu(f"❌ Error saat cek stok data: {e}", chat_id=session.chat_id, show_account_menu=True)

async def generate_cookie_satu_async(browser, account_name: str, email: str, pin: str, session, idx: int = 1, total: int = 1):
    """Login 1 per 1 secara KALEM & HATI-HATI (mirip login manual), ambil nama pangkalan, simpan storage_state ke cookies/<NAMA_PANGKALAN>.json"""
    for attempt in range(1, 3):
        context = None
        page = None
        try:
            logging.info(f"[{session.chat_id}] 🪷 [{idx}/{total}] Mode Kalem: Membuka browser untuk {email}...")
            context = await browser.new_context(ignore_https_errors=True)
            page = await context.new_page()
            
            # 1. Buka Halaman Login
            await page.goto(f"{BASE_URL}/merchant-login", wait_until="domcontentloaded", timeout=30000)
            await page.wait_for_timeout(random.uniform(2000, 3500))
            
            # 2. Isi Email (Human-like)
            await page.get_by_role("textbox", name="Nomor Ponsel atau Email").fill(email)
            await page.wait_for_timeout(random.uniform(1500, 2500))
            
            # 3. Isi PIN (Human-like)
            await page.get_by_role("textbox", name="PIN").fill(pin)
            await page.wait_for_timeout(random.uniform(2000, 3000))
            
            # 4. Klik Tombol MASUK
            try:
                await page.get_by_role("button", name="MASUK").click(timeout=5000)
            except Exception:
                await page.wait_for_timeout(1500)
                await page.get_by_role("button", name="MASUK").click(timeout=5000)
                
            logging.info(f"[{session.chat_id}] [{idx}/{total}] Klik MASUK untuk {email}. Menunggu navigasi beranda...")
            
            # 5. Menunggu Navigasi ke Dashboard
            login_ok = False
            for _ in range(45):
                await page.wait_for_timeout(1000)
                if "/merchant/app" in page.url:
                    login_ok = True
                    break
            
            if not login_ok:
                raise Exception("Timeout login / tidak berhasil masuk beranda dashboard")
            
            # Jeda 3.5 - 5.0 detik setelah masuk dashboard agar data ter-load sempurna
            await page.wait_for_timeout(random.randint(3500, 5000))
                
            # 6. Ambil nama pangkalan resmi dari header
            nama_scraped = await page.evaluate("""
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
                            if (text && text.length >= 4 && text.length < 80) {
                                const words = text.split(/\\s+/);
                                if (words.length >= 1 && words.length <= 5 && words.every(w => /^[A-Z]/.test(w))) {
                                    if (rect.top < topMostTop) {
                                        topMostTop = rect.top;
                                        topMostName = text;
                                    }
                                }
                            }
                        }
                    }
                    return topMostName;
                }
            """)
            
            real_name = account_name
            if nama_scraped:
                real_name = nama_scraped.strip().split('\n')[0].strip()
                
            cookie_path = session.get_cookie_path(real_name)
            await page.context.storage_state(path=str(cookie_path))
            session.add_account(real_name, email, pin)
            
            logging.info(f"[{session.chat_id}] 🟢 [{idx}/{total}] Cookie BERHASIL disimpan ke {cookie_path.name} untuk [{real_name}]")
            await context.close()
            return True, real_name
        except Exception as e:
            logging.warning(f"[{session.chat_id}] ⚠️ [{idx}/{total}] Attempt {attempt} gagal ({email}): {e}")
            if context:
                with contextlib.suppress(Exception): await context.close()
            await asyncio.sleep(2)
            continue
    return False, account_name or email


async def process_generate_cookies_batch_async(session, account_items: list):
    """Memproses akun 1 per 1 secara sekuensial (Mode Kalem) agar stabil & aman"""
    if not account_items:
        return [], []

    successes = []
    failures = []
    total = len(account_items)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=is_headless(),
            slow_mo=0,
        )

        for i, (name, em, pn) in enumerate(account_items, 1):
            if getattr(session, 'stop_requested', False):
                logging.info(f"[{session.chat_id}] 🛑 Penarikan cookie dihentikan karena perintah STOP user.")
                tg_send_menu("🛑 Proses penarikan cookie massal dihentikan!", chat_id=session.chat_id, show_account_menu=True)
                break
            try:
                ok, res_name = await asyncio.wait_for(
                    generate_cookie_satu_async(browser, name, em, pn, session, idx=i, total=total),
                    timeout=180
                )
                if ok:
                    successes.append(res_name)
                    tg_send_menu(f"🟢 **[{i}/{total}] COOKIE SUKSES**\n🏪 {res_name}\n💾 Sesi disimpan ke file & tombol otomatis!", chat_id=session.chat_id, show_account_menu=True)
                else:
                    failures.append(res_name)
                    tg_send_menu(f"❌ **[{i}/{total}] COOKIE GAGAL**\n📧 {em}\n⚠️ Tidak berhasil login 1x.", chat_id=session.chat_id, show_account_menu=True)
            except Exception as e:
                logging.warning(f"Error generate cookie {name} ({em}): {e}")
                failures.append(name or em)
                tg_send_menu(f"❌ **[{i}/{total}] ERROR**\n📧 {em}: {e}", chat_id=session.chat_id, show_account_menu=True)
            
            # Jeda Mode Kalem 3 detik antar akun agar server tidak menganggap Spam/WAF
            if i < total:
                logging.info(f"[{session.chat_id}] 🪷 Mode Kalem: Jeda 3 detik sebelum akun berikutnya...")
                await asyncio.sleep(3)

        await browser.close()

    return successes, failures


def run_generate_cookies_batch(session, custom_accounts: list = None):
    """Menjalankan pembuat cookie massal secara KALEM (sekuensial 1 per 1)"""
    session.stop_requested = False
    if custom_accounts:
        account_items = custom_accounts
    else:
        raw_list = session.get_accounts_list()
        account_items = []
        for name, cred_str in raw_list:
            em, pn = parse_credential_line(cred_str)
            if em and pn:
                account_items.append((name, em, pn))
                
    if not account_items:
        tg_send_menu("📭 Belum ada akun valid untuk diambil cookienya.", chat_id=session.chat_id, show_account_menu=True)
        return
        
    tg_send_menu(
        f"☕ **MEMULAI AMBIL COOKIES MASSAL (MODE KALEM)**\n"
        f"━━━━━━━━━━━━━━━━━\n"
        f"📊 Total Akun: {len(account_items)} akun\n"
        f"🛡️ Metode: Sekuensial 1 per 1 dengan jeda manusiawi (Aman dari Server Down & Anti-Bot)\n\n"
        f"Sistem akan memproses satu per satu dan mengirimkan laporan real-time. Mohon tunggu...",
        chat_id=session.chat_id,
        show_account_menu=True
    )
    
    try:
        successes, failures = asyncio.run(process_generate_cookies_batch_async(session, account_items))
        
        lines = [
            "🎉 **AMBIL COOKIES MASSAL SELESAI!**",
            "━━━━━━━━━━━━━━━━━",
            f"✅ **Berhasil:** {len(successes)}/{len(account_items)} akun"
        ]
        
        if successes:
            lines.append("\n🍪 **Daftar Cookie Tersimpan di Tombol:**")
            for s_name in successes:
                lines.append(f"• 🍪 {s_name}")
                
        if failures:
            lines.append("\n⚠️ **Gagal Ambil Cookie:**")
            for f_name in failures:
                lines.append(f"• ❌ {f_name}")
                
        lines.append("\n✨ Seluruh akun yang berhasil kini siap dipakai via tombol **PROSES AKUN** (Bypassed Login)!")
        
        tg_send_menu("\n".join(lines), chat_id=session.chat_id, show_account_menu=True)
    except Exception as e:
        logging.error(f"[{session.chat_id}] Error run_generate_cookies_batch: {e}")
        tg_send_menu(f"❌ Error saat generate cookies massal: {e}", chat_id=session.chat_id, show_account_menu=True)
