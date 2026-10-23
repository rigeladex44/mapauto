"""Isolated UI smoke. Requires Playwright + a local Chromium. No production data."""
import os, subprocess, tempfile, secrets, time, urllib.request, json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from cryptography.fernet import Fernet
root=Path(__file__).resolve().parents[1]
python=os.environ.get('BACKEND_PYTHON',str(root/'.venv/bin/python'))
password=secrets.token_urlsafe(20)
viewer_password=secrets.token_urlsafe(20)
with tempfile.TemporaryDirectory(prefix='mapauto-e2e-') as temp:
    env={**os.environ,'DATABASE_URL':'sqlite:///'+temp+'/test.db','DEMO_MODE':'true','APP_ENV':'development','TELEGRAM_ENABLED':'false','COOKIE_SECURE':'false','E2E_PASSWORD':password,'ALLOWED_HOSTS':'localhost,127.0.0.1,testserver','DATA_ENCRYPTION_KEY':Fernet.generate_key().decode(),'NIK_HASH_KEY':secrets.token_hex(32)}
    subprocess.run([python,'-m','alembic','-c','backend/alembic.ini','upgrade','head'],cwd=root,env=env,check=True)
    subprocess.run([python,'-c',"import os; from backend.app.db import SessionLocal; from backend.app.models import User; from backend.app.security import hash_password; db=SessionLocal(); db.add(User(username='e2e-admin',password_hash=hash_password(os.environ['E2E_PASSWORD']),role='admin')); db.commit()"],cwd=root,env=env,check=True)
    server=subprocess.Popen([python,'-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port','8011','--no-access-log'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    worker=subprocess.Popen([python,'-m','backend.app.worker'],cwd=root,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        for _ in range(60):
            try:
                urllib.request.urlopen('http://127.0.0.1:8011/api/health');break
            except Exception:time.sleep(.2)
        else:raise RuntimeError('E2E server did not start')
        with sync_playwright() as p:
            browser=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH','/usr/bin/chromium'),headless=True)
            context=browser.new_context(viewport={'width':1440,'height':1000})
            page=context.new_page();errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto('http://127.0.0.1:8011')
            page.get_by_label('Username',exact=True).fill('e2e-admin');page.get_by_label('Password',exact=True).fill(password)
            page.get_by_role('button',name='Masuk ke workspace').click()
            expect(page.get_by_role('heading',name='Semua dalam kendali.')).to_be_visible()
            page.get_by_role('navigation').get_by_role('button',name='Merchant',exact=True).click()
            page.get_by_role('button',name='Tambah merchant').click()
            dialog=page.get_by_role('dialog');dialog.get_by_label('Nama merchant').fill('Synthetic E2E Merchant');dialog.get_by_label('Referensi internal').fill('e2e-001')
            dialog.get_by_label('Saya memiliki otorisasi').check();dialog.get_by_role('button',name='Simpan',exact=True).click()
            expect(page.get_by_text('Synthetic E2E Merchant',exact=True)).to_be_visible()
            page.get_by_role('button',name='Edit & filter').click();dialog.get_by_label('USAHA MIKRO',exact=True).uncheck();dialog.get_by_role('button',name='Simpan',exact=True).click()
            page.get_by_role('navigation').get_by_role('button',name='Stok',exact=True).click()
            page.get_by_role('button',name='Cek stok simulasi').click();page.get_by_role('dialog').get_by_role('button',name='Simpan',exact=True).click()
            expect(page.get_by_text('100 tabung',exact=True)).to_be_visible(timeout=15000)
            page.get_by_role('navigation').get_by_role('button',name='Transaksi',exact=True).click()
            page.get_by_role('button',name='Simulasi transaksi').click();dialog.get_by_label('Jumlah tabung').fill('2');dialog.get_by_role('button',name='Simpan',exact=True).click()
            expect(page.get_by_text('SIMULASI: pencatatan lokal; bukan transaksi merchant',exact=True)).to_be_visible(timeout=15000)
            page.get_by_role('navigation').get_by_role('button',name='Batch NIK',exact=True).click()
            page.get_by_label('NIK sintetis, satu per baris').fill('0000000000000001\n0000000000000001')
            page.get_by_label('Saya memakai data sintetis untuk simulasi.').check()
            page.get_by_role('button',name='Validasi & preview').click()
            expect(page.get_by_text('1 NIK unik')).to_be_visible()
            page.get_by_role('button',name='Konfirmasi antrean').click()
            page.get_by_role('button',name='Batalkan batch').click()
            page.get_by_role('navigation').get_by_role('button',name='Verifikasi',exact=True).click()
            expect(page.get_by_text('Tidak ada verifikasi yang menunggu. Checkpoint baru akan muncul otomatis.')).to_be_visible()
            page.get_by_role('navigation').get_by_role('button',name='Worker',exact=True).click()
            page.get_by_role('button',name='Jeda',exact=True).click();expect(page.get_by_role('button',name='Lanjutkan',exact=True)).to_be_visible()
            # Queued work stays cancellable while the worker is paused.
            page.get_by_role('navigation').get_by_role('button',name='Transaksi',exact=True).click()
            page.get_by_role('button',name='Simulasi transaksi').click();dialog.get_by_role('button',name='Simpan',exact=True).click()
            page.get_by_role('button',name='Batalkan',exact=True).click();expect(page.get_by_text('Dibatalkan',exact=True)).to_be_visible()
            page.get_by_role('navigation').get_by_role('button',name='Worker',exact=True).click();page.get_by_role('button',name='Lanjutkan',exact=True).click()
            page.get_by_role('navigation').get_by_role('button',name='Pengguna',exact=True).click()
            page.get_by_role('button',name='Tambah pengguna').click();dialog.get_by_label('Username',exact=True).fill('synthetic-viewer');dialog.get_by_label('Password awal').fill(viewer_password);dialog.get_by_role('button',name='Simpan',exact=True).click()
            expect(page.get_by_text('synthetic-viewer',exact=True)).to_be_visible()
            page.get_by_role('row').filter(has_text='synthetic-viewer').get_by_role('button',name='Kelola akses').click();dialog.get_by_label('Tambahkan masa aktif').fill('5');dialog.get_by_role('button',name='Simpan',exact=True).click()
            page.get_by_role('navigation').get_by_role('button',name='Laporan',exact=True).click()
            with page.expect_download() as download:page.get_by_role('link',name='Unduh laporan CSV').click()
            assert download.value.suggested_filename=='mapauto-jobs.csv'
            page.get_by_role('navigation').get_by_role('button',name='Pengaturan',exact=True).click();page.get_by_role('button',name='Simpan pengaturan').click()
            expect(page.get_by_role('status')).to_contain_text('Perubahan disimpan')
            # PWA registration and privacy boundary: authenticated API never enters Cache Storage.
            page.wait_for_function("navigator.serviceWorker.controller !== null")
            paths=page.evaluate("async()=>{const all=[];for(const k of await caches.keys()){for(const r of await (await caches.open(k)).keys()) all.push(new URL(r.url).pathname);}return all;}")
            assert not any(path.startswith('/api') for path in paths)
            page.get_by_role('navigation').get_by_role('button',name='Dashboard',exact=True).click();page.screenshot(path='/tmp/mapauto-desktop.png',full_page=True)
            page.set_viewport_size({'width':390,'height':844});page.reload();expect(page.get_by_role('heading',name='Semua dalam kendali.')).to_be_visible()
            assert page.evaluate('document.documentElement.scrollWidth <= window.innerWidth')
            page.get_by_role('button',name='Buka navigasi').click();page.get_by_role('navigation').get_by_role('button',name='Merchant',exact=True).click()
            page.wait_for_timeout(300);page.screenshot(path='/tmp/mapauto-mobile.png',full_page=True)
            # Mobile create form must fit, Escape closes it and returns focus.
            page.get_by_role('button',name='Tambah merchant').click();expect(dialog).to_be_visible();page.keyboard.press('Escape');expect(dialog).not_to_be_visible()
            page.get_by_role('button',name='Buka navigasi').click();page.get_by_role('button',name='Keluar dari workspace').click()
            page.get_by_label('Username',exact=True).fill('synthetic-viewer');page.get_by_label('Password',exact=True).fill(viewer_password);page.get_by_role('button',name='Masuk ke workspace').click()
            expect(page.get_by_role('heading',name='Semua dalam kendali.')).to_be_visible()
            page.get_by_role('button',name='Buka navigasi').click()
            expect(page.get_by_role('navigation').get_by_role('button',name='Pengguna',exact=True)).to_have_count(0)
            page.get_by_role('navigation').get_by_role('button',name='Merchant',exact=True).click()
            expect(page.get_by_role('button',name='Tambah merchant')).to_have_count(0)
            page.get_by_role('button',name='Buka navigasi').click();page.get_by_role('button',name='Ubah password',exact=True).click()
            dialog.get_by_label('Password saat ini',exact=True).fill(viewer_password);dialog.get_by_label('Password baru',exact=True).fill(secrets.token_urlsafe(20));dialog.get_by_role('button',name='Simpan',exact=True).click()
            expect(page.get_by_role('button',name='Masuk ke workspace')).to_be_visible()
            assert not errors, f'Browser runtime errors: {len(errors)}'
            browser.close()
        print('PASS browser: login, merchant/filter, stock, transaction, batch preview/confirm/cancel, worker pause/resume, user/expiry, CSV, settings, PWA privacy, mobile layout and modal; zero runtime errors')
    finally:
        for process in [worker,server]:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()
