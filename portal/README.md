# MAP.PRO — frontend + backend Playwright

Implementasi integrasi terpisah dari bot Telegram lama. Frontend membawa desain prototipe terakhir: logo MAP.PRO, hijau glossy, ikon LPG, input NIK, kontrol batch dan laporan.

## Cakupan versi ini

**Mode real saat ini adalah inspeksi, bukan penjualan otomatis.**

- Login manual ke situs merchant memakai akun operator sendiri.
- Nama pangkalan dan stok dibaca dari merchant; jika gagal stok terakhir tetap ditampilkan dengan keterangan belum sinkron.
- NIK satu jenis langsung diperiksa pada kartu Informasi Pelanggan.
- NIK beberapa jenis dipilih berdasarkan teks persis, bukan posisi tombol.
- RT & UM: prioritas UM; pindah ke RT hanya setelah limit sebelum penjualan terverifikasi.
- Jenis lain atau jenis yang tidak terbaca pasti tidak dilanjutkan.
- Berhenti di halaman penjualan, tanpa menekan Cek Pesanan, bayar, konfirmasi transaksi atau menyelesaikan CAPTCHA.
- Status **Siap ditinjau** berarti jenis sudah terverifikasi, bukan transaksi sukses. Jumlah tabung terjual selalu 0 dalam inspeksi.
- Tombol jeda/stop berlaku setelah NIK aktif; sisa NIK tidak dibuang dan tidak dijalankan otomatis setelah restart.
- Kunci akses backend wajib; PIN dan token disimpan hanya di memori, tidak ditulis ke database/browser storage/log aplikasi.
- Database lokal menyimpan NIK dan hasil, berizin file 0600. Batasi akses host dan gunakan disk terenkripsi bila diperlukan. Tidak ada NIK dalam URL.
- Laporan dipisahkan per sesi aplikasi. Riwayat bertahan di database, tetapi login ulang belum dapat mengakses riwayat sesi lama; autentikasi pengguna permanen adalah pekerjaan berikutnya.
- Tidak mengimpor atau menjalankan bot Telegram, `.env` lama, cookie akun lama, atau solver CAPTCHA lama.

## Jalankan lokal di Mac/Linux (pengujian pertama)

Dari root repo:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r portal/backend/requirements.lock.txt
playwright install chromium
```

Buat kunci acak dan atur langsung di terminal lokal (jangan kirim ke chat / commit):

```bash
export MAP_ACCESS_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export MAP_HEADLESS=false
python3 -m uvicorn portal.backend.app:app --host 127.0.0.1 --port 8000 --no-access-log
```

Buka `http://127.0.0.1:8000`. Isi kunci akses dari variabel lokal `MAP_ACCESS_KEY` melalui form aplikasi, lalu email/ponsel dan PIN merchant Anda sendiri. Untuk melihat kunci gunakan terminal lokal yang terpisah sesuai metode penyimpanan rahasia Anda. Jangan masukkan kunci asli ke Git atau file frontend.

Pilih **Playwright · Uji baca merchant**. Browser Chromium akan muncul di komputer tempat backend dijalankan. Jika CAPTCHA atau verifikasi muncul, selesaikan sendiri di browser tersebut lalu klik **Periksa sesi**. Jangan membuka sesi merchant kedua untuk akun yang sama sebelum logout.

Tes pertama:

1. Cocokkan nama dan stok pada dashboard dengan browser merchant.
2. Mulai dengan 1 NIK yang sah dan diizinkan untuk pengujian, lalu uji RT/UM.
3. Periksa jenis yang aktif pada halaman penjualan. Tidak ada transaksi yang dikirim.
4. Uji NIK dengan dua atau tiga pilihan, dan limit UM. Pastikan fallback hanya pada penolakan yang jelas.
5. Logout dari MAP.PRO untuk menutup browser dan menghapus token sesi.

**Satu NIK:** halaman penjualan dibiarkan terbuka untuk pemeriksaan. **Batch:** NIK berikutnya akan membuka verifikasi lagi setelah hasil disimpan; gunakan Jeda jika ingin memeriksa halaman setiap NIK. Sinkronisasi stok hanya bisa dilakukan saat batch tidak aktif karena memakai browser yang sama.

## Demo UI

Pilih **Demo UI** pada halaman login. Data dan hasil tetap simulasi. Mode demo tidak mengirim permintaan merchant; jangan gunakan hasil demo sebagai bukti transaksi.

## Frontend di Vercel

- Root Directory: `portal/frontend`; static project, tanpa build.
- Isi `MAP_API_BASE` di `portal/frontend/config.js` dengan **origin HTTPS backend**, tanpa `/api` di belakang.
- Atur `MAP_ALLOWED_ORIGINS` di backend menjadi origin HTTPS Vercel yang tepat. Jangan gunakan `*`.
- Kunci akses backend tetap dimasukkan lewat form dan tidak ditulis ke config.js.
- HTTPS wajib untuk penggunaan di internet; untuk tes pertama gunakan localhost.

## VPS / Docker

```bash
docker build -f portal/backend/Dockerfile -t map-pro .
docker run --rm -p 127.0.0.1:8000:8000 \
  --env MAP_ACCESS_KEY --env MAP_ALLOWED_ORIGINS \
  -v map-pro-data:/app/portal/runtime map-pro
```

Image memakai user non-root dan browser terpisah dari kode bot. Untuk volume bind mount, pastikan user container dapat menulis direktori runtime. Letakkan reverse proxy HTTPS dan rate limit di depan backend. Jangan mengekspos port 8000 tanpa proteksi.

Docker berjalan headless. Verifikasi manusia yang memerlukan browser terlihat harus diuji lokal terlebih dahulu; viewer remote yang aman belum disediakan. Mode inspeksi tidak melewati CAPTCHA. Menutup terminal atau restart backend mengakhiri sesi browser; login ulang diperlukan. Batch terputus tidak diteruskan otomatis.

## Konfigurasi

| Variabel | Fungsi |
| --- | --- |
| MAP_ACCESS_KEY | Minimal 24 karakter acak, wajib saat startup |
| MAP_HEADLESS | `false` untuk Chromium terlihat di komputer penguji; default true |
| MAP_ALLOWED_ORIGINS | Daftar origin frontend HTTPS dipisahkan koma |
| MAP_MAX_SESSIONS | Batas browser aktif, default 2 |
| MAP_DB_PATH | Lokasi SQLite, default `portal/runtime/map-pro.sqlite3` |

## Pemeriksaan otomatis

```bash
pip install httpx==0.28.1
python -m unittest discover -s portal/tests -v
node --check portal/frontend/live.js
```

Pengujian menggunakan adapter merchant palsu dan fixture tampilan/logika. Tidak login atau bertransaksi dengan merchant asli. Selektor real didasarkan pada repo mapauto dan foto yang diberikan; perubahan situs masih dapat memerlukan penyesuaian setelah uji lokal.

## Tahap berikutnya

Tuntaskan uji baca real dan tetapkan aturan jumlah tabung sebelum mengaktifkan penjualan. Tambahkan autentikasi pengguna/admin, pemulihan status transaksi yang benar-benar terverifikasi, dan aturan retry/idempotensi. Versi ini sengaja tidak memiliki endpoint submit transaksi.

## Catatan repository

`.gitignore` baru mencegah penambahan runtime/rahasia berikutnya. File sensitif yang sudah tracked atau berada dalam riwayat Git **tidak otomatis terhapus**. Cabut/rotasi kredensial yang pernah dipublikasikan dan tangani pembersihan riwayat secara terpisah; patch ini tidak menghapus data lama Anda.
