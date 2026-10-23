# Mapauto Web

Workspace PWA untuk manajemen merchant, pengguna dan masa aktif, stok, job/worker, filter pelanggan, audit dan laporan. FastAPI + React/TypeScript/Tailwind, PostgreSQL produksi. Default tidak berisi data dummy; simulasi hanya dengan Demo Mode eksplisit.

- [Audit keamanan](AUDIT_REPORT.md)
- [Rencana migrasi](docs/MIGRATION_PLAN.md)
- [Rotasi credential & rencana history cleanup](docs/SECURITY_ROTATION.md)
- [Instalasi lokal dan deployment](docs/DEPLOYMENT.md)
- [Hasil pengujian dan batas fitur](docs/TEST_REPORT.md)

**Belum production-ready.** Tidak ada integrasi transaksi merchant live. Tidak mengimpor credential/cookie/NIK legacy, tidak melewati CAPTCHA/OTP, dan tidak menjalankan bot Telegram. Launcher bot legacy dihentikan; modul legacy hanya untuk referensi audit. Panduan lama DOKUMENTASI_LENGKAP.md adalah arsip perilaku bot, bukan panduan deployment web.

Quick start ada di panduan deployment. Buat admin lewat CLI tanpa password default, jalankan migrasi, build frontend, lalu API dan worker. Jangan jalankan scripts/cleanup lama pada lingkungan yang perlu menjaga bukti audit.
