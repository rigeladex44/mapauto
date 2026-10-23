# Mapauto Web

Workspace PWA untuk manajemen merchant, pengguna dan masa aktif, stok, job/worker, filter pelanggan, audit dan laporan. FastAPI + React/TypeScript/Tailwind, PostgreSQL produksi. Default tidak berisi data dummy; simulasi hanya dengan Demo Mode eksplisit.

- [Audit keamanan](AUDIT_REPORT.md)
- [Rencana migrasi](docs/MIGRATION_PLAN.md)
- [Rotasi credential & rencana history cleanup](docs/SECURITY_ROTATION.md)
- [Instalasi lokal dan deployment](docs/DEPLOYMENT.md)
- [Hasil pengujian dan batas fitur](docs/TEST_REPORT.md)
- [Arsitektur VPS](ARCHITECTURE.md)
- [Peta alur bot utama dan webapp](FLOW_MAP.md)
- [Deployment VPS Ubuntu](DEPLOYMENT_VPS.md)
- [Checklist keamanan](SECURITY_CHECKLIST.md)

**Belum production-ready.** Stack VPS memakai Caddy, FastAPI, PostgreSQL, Redis, dan container worker Chromium dengan antrean tenant/merchant terisolasi. Batch, preview, pause/resume/cancel, verifikasi manual, rekonsiliasi dan browser flow tersedia hanya untuk merchant mock dalam Demo Mode. Tidak ada integrasi transaksi merchant live. Tidak mengimpor credential/cookie/NIK legacy, tidak melewati CAPTCHA/OTP, dan tidak menjalankan bot Telegram. Launcher bot legacy dihentikan; modul legacy hanya untuk referensi audit. Panduan lama DOKUMENTASI_LENGKAP.md adalah arsip perilaku bot, bukan panduan deployment web.

Alur layar yang difokuskan sekarang: login Web App → cek stok otomatis dalam Demo Mode untuk merchant aktif pertama → dashboard stok dan tombol **Catat Penjualan** → input banyak NIK sintetis, preview, konfirmasi → progres job dalam panel empat baris yang diperbarui berkala. Login ini masih autentikasi akun Web App; PIN merchant asli, stok live, dan proses NIK live melalui Playwright belum terhubung. Jangan masukkan PIN atau NIK asli saat menguji Demo Mode.

Untuk menjalankan demo lokal seperti launcher bot: pasang Docker Desktop dan Python 3, lalu buka `run_webapp.command` di macOS atau `run_webapp.bat` di Windows. Pertama kali, terminal meminta pembuatan akun admin; kemudian browser membuka `http://127.0.0.1:18080`. Launcher membuat `.env.local-demo` yang diabaikan Git, menjalankan Compose pada loopback, dan tidak memakai `.env` production. Jalankan lagi launcher yang sama untuk membuka aplikasi berikutnya. Untuk berhenti: `docker compose --env-file .env.local-demo -f docker-compose.yml -f deploy/compose.demo.yml -f deploy/compose.smoke.yml --profile demo down` dari folder repo. Jangan gunakan `down -v` kecuali memang ingin menghapus database demo.

Quick start ada di panduan deployment. Buat admin lewat CLI tanpa password default, jalankan migrasi, build frontend, lalu API dan worker. Jangan jalankan scripts/cleanup lama pada lingkungan yang perlu menjaga bukti audit.
