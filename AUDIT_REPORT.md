# Audit keamanan dan migrasi Mapauto

Tanggal: 23 Oktober 2026. Scope: seluruh file tracked dan satu commit reachable pada awal audit; BOT1_CAPTCHA.py, modules, semiauto, webapp, durations.json, requirements.txt, dokumentasi dan semua launcher/cleanup. Audit statis; tidak ada login merchant, polling, pesan Telegram, transaksi, atau CAPTCHA dijalankan. Nilai sensitif tidak dicetak. Pemeriksaan pola bukan jaminan semua secret terdeteksi; binary/aset perlu review manual.

## Temuan

- **Kritis:** token Telegram, kredensial akun, cookie/session dan data pribadi ada dalam snapshot tracked. 55 file memiliki indikator pola atau jalur sensitif. `BOT1_CAPTCHA.env`, `user_data/`, `durations.json`, `semiauto/akun.txt`, `semiauto/nik.txt`, `semiauto/cookies/`, `semiauto/riwayat/`, dan cache bytecode harus dikeluarkan dari index. Salinan lokal dipertahankan; history lama tetap terpapar sampai prosedur rotasi dan rewrite yang disetujui selesai.
- **Kritis:** BOT1_CAPTCHA.py mematikan verifikasi SSL secara global. Installer Windows juga memakai trusted-host dan NODE_TLS_REJECT_UNAUTHORIZED=0. Dilarang digunakan oleh aplikasi baru.
- **Tinggi:** modules/auto_transaction.py menulis nama/stok ke GitHub Pages, menjalankan git add/commit/push origin main otomatis. Jalur ini tidak dipanggil aplikasi baru.
- **Tinggi:** modules/captcha.py dan semiauto/captcha_solver.py mengotomasi slider. Tidak dimigrasikan. Integrasi live yang dimaksud memakai Playwright pada antarmuka merchant dengan akun yang diotorisasi, bukan API resmi. Alur live belum diaktifkan; CAPTCHA/OTP harus berhenti pada checkpoint verifikasi manual.
- **Tinggi:** penyimpanan akun/PIN/cookie plaintext; NIK dan antrean file, otorisasi berbasis chat ID hardcoded. Tidak diimpor otomatis. Perlu pemilik data menyetujui pemetaan dan retensi sebelum impor.
- **Sedang:** webapp/index.html lama hanya dashboard stok read-only Telegram dengan fallback dummy, data.json statis, dan interpolasi innerHTML berisiko XSS. Tidak ada API/auth/PWA. Gunakan kembali konsep agregasi stok, pengurutan stok, daftar merchant, dan expiry, bukan menduplikasi seluruh bot.
- **Sedang:** durations JSON tanpa concurrency control; session process-local; worker threading tanpa durable queue dan event audit. Tidak cocok dipindah langsung ke web multiuser.
- **Sedang:** cleanup.sh/.bat menghapus log dan cache; run_bot.bat auto-restart tanpa readiness atau shutdown terkelola. Tidak dipakai untuk web.
- requirements.txt cocok Python 3.11, tetapi memuat dependency browser/image lama. Web memiliki requirements terpisah; pemutakhiran runtime legacy bukan bukti jalur transaksi aman.
- DOKUMENTASI_LENGKAP.md mendokumentasikan instalasi Windows, durasi, filter, dan bot; dokumentasi baru harus mengacu pada web. Asumsi nama/ID/tautan legacy tidak dijadikan default web.

## Batas verifikasi

Fitur legacy diidentifikasi dari implementasi, bukan diverifikasi dengan transaksi nyata. Logika murni yang layak dipertahankan: ekstensi expiry dari max(now, expiry), filter jenis pelanggan, agregasi/sort stok, status antrean dan ringkasan. Tidak mengimpor modul Telegram karena efek samping konfigurasi dan coupling. Laporan testing web ditulis terpisah setelah implementasi. `.gitignore` tidak menghapus history; tidak ada force push atau rewrite remote dilakukan.

Jalankan `python scripts/security_audit.py` untuk laporan JSON teredaksi (path/kategori/jumlah saja); simpan laporan rinci di luar repo. Jangan memakai git diff atas file sensitif yang dihapus dari index saat merekam output.

## Remediasi pada branch fitur

Pada branch VPS, audit statis ulang terhadap tree kerja dan history tetap hanya menyimpan kategori/jumlah temuan di luar repo; tidak ada nilai rahasia dicetak. Temuan history lama tetap berlaku. Migrasi baru menambahkan tenant boundary, grant merchant, enkripsi NIK, audit checkpoint, worker browser terisolasi, Redis queue dan batas production yang menolak adapter live. Image dan Compose hanya menyalin source web/backend baru, bukan data legacy. File `.env` dibuat lokal mode 0600 dan diabaikan Git. Pembersihan history belum dilakukan karena memerlukan rotasi serta persetujuan force push.

52 jalur runtime/cache dihapus dari index (salinan lokal tetap), ditambah dua aset legacy pembayaran/branding yang dikarantina untuk review privasi. Identifier/contact default pada teks legacy disamarkan. Legacy bot dan semiauto entrypoint dihentikan; bypass SSL global dihapus, installer yang menonaktifkan verifikasi diganti panduan migrasi, dan fungsi publikasi stok ke GitHub dihentikan. Implementasi CAPTCHA lama disimpan hanya sebagai arsip kode; tidak diimpor aplikasi atau dimasukkan image. Kode bisnis murni dipisahkan di backend/app/domain.py, bukan menjalankan handler Telegram.

History masih mengandung secret dari commit awal; commit remediasi tidak menghilangkannya. Rotasi, review binary/aset, rewrite Git history, fork/Pages/cache cleanup dan persetujuan pemilik tetap diperlukan. Tidak ada push, force push, pemusnahan salinan lokal, ataupun perubahan transaksi production.
