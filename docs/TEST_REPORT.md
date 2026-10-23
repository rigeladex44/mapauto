# Hasil validasi migrasi

23 Oktober 2026. Seluruh fixture menggunakan data sintetis dan database test terisolasi; tidak memakai akun merchant, NIK, token, cookie atau session legacy. Bagian baseline di bawah berasal dari branch web awal; tambahan VPS dicatat terpisah.

## Tambahan VPS / multi-tenant

- PostgreSQL + Redis + Chromium mock: **27 passed**; termasuk akses lintas tenant, grant merchant operator, deduplikasi/enkripsi NIK sintetis, idempotensi, pause/resume/cancel, checkpoint verifikasi manual, worker restart, pengiriman tidak diketahui dan rekonsiliasi tanpa replay. Tidak ada transaksi nyata.
- Frontend unit test **1 passed**, TypeScript dan build Vite lulus sesudah penambahan layar batch/verifikasi.
- Build image backend, frontend, proxy dan worker Chromium dengan lockfile hash berhasil. Compose demo sintetis melayani JSON health dan HTML PWA melalui HTTP loopback; API, frontend, database, Redis dan worker sehat. Chromium di container worker berhasil diluncurkan dengan sandbox aktif, capability `SYS_CHROOT` terbatas, dan membuka merchant mock lokal. Konfigurasi Caddy HTTPS production lulus validasi sintaks dengan domain placeholder; sertifikat nyata belum diterbitkan.
- Browser Chromium desktop dan viewport mobile: flow batch preview/konfirmasi/pembatalan sintetis ditambahkan ke E2E yang sudah ada dan lulus tanpa error JavaScript.
- Migrasi baru hanya upgrade; downgrade otomatis sengaja dilarang karena tenant/NIK/batch baru membutuhkan backup terverifikasi. Workflow CI telah diubah mengikuti aturan ini, tetapi belum berjalan pada GitHub Actions.

## Berhasil

- API pada PostgreSQL: **17 test passed**, termasuk autentikasi, hash/session, CSRF dan login cross-site, role viewer/operator/admin, expiry, account lockout, pencabutan sesi/password, validasi tanpa echo secret, authorized merchant/filter, konflik duplikat, antrean, cancellation, pause/resume, failed transaction, pemeriksaan hak pembuat job, ekspor CSV dan settings.
- SQLite: **16 passed, 1 skipped**. Satu skip adalah pengujian konkurensi row lock khusus PostgreSQL, yang dijalankan dan lulus pada PostgreSQL.
- Dua worker PostgreSQL memproses transaksi simulasi pada merchant sama tanpa lost update stok. Tidak ada transaksi nyata.
- Migrasi Alembic baseline PostgreSQL upgrade → schema check (no diff) → downgrade → upgrade berhasil pada database sementara sebelum migrasi VPS. Migrasi VPS diperiksa melalui upgrade dan schema check; downgrade baru sengaja tidak didukung.
- Frontend unit test **1 passed**; typecheck dan build Vite berhasil. Instalasi ulang `npm ci` serta instalasi Python `--require-hashes` berhasil.
- Browser Chromium desktop dan mobile: login, merchant create/edit, filter, stok simulasi, transaksi simulasi, worker pause/resume, queued job cancel, user create/extend, CSV download, settings, role viewer read-only, logout/password change, modal dan layout mobile. Tidak ada error runtime JavaScript pada alur yang diuji. Ini bukan pengujian setiap kombinasi browser/input.
- PWA manifest dan icon, service worker registration, dan tidak adanya /api dalam Cache Storage diverifikasi. API memakai Cache-Control no-store. Data sintetis berlabel Demo Mode.
- Image Docker multi-stage berhasil dibangun dengan verifikasi TLS dan trust proxy. Startup awal gagal karena permission file root-copy; diperbaiki dengan ownership untuk UID 10001. Uji ulang API non-root/read-only, PostgreSQL migration, static PWA, penolakan akses tanpa session, API docs disabled dan heartbeat worker berhasil. Compose config lolos validasi. Full stack Compose dengan domain/TLS produksi belum dideploy.
- `npm audit`: **0 advisory** pada dependency web saat pemeriksaan. `pip-audit --disable-pip -r backend/requirements.lock`: **no known vulnerabilities**. Ini hanya dependency baru, bukan sertifikasi keamanan semua kode/binary atau requirements legacy.

## Belum diverifikasi / perlu tindakan

- Credential lama harus dirotasi; history lama, fork/Pages/cache dan salinan luar masih dapat memuat data sensitif. Scanner pola bukan audit forensik lengkap. Tidak ada rewrite/force push dilakukan.
- Adapter Playwright saat ini hanya terhubung ke merchant mock; alur UI Merchant MyPertamina live belum dipetakan atau diuji dengan akun berizin. Semua permintaan live ditolak. Stok/transaksi asli, penyimpanan credential aman, verifikasi manual OTP/CAPTCHA dan batas production belum diuji.
- Telegram hanya diuji dengan transport mock; tidak ada pesan nyata dikirim. Pengiriman nyata perlu secret baru, opt-in environment dan admin, serta pengujian terotorisasi.
- Instalasi iPhone/Android fisik, Safari iOS, audit aksesibilitas menyeluruh, load/penetration test, disaster recovery, HTTPS/reverse proxy, secret manager dan rate limiting IP belum diuji.
- CI workflow disiapkan; eksekusi pada GitHub Actions belum terjadi karena tidak ada push.
- Ada satu deprecation warning upstream Starlette TestClient terkait httpx; test tetap dieksekusi dan lulus.

**Kesimpulan:** aplikasi lokal dan jalur simulasi teruji; bukan klaim production-ready. Panduan deployment mencantumkan batas integrasi live, retensi dan prasyarat operasi nyata.
