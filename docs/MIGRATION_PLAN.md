# Rencana migrasi berdasarkan audit

1. Karantina data legacy dari index tanpa menghapus file lokal; panduan rotasi dan rewrite history terpisah, tanpa force push.
2. FastAPI + SQLAlchemy + Alembic, PostgreSQL produksi, SQLite untuk pengembangan/test. Session cookie opaque, hash password scrypt, CSRF, RBAC admin/operator/viewer, expiry, login throttling dan audit tanpa payload rahasia.
3. Pisahkan domain expiry/filter/stok dari Telegram. Target live adalah alur UI Playwright dengan akun merchant berizin, menggunakan tahap login/NIK/hasil pada `modules/pertamina.py` dan stok pada `modules/stock.py` setelah validasi ulang. Checkpoint verifikasi manual ditangani worker web; `semiauto/` tidak digunakan. Merchant saat ini hanya metadata otorisasi, bukan PIN/cookie. Adapter live fail-closed; simulasi eksplisit dan tidak pernah menghubungi merchant.
4. Queue database durable, proses worker terpisah, klaim job atomik, heartbeat, cancellation dan riwayat. Demo hanya saat DEMO_MODE=true; transaksi simulasi dilabeli di DB dan UI.
5. React/TypeScript/Tailwind: dashboard stok/activity, merchant, pengguna, expiry, transaksi, filter, worker, laporan CSV dan sistem. Polling real-time, tanpa fake control, empty/error/loading states. PWA shell tanpa cache API/akun.
6. Docker/Compose PostgreSQL, migrasi, bootstrap admin CLI tanpa password default, CI API/frontend/build dan smoke UI. Uji batas keamanan dan simulasi; live merchant/notifikasi tidak dikirim saat test.
7. Commit per tahap; tidak push, rewrite history atau mengubah transaksi produksi. Hasil akhir mencantumkan tes yang dijalankan dan batas deployment/integrasi/manual approval.
