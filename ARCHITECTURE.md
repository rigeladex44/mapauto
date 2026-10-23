# Arsitektur Mapauto VPS

Browser pengguna mengakses Caddy melalui HTTPS. Caddy meneruskan `/api/*` ke FastAPI dan aset PWA ke Nginx. FastAPI memakai PostgreSQL sebagai sumber status dan Redis untuk sinyal antrean. Worker Python mengklaim job dengan lock merchant di Redis dan row lock serta fencing token di PostgreSQL, lalu membuka Chromium context baru untuk satu job. Tidak ada port database, Redis, debugging browser, atau VNC yang diterbitkan.

Setiap user, merchant, batch, job, worker, notifikasi, dan audit membawa `tenant_id`. Query API dibatasi di lapisan ORM menurut tenant; operator dibatasi lagi oleh `MerchantGrant`. Admin dapat memberi akses merchant dan menonaktifkannya. Browser context baru menutup setiap job dan tidak menyimpan cookie antarmerchant. Kapasitas global browser dibatasi `MAX_BROWSER_CONTEXTS`; tiap merchant hanya satu job aktif.

Batch mengharuskan preview, format NIK 16 digit, deduplikasi, dan konfirmasi. NIK disimpan terenkripsi Fernet sementara job berjalan, indeks deduplikasi berupa HMAC, dan respons API hanya menampilkan nilai tersamar. Key idempotensi menjaga pengiriman berulang. Jika status pengiriman tidak diketahui setelah crash, job masuk `RECONCILIATION_REQUIRED` dan tidak dikirim lagi otomatis. Checkpoint OTP/CAPTCHA berstatus `WAITING_VERIFICATION`, memerlukan operator berizin dan kedaluwarsa. Tidak ada solver otomatis.

**Batas integrasi:** adapter browser saat ini hanya berbicara dengan merchant mock lokal untuk Demo Mode. Endpoint batch menolak mode production. Akun/NIK asli dan transaksi live belum didukung sampai metode resmi, izin, serta review perubahan transaksi diberikan. Telegram hanya kanal notifikasi opsional, bukan pengendali aplikasi.

Sumber logika legacy yang telah dipindahkan: expiry dari `max(now, expiry)`, filter pelanggan, agregasi stok, status job, dan audit. Bot Telegram lama serta skrip transaksi/CAPTCHA tidak dijalankan oleh Compose. Rincian temuan ada di [AUDIT_REPORT.md](AUDIT_REPORT.md).
