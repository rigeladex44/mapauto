# Deployment Mapauto di VPS Ubuntu

Gunakan VPS Ubuntu 24.04/22.04 x86_64 dengan domain publik. Untuk satu Chromium context, mulai dari 2 vCPU, 4 GB RAM, dan ruang disk 30 GB; ukur beban sebelum menaikkan concurrency. Shared hosting biasa tidak dapat menjalankan Compose, Redis dan Chromium worker 24/7. Container hosting dapat dipakai bila mengizinkan proses panjang, storage persisten dan sandbox Chromium.

## Lokal (hanya demo sintetis)

Pasang Docker Engine dan Compose plugin. Dari root repo:

```sh
python3 -m venv .venv
.venv/bin/pip install --require-hashes -r backend/requirements.lock
.venv/bin/python scripts/generate-keys.py
# Ubah APP_DOMAIN, ACME_EMAIL dan ALLOWED_HOSTS di .env sebelum akses publik.
docker compose -f docker-compose.yml -f deploy/compose.demo.yml -f deploy/compose.smoke.yml --profile demo build
docker compose -f docker-compose.yml -f deploy/compose.demo.yml -f deploy/compose.smoke.yml --profile demo up -d
docker compose -f docker-compose.yml -f deploy/compose.demo.yml -f deploy/compose.smoke.yml exec api python -m backend.app.cli create-admin
docker compose -f docker-compose.yml -f deploy/compose.demo.yml -f deploy/compose.smoke.yml exec -T api python -m backend.app.cli seed-demo
docker compose -f docker-compose.yml -f deploy/compose.demo.yml -f deploy/compose.smoke.yml ps
curl --fail http://127.0.0.1:18080/api/health
```

Perintah `create-admin` meminta username/password secara interaktif. Jangan memasukkan password di argumen shell atau chat. Override smoke membatasi HTTP pada loopback host; Caddy production memerlukan DNS dan sertifikat. Demo Mode hanya menerima NIK sintetis; jangan masukkan NIK asli.

## VPS Ubuntu

1. Pasang Docker Engine dan Compose plugin dari dokumentasi resmi Docker, aktifkan update keamanan dan firewall 80/443/SSH. Arahkan A/AAAA domain ke VPS; pastikan port 80/443 dapat menerima ACME.
2. Clone branch yang telah direview. Audit file `.env`, permission, dan history dahulu. Jalankan `python3 -m venv .venv`, instal lockfile backend, lalu `scripts/generate-keys.py`; simpan `.env` mode 0600. Set `APP_DOMAIN`, `ACME_EMAIL`, `ALLOWED_HOSTS`. Simpan kunci di secret manager server jika tersedia. Jangan commit `.env`.
3. Jalankan `docker compose build` dan `docker compose up -d`. Migration job harus selesai sebelum API/worker. Jalankan `docker compose ps`, `docker compose exec -T api python -m backend.app.health api`, dan pemeriksaan HTTPS domain. Buat admin interaktif dengan `docker compose exec api python -m backend.app.cli create-admin`.
4. Atur backup terenkripsi: pasang `age` di host, tetapkan `BACKUP_RECIPIENT` berupa **public recipient** dan `BACKUP_DIR` terlindung, jadwalkan `scripts/backup.sh`, salin off-host, dan uji `scripts/restore-test.sh` terhadap database terisolasi. Lindungi private identity di luar repo.
5. Untuk pembaruan: backup teruji, `git pull` branch yang disetujui, `docker compose build`, `docker compose up -d`, periksa migrasi, health, audit dan job rekonsiliasi. Jangan rollback migrasi dengan downgrade otomatis; pulihkan backup teruji jika perlu.

`docker compose --profile demo -f docker-compose.yml -f deploy/compose.demo.yml` dipakai hanya untuk staging sintetis. Default production menonaktifkan Demo Mode dan **belum** bisa mengirim transaksi live. Tidak ada deployment VPS dalam pekerjaan ini karena akses VPS/domain belum diberikan.
