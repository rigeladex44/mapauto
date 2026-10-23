# Mapauto Web — pengembangan dan deployment

Status: implementasi awal yang dapat diuji, **belum production-ready**. Lihat AUDIT_REPORT.md, SECURITY_ROTATION.md dan TEST_REPORT.md. Aplikasi baru tidak mengimpor handler legacy, data akun/cookie/NIK, atau durations.json. Single organization: seluruh role yang berhak membaca dapat melihat metadata merchant workspace yang sama; bukan SaaS multitenant.

## Lokal

Python 3.11+, Node 22.12+ (toolchain frontend modern). Pakai checkout yang ada, tidak perlu worktree. Jalankan dari root repository:

```sh
python3.11 -m venv .venv
. .venv/bin/activate
pip install --require-hashes -r backend/requirements.lock
cp .env.example .env
alembic -c backend/alembic.ini upgrade head
python -m backend.app.cli create-admin
npm ci --prefix webapp
npm run build --prefix webapp
bash scripts/dev.sh
```

Admin CLI meminta password tersembunyi, tanpa default. API melayani build PWA pada origin yang sama. SQLite hanya untuk lokal dan satu worker. Untuk frontend hot reload, jalankan `npm run dev --prefix webapp` di terminal lain; Vite memproxy /api ke backend, bukan CORS terbuka. Jangan gunakan dev server untuk production.

Mode default kosong; tidak ada seed otomatis. Untuk demo tanpa transaksi nyata, set `DEMO_MODE=true` di .env **sebelum** memulai API/worker, lalu:

```sh
python -m backend.app.cli seed-demo
python -m backend.app.worker
```

Buat job pemeriksaan stok simulasi sebelum transaksi simulasi. Semua angka hasil worker adalah sintetis dan dilabeli. Jangan memakai database demo untuk production. Worker heartbeat setiap detik; UI polling setiap tiga detik. Job tersimpan, pembatalan menghalangi hasil diterapkan; job worker mati ditandai gagal setelah 60 detik, tidak diulang otomatis. Jeda hanya menghalangi klaim baru. Status offline setelah 20 detik. `WORKER_ID` harus unik dan stabil per proses. Maksimum 200 job/log terakhir ditampilkan; CSV mengekspor semua job. Pagination lanjutan/retention belum tersedia.

## Keamanan dan role

- Admin: pengguna, masa aktif, pengaturan, seluruh operasi; operator: merchant/filter/job/worker/log/laporan; viewer: dashboard/merchant/stok/job/worker read-only.
- Session opaque disimpan sebagai SHA-256 di DB, cookie HttpOnly/SameSite Strict, CSRF header pada perubahan, expiry dan status akun diperiksa per request. Password scrypt; minimum 12 karakter. Password change mencabut seluruh sesi. Admin tidak dapat mencabut akses sendiri.
- Lima login gagal pada akun mengunci 5 menit. Tambahkan rate limiting berdasarkan IP pada reverse proxy (termasuk akun yang tidak ada), batas ukuran request, timeout, monitoring dan alert. MFA, reset password via email, recovery otomatis dan SSO belum tersedia; admin CLI hanya bootstrap akun baru.
- Merchant hanya metadata/referensi internal dan pernyataan otorisasi; tidak menyimpan PIN/cookie/password merchant. Jangan menaruh credential atau NIK pada nama/referensi. Form bukan brankas rahasia.
- Tidak ada transaksi live, OTP/CAPTCHA automation, atau bypass limit. Integrasi yang direncanakan menggunakan Playwright pada UI merchant dengan akun berizin, bukan API resmi. Port `AuthorizedMerchantAdapter` fail-closed sampai alur UI, otorisasi akun, retensi, idempotensi, persetujuan transaksi dan uji terkontrol tersedia. Monitoring transaksi saat ini berasal dari job simulasi, bukan data merchant live.
- Telegram opsional: secret **baru yang dirotasi** di server `TELEGRAM_BOT_TOKEN`, target `TELEGRAM_CHAT_ID`, `TELEGRAM_ENABLED=true`, kemudian admin mengaktifkan pengaturan UI. Pengaktifan adalah opt-in untuk notifikasi job berikutnya. Pesan hanya ID job, tanpa nama/PIN/NIK. Jangan menyalakan saat testing. Pengiriman at-most-once; status failed/sending perlu review manual, tidak retry otomatis. Jalur ini tidak diuji terhadap Telegram nyata.
- Secret jangan diletakkan di build arguments, browser, image, repo atau output `docker compose config`. Di deployment nyata gunakan secret manager dan restricted env/file injection. DB backup mengandung hash/session; enkripsi dan batasi akses.

## PostgreSQL dan Docker

Compose menyediakan PostgreSQL 17, migrasi satu kali, API dan worker non-root. Siapkan `.env` dengan `POSTGRES_PASSWORD` kuat dan `DATABASE_URL=postgresql+psycopg://mapauto:<URL-encoded-password>@db:5432/mapauto`, `APP_ENV=production`, `COOKIE_SECURE=true`, `DEMO_MODE=false`, `ALLOWED_HOSTS=localhost,app.example.com` (ganti domain). `localhost` dipakai healthcheck container, bukan wildcard. Jangan commit nilai. Jangan print resolved Compose config karena memuat secret.

```sh
docker compose build
docker compose up -d db migrate api worker
docker compose exec api python -m backend.app.cli create-admin
```

Gunakan TLS reverse proxy pada origin publik, proxy ke port loopback 8000, HSTS, request body limit dan login rate limits. TLS terminasi tidak disiapkan otomatis. Cookie secure memerlukan HTTPS; jangan matikan di production. Framework tidak mempercayai forwarded headers default. Terapkan allowlist host dan egress, hanya DB internal dan Telegram jika opt-in. PostgreSQL tidak diekspos ke host. Sediakan backup dan uji restore sebelum penggunaan nyata. Jangan menjalankan downgrade/menghapus volume pada DB production tanpa backup dan persetujuan.

Dalam cloud managed yang memakai CA proxy saat build:

```sh
docker build --secret id=proxy_ca,src="$CODEX_PROXY_CERT" \
  --secret id=ca_bundle,src=/etc/ssl/certs/ca-certificates.crt \
  -t mapauto-web:local .
```

Gunakan pengaturan proxy bawaan, bukan host networking. Runtime yang perlu HTTPS juga memerlukan bundle CA yang dipasang read-only dan `SSL_CERT_FILE`; jangan menanam CA sesi ke image. Di host normal secret CA build opsional. Tidak ada file legacy/data rahasia dalam build context karena whitelist .dockerignore.

## PWA

Manifest, ikon 192/512, apple-touch-icon dan service worker tersedia. Android/desktop instal dari menu browser; iOS Safari dari Share → Add to Home Screen. HTTPS wajib kecuali localhost. Shell publik dapat di-cache, API/credential tidak di-cache. Offline tidak dapat login atau membaca data server; ini disengaja. Uji instalasi perangkat nyata iOS/Android diperlukan sebelum rilis.

## Pengujian

```sh
python -m pytest backend/tests -q
npm test --prefix webapp
npm run build --prefix webapp
```

CI juga memigrasikan PostgreSQL dan menguji API/worker menggunakan database test terisolasi. Test tidak boleh memakai DATABASE_URL production. Script browser tambahan `scripts/test_browser.py` memerlukan Playwright dan Chromium sistem; env `BACKEND_PYTHON` menentukan Python backend. Script membuat DB dan admin sintetis sementara, menjalankan server/worker sendiri, lalu menghentikannya. Tidak memakai akun merchant nyata. Tidak ada tes yang mengirim pesan Telegram.
