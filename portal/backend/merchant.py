"""Async adapter using routes/labels from mapauto, isolated from Telegram.
No checkout, payment submission or CAPTCHA solver is imported or called.
"""
import asyncio
import os
import re
import time
from .policy import LABELS, candidates, normalize_type, parse_stock

BASE = 'https://subsiditepatlpg.mypertamina.id'

class MerchantError(Exception):
    pass

class HumanRequired(MerchantError):
    pass

class Merchant:
    def __init__(self):
        self.pw = self.browser = self.context = self.page = None
        self.heading = os.getenv('MAP_HEADLESS', 'true').lower() != 'false'

    async def open(self):
        from playwright.async_api import async_playwright
        self.pw = await async_playwright().start()
        self.browser = await self.pw.chromium.launch(headless=self.heading)
        self.context = await self.browser.new_context(viewport={'width': 1100, 'height': 850})
        self.page = await self.context.new_page()
        self.page.set_default_timeout(10000)

    async def close(self):
        try:
            if self.context:
                await self.context.close()
            if self.browser:
                await self.browser.close()
        finally:
            if self.pw:
                await self.pw.stop()

    async def one(self, locator):
        await locator.first.wait_for(state='visible')
        visible = [item for item in await locator.all() if await item.is_visible()]
        if len(visible) != 1:
            raise MerchantError('Kontrol halaman tidak unik atau belum tersedia; periksa tampilan merchant.')
        return visible[0]

    async def text(self):
        return await self.page.locator('body').inner_text()

    async def human_check(self):
        for selector in ['.rc-slider-captcha', 'iframe[src*="recaptcha"]', 'iframe[src*="hcaptcha"]']:
            for item in await self.page.locator(selector).all():
                if await item.is_visible():
                    raise HumanRequired('Verifikasi manusia diperlukan. Selesaikan di browser pengujian, lalu tekan Periksa sesi.')

    async def login(self, identity, pin):
        await self.open()
        await self.page.goto(BASE + '/merchant-login', wait_until='domcontentloaded')
        await (await self.one(self.page.get_by_role('textbox', name=re.compile('nomor ponsel atau email', re.I)))).fill(identity)
        await (await self.one(self.page.get_by_role('textbox', name=re.compile('^PIN', re.I)))).fill(pin)
        await (await self.one(self.page.get_by_role('button', name=re.compile('^masuk$', re.I)))).click()
        # Never log or persist identity/PIN; a challenge is handed back to the operator.
        await self.wait_login()

    async def wait_login(self):
        end = time.monotonic() + 25
        while time.monotonic() < end:
            await self.human_check()
            if '/merchant/app' in self.page.url:
                return
            text = (await self.text()).lower()
            if any(t in text for t in ['email atau pin salah', 'akun tidak valid', 'login gagal']):
                raise MerchantError('Login ditolak merchant. Periksa email/ponsel dan PIN.')
            await asyncio.sleep(.3)
        raise HumanRequired('Login belum terkonfirmasi. Periksa browser pengujian lalu Periksa sesi.')

    async def dashboard(self):
        await self.page.goto(BASE + '/merchant/app', wait_until='domcontentloaded')
        await self.page.get_by_text('Catat Penjualan', exact=True).first.wait_for(state='visible')
        # Only visible leaf text in the account corner. No fallback to email or guessed stock.
        names = await self.page.evaluate('''() => Array.from(document.querySelectorAll('body *')).filter(e=>e.children.length===0).filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.left>innerWidth*.50&&r.top<260}).map(e=>(e.innerText||'').trim()).filter(t=>t.length>2&&t.length<100)''')
        name = names[0] if names else None
        subname = names[1] if len(names) > 1 else None
        return {'name': name, 'subname': subname}

    async def stock(self):
        await self.page.goto(BASE + '/merchant/app/manage-product', wait_until='domcontentloaded')
        label = await self.one(self.page.get_by_text(re.compile('Stok Tabung per', re.I)))
        text = await label.evaluate('''el=>{let p=el;for(let i=0;i<7&&p;i++,p=p.parentElement){let t=p.innerText||'';if(/Stok Tabung per/i.test(t)&&/\\d+\\s*Tabung/i.test(t))return t}return ''}''')
        return parse_stock(text)

    async def wait_nik_state(self, allow_choice=True):
        end = time.monotonic() + 15
        while time.monotonic() < end:
            await self.human_check()
            if 'merchant-login' in self.page.url:
                raise MerchantError('Sesi merchant berakhir. Login ulang diperlukan.')
            text = (await self.text()).lower()
            if any(t in text for t in ['melebihi batas kewajaran', 'tidak dapat transaksi', 'batas kewajaran']):
                return 'limit'
            if any(t in text for t in ['tidak ditemukan', 'tidak terdaftar']):
                return 'missing'
            if '/merchant/app/sale' in self.page.url and 'informasi pelanggan' in text:
                return 'sale'
            if allow_choice and 'jenis pelanggan di bawah ini' in text:
                return 'choice'
            await asyncio.sleep(.25)
        raise MerchantError('Tampilan setelah pemeriksaan NIK belum dikenali. Tidak dilanjutkan otomatis.')

    async def lookup(self, nik):
        await self.page.goto(BASE + '/merchant/app/verification-nik', wait_until='domcontentloaded')
        field = self.page.get_by_role('combobox', name=re.compile('Masukkan 16 digit NIK', re.I))
        if not await field.count():
            field = self.page.get_by_placeholder(re.compile('Masukkan 16 digit NIK', re.I))
        await (await self.one(field)).fill(nik)
        button = self.page.get_by_test_id('btnCheckNik')
        if not await button.count():
            button = self.page.get_by_role('button', name=re.compile('^LANJUTKAN PENJUALAN$', re.I))
        await (await self.one(button)).click()
        return await self.wait_nik_state()

    async def sale_type(self):
        heading = await self.one(self.page.get_by_text('Informasi Pelanggan', exact=True))
        card = await heading.evaluate('''el=>{let p=el;for(let i=0;i<6&&p;i++,p=p.parentElement){const t=p.innerText||'';if(/Informasi Pelanggan/i.test(t)&&/Ganti Pelanggan/i.test(t))return t}return ''}''')
        found = [t for t in card.splitlines() if normalize_type(t)]
        if len(found) != 1:
            raise MerchantError('Jenis pada kartu Informasi Pelanggan tidak terbaca secara pasti.')
        return normalize_type(found[0])

    async def prepare(self, nik, mode, emit):
        await emit('Memeriksa NIK dan jenis pelanggan')
        state = await self.lookup(nik)
        if state == 'missing':
            return {'status': 'Dilewati', 'type': '—', 'reason': 'NIK tidak ditemukan/terdaftar.'}
        if state == 'limit':
            return {'status': 'Limit', 'type': '—', 'reason': 'Merchant menampilkan batas transaksi sebelum jenis dapat dipilih.'}
        if state == 'sale':
            actual = await self.sale_type()
            if actual not in candidates(mode, [actual]):
                return {'status': 'Dilewati', 'type': actual, 'reason': 'Jenis pelanggan tidak sesuai filter.'}
            return {'status': 'Siap ditinjau', 'type': actual, 'reason': 'Jenis terverifikasi pada halaman penjualan. Belum ada transaksi.'}
        available = []
        for kind, label in LABELS.items():
            matches = [e for e in await self.page.get_by_text(label, exact=True).all() if await e.is_visible()]
            if len(matches) == 1:
                available.append(kind)
        order = candidates(mode, available)
        if not order:
            return {'status': 'Dilewati', 'type': '—', 'reason': 'Tidak ada pilihan RT/UM yang sesuai; jenis lain dilewati.'}
        limited = []
        for pos, kind in enumerate(order):
            if pos:
                # Only revisit after a verified pre-sale limit; no payment was submitted.
                await emit('UM limit; membuka ulang pilihan untuk RT')
                if await self.lookup(nik) != 'choice':
                    raise MerchantError('Tidak berhasil membuka ulang pilihan pelanggan. Berhenti untuk ditinjau.')
            await emit('Memilih ' + kind)
            await (await self.one(self.page.get_by_text(LABELS[kind], exact=True))).click()
            # Limit may appear immediately after choosing, before Continue.
            await asyncio.sleep(.4)
            current_text = (await self.text()).lower()
            if any(t in current_text for t in ['melebihi batas kewajaran', 'tidak dapat transaksi']):
                limited.append(kind)
                continue
            button = self.page.get_by_role('button', name=re.compile('^LANJUTKAN (PENJUALAN|TRANSAKSI)$', re.I))
            await (await self.one(button)).click()
            state = await self.wait_nik_state(allow_choice=False)
            if state == 'limit':
                limited.append(kind)
                continue
            if state != 'sale':
                raise MerchantError('Halaman penjualan belum terkonfirmasi; tidak ada transaksi dikirim.')
            actual = await self.sale_type()
            if actual != kind:
                raise MerchantError('Jenis aktif berbeda dari pilihan. Proses dihentikan untuk pemeriksaan.')
            return {'status': 'Siap ditinjau', 'type': actual, 'reason': ('UM limit → RT terpilih. ' if limited else '') + 'Jenis terverifikasi. Belum checkout atau transaksi.'}
        return {'status': 'Limit', 'type': limited[-1] if limited else '—', 'reason': 'Seluruh jenis yang diizinkan mencapai limit.'}
