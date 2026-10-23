import re
import time
import logging
import os
from pathlib import Path

def clear_terminal():
    """Clear terminal console screen"""
    os.system('cls' if os.name == 'nt' else 'clear')

def clear_terminal_and_logs():
    """Clear terminal console screen dan hapus temporary log/image files"""
    clear_terminal()
    try:
        # Hapus temporary image files jika ada
        for img in ["temp_bg.jpg", "temp_piece.png", "piece_detection.png"]:
            p = Path(img)
            if p.exists():
                try: p.unlink()
                except Exception: pass
        # Hapus file *.log di root
        for log_file in Path(".").glob("*.log"):
            try: log_file.unlink()
            except Exception: pass
    except Exception:
        pass
    logging.info("🧹 Terminal VPS & log berhasil dibersihkan.")

def normalize_button_text(s: str) -> str:
    """Hilangkan emoji dari text tombol untuk normalisasi"""
    s_clean = re.sub(r'[^\w\s]', '', s or '')
    return s_clean.strip().upper()

def normalize_cmd(s: str) -> str:
    s_strip = (s or "").strip()
    if s_strip.startswith("/"): return s_strip
    alias = {"login": "/login", "stop": "/stop", "cek": "/cek", "cek stok": "/cek", "del": "/del", "status": "/status"}
    return alias.get(s_strip.lower(), s_strip)

def parse_credential_line(s: str):
    parts = s.split("|", 1)
    if len(parts) != 2: return None, None
    email, pin = parts[0].strip(), parts[1].strip()
    return (email, pin) if (email and pin) else (None, None)

def close_location_popup(page, wait_time=0.5):
    """Tutup popup izin lokasi jika muncul (browser permission dialog)."""
    try:
        if wait_time > 0:
            time.sleep(wait_time)
        for i in range(3):
            try:
                page.keyboard.press("Escape")
                time.sleep(0.15)
            except:
                pass
        close_selectors = [
            "button[aria-label*='close' i]", "button[aria-label*='tutup' i]",
            "[role='button'][aria-label*='close' i]", "button:has-text('×')",
            "button:has-text('✕')", "[data-dismiss]", ".close", "[class*='close']"
        ]
        for selector in close_selectors:
            try:
                close_btn = page.locator(selector).first
                if close_btn.is_visible(timeout=500):
                    close_btn.click()
                    logging.debug("   ✅ Tutup popup lokasi")
                    time.sleep(0.2)
                    break
            except:
                continue
        try:
            page.mouse.click(10, 10)
            time.sleep(0.15)
        except:
            pass
        try:
            page.keyboard.press("Escape")
            time.sleep(0.15)
        except:
            pass
    except:
        pass

def close_generic_popup(page, wait_time=0.3):
    """Tutup popup HTML generik (iklan, info, modal, dll). JANGAN tutup captcha!"""
    try:
        if wait_time > 0:
            time.sleep(wait_time)
        try:
            captcha_visible = page.locator(".rc-slider-captcha").first.is_visible(timeout=300)
            if captcha_visible:
                logging.debug("   ℹ️ Captcha terdeteksi, skip tutup popup")
                return
        except:
            pass
        try:
            page.evaluate("""
                () => {
                    const isCaptcha = (element) => {
                        return element.closest('.rc-slider-captcha') !== null ||
                                element.querySelector('.rc-slider-captcha') !== null ||
                                element.classList.contains('rc-slider-captcha');
                    };
                    const modals = document.querySelectorAll('.modal.show, .modal[style*="display"]');
                    modals.forEach(modal => {
                        if (isCaptcha(modal)) return;
                        const closeBtn = modal.querySelector('[data-dismiss="modal"], [data-bs-dismiss="modal"], .close, button.close');
                        if (closeBtn && !isCaptcha(closeBtn)) {
                            closeBtn.click();
                        } else {
                            const event = new Event('hidden.bs.modal', { bubbles: true });
                            modal.dispatchEvent(event);
                        }
                    });
                    const popups = document.querySelectorAll('.popup, .popup-overlay, [class*="popup"], [class*="modal"]');
                    popups.forEach(popup => {
                        if (isCaptcha(popup)) return;
                        const style = window.getComputedStyle(popup);
                        if (style.display !== 'none' && style.visibility !== 'hidden' && style.zIndex > 100) {
                            const closeBtn = popup.querySelector('button.close, .close-button, [aria-label*="close" i], button:has-text("×"), button:has-text("✕")');
                            if (closeBtn && !isCaptcha(closeBtn)) {
                                closeBtn.click();
                            }
                        }
                    });
                    const allButtons = document.querySelectorAll('button, [role="button"]');
                    for (let btn of allButtons) {
                        if (isCaptcha(btn)) continue;
                        const style = window.getComputedStyle(btn);
                        const parent = btn.closest('.modal, .popup, [class*="modal"], [class*="popup"]');
                        if (parent && !isCaptcha(parent)) {
                            const parentStyle = window.getComputedStyle(parent);
                            if (parentStyle.display !== 'none' && parentStyle.visibility !== 'hidden') {
                                const btnText = btn.textContent || btn.getAttribute('aria-label') || '';
                                if (btnText.toLowerCase().includes('close') || btnText.includes('×') || btnText.includes('✕') ||
                                    btn.classList.contains('close') || btn.getAttribute('data-dismiss')) {
                                    btn.click();
                                }
                            }
                        }
                    }
                }
            """)
            time.sleep(0.2)
        except:
            pass
        close_selectors = [
            "[data-dismiss='modal']", "[data-bs-dismiss='modal']", ".modal.show button.close",
            ".modal.show .close", ".popup .close", "button.close", ".close-button",
            "button[aria-label*='close' i]", "button[aria-label*='tutup' i]",
            "button:has-text('×')", "button:has-text('✕')", "[class*='close'][class*='button']"
        ]
        for selector in close_selectors:
            try:
                elements = page.locator(selector).all()
                for element in elements[:5]:
                    try:
                        if element.is_visible(timeout=300):
                            is_in_captcha = element.evaluate("(el) => el.closest('.rc-slider-captcha') !== null")
                            if is_in_captcha:
                                continue
                            element.click()
                            logging.debug("   ✅ Tutup popup HTML")
                            time.sleep(0.15)
                            break
                    except:
                        continue
            except:
                continue
        for i in range(2):
            try:
                page.keyboard.press("Escape")
                time.sleep(0.15)
            except:
                pass
        try:
            backdrop = page.locator(".modal-backdrop, .overlay, [class*='backdrop']").first
            if backdrop.is_visible(timeout=300):
                box = backdrop.bounding_box()
                if box:
                    page.mouse.click(box['x'] + box['width']/2, box['y'] + box['height']/2)
                    time.sleep(0.15)
        except:
            pass
    except:
        pass
