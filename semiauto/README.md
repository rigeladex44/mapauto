# 🛠️ Tools Semi-Manual NIK Pertamina (Terminal Murni - 1 Akun)

Tools ini berjalan **100% langsung di terminal tanpa bot Telegram**, difokuskan khusus untuk **1 akun pangkalan**.

---

## ⚡ Cara Kerja

1. **Otomatis**:
   - Membaca akun dari `semiauto/akun.txt` (atau pilih 1 kali saat pertama kali jalan).
   - Membuka browser Chromium di layar Anda (*headed mode*).
   - Login otomatis (atau memuat session cookies tersimpan).
   - Navigasi ke halaman verifikasi NIK (`/merchant/app/verification-nik`).
   - Mengambil NIK dari `semiauto/nik.txt`.
   - Mengisi 16 digit NIK secara otomatis dan klik cek NIK / Lanjutkan Penjualan.
   - Otomatis menangani modal jenis pelanggan (Rumah Tangga / Usaha Mikro) & popup NIB hingga tiba di halaman penjualan.

2. **MANUAL di Halaman Sale**:
   - Tepat di halaman:
     `https://subsiditepatlpg.mypertamina.id/merchant/app/sale`
   - Bot berbunyi beep dan **berhenti menunggu Anda di browser**:
     * Anda atur kuantitas tabung gas (1, 2, 3, 5 tabung).
     * Klik **Cek Pesanan** & **Proses Penjualan / Bayar**.
     * Geser **Slider Captcha**.

3. **Otomatis Lanjut**:
   - Begitu transaksi selesai (atau tombol *"Ke Beranda"* muncul / Anda tekan `[ENTER]` di terminal):
     * NIK dicatat sebagai **SUKSES** di `riwayat/sukses.txt`.
     * NIK yang selesai langsung dihapus dari antrean `nik.txt` agar tidak dobel.
     * Bot otomatis membawa browser kembali ke halaman input NIK.
     * Mengambil NIK berikutnya dari `nik.txt` dan mengulang proses sampai selesai!

---

## 📁 File Penting di Folder `semiauto/`

- **[akun.txt](file:///Users/rigeel/BOTMAPV7/semiauto/akun.txt)**: Akun aktif yang difokuskan (Format: `NAMA email|pin` atau `email|pin`).
- **[nik.txt](file:///Users/rigeel/BOTMAPV7/semiauto/nik.txt)**: Daftar NIK yang ingin diproses (1 NIK per baris).
- **[main.py](file:///Users/rigeel/BOTMAPV7/semiauto/main.py)**: Script utama langsung di terminal.
- **[run.sh](file:///Users/rigeel/BOTMAPV7/semiauto/run.sh)**: Launcher untuk Mac/Linux.
- **[run.bat](file:///Users/rigeel/BOTMAPV7/semiauto/run.bat)**: Launcher untuk Windows.
- **riwayat/**:
  - `sukses.txt` : NIK yang berhasil transaksi.
  - `limit.txt` : NIK yang limit kuota.
  - `tidak_ditemukan.txt` : NIK yang tidak terdaftar.
  - `skip.txt` : NIK yang dilewati.

---

## 🚀 Cara Menjalankan

### Di Mac / Linux:
```bash
cd /Users/rigeel/BOTMAPV7/semiauto
./run.sh
```
*atau:*
```bash
python3 main.py
```

### Di Windows:
Cukup klik ganda (double-click) file:
```
run.bat
```

---

## ⌨️ Kontrol Terminal di Halaman Sale
- **Deteksi Otomatis**: Bot otomatis mendeteksi ketika transaksi berhasil di browser.
- **Tekan `[ENTER]`**: Langsung paksa lanjut ke NIK berikutnya.
- **Ketik `s` lalu `[ENTER]`**: Skip NIK ini.
- **Ketik `q` lalu `[ENTER]`**: Berhenti (sisa NIK tersimpan aman di `nik.txt`).
