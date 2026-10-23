# Checklist keamanan produksi

- [ ] Rotasi seluruh token, PIN/password merchant, cookie, sesi, dan akses Git yang pernah ada di history; validasi revoke bersama pemilik.
- [ ] Review semua branch, tag, fork, Pages, aset binary, backup, dan cached GitHub view; rencanakan rewrite history terpisah. **Jangan force push tanpa persetujuan eksplisit.** Lihat [rotasi](docs/SECURITY_ROTATION.md).
- [ ] Konfirmasi hak penggunaan akun merchant dan izin otomasi antarmuka melalui Playwright sebelum mengaktifkan integrasi live. Tinjau ketentuan layanan, alur login, CAPTCHA/OTP manual, dan batas transaksi. Mode production saat ini menolak transaksi.
- [ ] Domain dan email ACME nyata; HTTPS valid, firewall hanya port 80/443/SSH, SSH berbasis key dan MFA admin hosting.
- [ ] `.env` mode 0600 dengan kunci unik; batasi akses OS, backup terenkripsi dan salinan off-host. Simpan key lama untuk decrypt selama rotasi terencana.
- [ ] Jalankan migrasi di staging dan restore backup ke database terisolasi sebelum update produksi.
- [ ] Periksa dukungan user namespace/seccomp Chromium di VPS. Jangan memakai `privileged`, mematikan sandbox, atau membuka CDP/VNC publik.
- [ ] Ukur RAM/CPU worker, set `MAX_BROWSER_CONTEXTS` dan `WORKER_CPUS` sesuai VPS, pantau OOM dan restart.
- [ ] Uji tenant isolation, RBAC, CSRF, cookie Secure/HttpOnly/SameSite, rate limit Redis, audit dan masking di staging.
- [ ] Tentukan retensi NIK, audit, log, dan bukti transaksi bersama pemilik data; dokumentasikan prosedur penghapusan.
- [ ] Pantau health API/worker, antrean, checkpoint kedaluwarsa, job `RECONCILIATION_REQUIRED`, kapasitas disk, sertifikat, backup.

Checklist belum berarti lolos produksi. Hasil yang benar-benar diuji ada di [laporan test](docs/TEST_REPORT.md).
