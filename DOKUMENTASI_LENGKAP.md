# 📚 DOKUMENTASI LENGKAP BOT LPG

**Versi System:** 4.26 (Mode Kalem & Auto Report)  
**Tanggal Update:** 26 April 2026

---

## 📋 DAFTAR ISI

1. [Cara Pasang di VPS Windows](#1-cara-pasang-di-vps-windows)
2. [Konfigurasi & Token](#2-konfigurasi--token)
3. [Cara Menambah Bot (Clone Folder)](#3-cara-menambah-bot-clone-folder)
4. [Sistem Akses & User](#4-sistem-akses--user)
5. [Menu & Fitur](#5-menu--fitur)
6. [Fitur Teknis Terbaru (Filter Pelanggan)](#6-fitur-teknis-terbaru-filter-pelanggan)
7. [Troubleshooting](#7-troubleshooting)

---

## 1. 🚀 CARA PASANG DI VPS WINDOWS

Panduan mudah untuk menjalankan bot di VPS Windows 11 Pro.

### 1️⃣ Install Python
1. Download Python: [Python 3.11.x](https://www.python.org/downloads/windows/)
2. **PENTING:** Saat install, **CENTANG** kotak **"Add Python to PATH"**.

### 2️⃣ Copy Bot
Copy seluruh folder `BOTMELON2` ke VPS Anda.

### 3️⃣ Instalasi (Sekali Saja)
Di dalam folder bot, klik 2x file:
👉 **`install_windows.bat`**
*   Tunggu sampai muncul "DOWNLOAD & INSTALASI SELESAI".
*   Script ini otomatis membuat environment dan install semua library.

### 4️⃣ Jalankan Bot
Untuk menjalankan bot:
👉 **`run_bot.bat`**
*   Bot akan jalan dengan fitur **auto-restart** (jika crash akan nyala lagi sendiri).
*   Jangan tutup jendela hitam tersebut (cukup minimize).

---

## 2. ⚙️ KONFIGURASI & TOKEN

### Edit Token
Buka file **`BOT1_CAPTCHA.env`** menggunakan Notepad.

```env
BOT_TOKEN=123456789:AAEOxxxxx...  <-- Token dari @BotFather
ALLOWED_CHAT_ID=5601279587
HEADLESS=1
FILTER_JENIS_PELANGGAN=RUMAH TANGGA,USAHA MIKRO
```

> **Note:**
> *   `HEADLESS=1` : Bot jalan di background (ringan).
> *   `FILTER_JENIS_PELANGGAN`: Jenis pelanggan yang diizinkan (pisahkan dengan koma).

---

## 3. 👯 CARA MENAMBAH BOT (CLONE FOLDER)

Jika Anda ingin menjalankan 2 bot atau lebih, caranya adalah dengan **mengkopi 1 folder utuh**.

1.  Copy folder `BOTMELON2`.
2.  Paste dan rename menjadi `BOTMELON_JATIM` (misalnya).
3.  Masuk ke folder `BOTMELON_JATIM`.
4.  Edit file `BOT1_CAPTCHA.env`, masukkan **Token Bot Baru**.
5.  Jalankan `run_bot.bat` di folder baru tersebut.

**Keuntungan:**
*   Bot benar-benar terpisah (isolasi total).
*   Data user tidak akan pernah tercampur.
*   Jika satu folder error, folder lain aman.

---

## 4. 👤 SISTEM AKSES & USER

Bot memiliki sistem proteksi ketat.

### Tipe User

1.  **👑 OWNER**
    *   Akses penuh tanpa batas.
    *   Punya **ADMIN PANEL** khusus.

2.  **✅ PREMIUM (Aktif)**
    *   Akses penuh ke semua fitur bot (Proses NIK, Cek Stok, dll).
    *   Langsung masuk Menu Premium saat `/start`.

3.  **⚠️ EXPIRED**
    *   Hanya bisa **Cek Durasi** dan **Perpanjang**.

4.  **🚫 USER BARU (Belum Terdaftar)**
    *   Tidak bisa akses apapun.
    *   Bot akan respon: *"Silahkan Hubungi @mhengkyy"*.
    *   Owner akan dapat notifikasi di Telegram.

### Cara Owner Tambah User
Kirim command:
`/add_duration [USER_ID] [HARI]`
Contoh: `/add_duration 123456789 30`

---

## 5. 📱 MENU & FITUR

### Menu Premium (User Aktif)
```
[PROSES AKUN] [LOGIN MANUAL]
[INPUT AKUN] [HAPUS AKUN]
[CEK STOK DATA]
[CEK DURASI] [PERPANJANG]
```

### Flow Login
1. User klik `[PROSES AKUN]`.
2. Pilih Akun → Bot Login.
3. Masuk ke **Menu Running** (`[STATUS]`, `[CEK STOK]`, `[LOGOUT]`).
4. Jika klik `[LOGOUT]`, file NIK otomatis dihapus (Auto-Cleanup).

---

## 6. 🛠️ FITUR TEKNIS TERBARU (FILTER PELANGGAN)

### ✅ Filter Jenis Pelanggan
Anda bisa membatasi bot hanya memproses jenis pelanggan tertentu.
*   **Contoh:** Hanya mau proses "Rumah Tangga" saja (Usaha Mikro dll di-skip).
*   **Cara:** Edit `.env`, set `FILTER_JENIS_PELANGGAN=RUMAH TANGGA`.
    *   Jika mau proses RT dan UM: `FILTER_JENIS_PELANGGAN=RUMAH TANGGA,USAHA MIKRO`.
*   Bot akan otomatis **SKIP** NIK yang jenis pelanggannya tidak sesuai dengan list ini.

### ✅ Server Down Detection
*   Bot mendeteksi jika web down atau session expired.
*   Otomatis login ulang.

### ✅ Auto-Cleanup Data
*   File `nik.txt` dihapus otomatis saat Logout/Restart.
*   Menjaga privasi dan kebersihan data antar user.

---

## 7. ❓ TROUBLESHOOTING

**Q: Bot tidak jalan setelah ganti token?**
A: Pastikan format token benar dan tidak ada spasi. Restart bot (tutup dan buka `run_bot.bat` lagi).

**Q: Di mana saya bisa melihat log error?**
A: Log muncul langsung di **jendela hitam (Terminal/CMD)** yang Anda buka saat menjalankan `run_bot.bat`. Tidak ada file log yang disimpan agar hemat penyimpanan.

**Q: Bagaimana cara update bot?**
A: Jika ada update script `BOT1_CAPTCHA.py`, cukup copy file py baru itu ke semua folder bot Anda.

**Q: Data user disimpan dimana?**
A: Di folder `user_data/`. Durasi user di file `durations.json`.
