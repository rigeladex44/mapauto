# Hasil validasi migrasi

23 Oktober 2026. Seluruh fixture menggunakan data sintetis dan database test terisolasi; tidak memakai akun merchant, NIK, token, cookie atau session legacy.

## Berhasil

- API pada PostgreSQL: **17 test passed**, termasuk autentikasi, hash/session, CSRF dan login cross-site, role viewer/operator/admin, expiry, account lockout, pencabutan sesi/password, validasi tanpa echo secret, authorized merchant/filter, konflik duplikat, antrean, cancellation, pause/resume, failed transaction, pemeriksaan hak pembuat job, ekspor CSV dan settings.
- SQLite: **16 passed, 1 skipped**. Satu skip adalah pengujian konkurensi row lock khusus PostgreSQL, yang dijalankan dan lulus pada PostgreSQL.
- Dua worker PostgreSQL memproses transaksi simulasi pada merchant sama tanpa lost update stok. Tidak ada transaksi nyata.
- Migrasi Alembic PostgreSQL upgrade → schema check (no diff) → downgrade → upgrade berhasil pada database sementara. Migrasi SQLite juga dipakai dalam smoke browser dan instance lokal.
- Frontend unit test **1 passed**; typecheck dan build Vite berhasil. Instalasi ulang `npm ci` serta instalasi Python `--require-hashes` berhasil.
- Browser Chromium desktop dan mobile: login, merchant create/edit, filter, stok simulasi, transaksi simulasi, worker pause/resume, queued job cancel, user create/extend, CSV download, settings, role viewer read-only, logout/password change, modal dan layout mobile. Tidak ada error runtime JavaScript pada alur yang diuji. Ini bukan pengujian setiap kombinasi browser/input.
- PWA manifest dan icon, service worker registration, dan tidak adanya /api dalam Cache Storage diverifikasi. API memakai Cache-Control no-store. Data sintetis berlabel Demo Mode.
- Image Docker multi-stage berhasil dibangun dengan verifikasi TLS dan trust proxy. Startup awal gagal karena permission file root-copy; diperbaiki dengan ownership untuk UID 10001. Uji ulang API non-root/read-only, PostgreSQL migration, static PWA, penolakan akses tanpa session, API docs disabled dan heartbeat worker berhasil. Compose config lolos validasi. Full stack Compose dengan domain/TLS produksi belum dideploy.
- `npm audit`: **0 advisory** pada dependency web saat pemeriksaan. `pip-audit --disable-pip -r backend/requirements.lock`: **no known vulnerabilities**. Ini hanya dependency baru, bukan sertifikasi keamanan semua kode/binary atau requirements legacy.

## Belum diverifikasi / perlu tindakan

- Credential lama harus dirotasi; history lama, fork/Pages/cache dan salinan luar masih dapat memuat data sensitif. Scanner pola bukan audit forensik lengkap. Tidak ada rewrite/force push dilakukan.
- Tidak tersedia adapter merchant resmi atau izin API: semua permintaan live ditolak. Stok/transaksi asli, account credential vault, OTP/CAPTCHA dan limit production tidak dimigrasikan atau diuji.
- Telegram hanya diuji dengan transport mock; tidak ada pesan nyata dikirim. Pengiriman nyata perlu secret baru, opt-in environment dan admin, serta pengujian terotorisasi.
- Instalasi iPhone/Android fisik, Safari iOS, audit aksesibilitas menyeluruh, load/penetration test, disaster recovery, HTTPS/reverse proxy, secret manager dan rate limiting IP belum diuji.
- CI workflow disiapkan; eksekusi pada GitHub Actions belum terjadi karena tidak ada push.
- Ada satu deprecation warning upstream Starlette TestClient terkait httpx; test tetap dieksekusi dan lulus.

**Kesimpulan:** aplikasi lokal dan jalur simulasi teruji; bukan klaim production-ready. Panduan deployment mencantumkan batas scope, single organization, retensi/pagination dan prasyarat operasi nyata.
