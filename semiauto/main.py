# Legacy merchant automation is excluded from the web migration.
if __name__ == "__main__":
    raise SystemExit("Legacy automation retired. Use authorized web integrations only.")

import os
import sys
import time
from pathlib import Path

# Setup Path mandiri di semiauto
CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from config import (
    AKUN_FILE, NIK_FILE,
    SUKSES_FILE, LIMIT_FILE, TIDAK_DITEMUKAN_FILE, SKIP_FILE,
    DEFAULT_ALLOWED_TYPES
)
from processor import SemiAutoProcessor, append_to_file

def clear_screen():
    os.system('cls' if os.name == 'nt' else 'clear')

def parse_account_string(line: str) -> dict or None:
    line = line.strip()
    if not line or line.startswith("#") or line.startswith("["):
        return None
    if "|" not in line:
        return None
    parts = line.split()
    cred = parts[-1]
    name = " ".join(parts[:-1]) if len(parts) > 1 else "AKUN"
    if "|" in cred:
        email, pin = cred.split("|", 1)
        if email.strip() and pin.strip():
            return {
                "name": name.strip(),
                "email": email.strip(),
                "pin": pin.strip()
            }
    return None

def get_saved_account() -> dict or None:
    """Membaca akun tersimpan dari semiauto/akun.txt"""
    if not AKUN_FILE.exists():
        return None
    with open(AKUN_FILE, "r", encoding="utf-8") as f:
        for line in f:
            acc = parse_account_string(line)
            if acc:
                return acc
    return None

def save_account_to_file(acc: dict):
    """Menyimpan akun ke semiauto/akun.txt"""
    with open(AKUN_FILE, "w", encoding="utf-8") as f:
        f.write("# Konfigurasi Akun Semi-Manual\n")
        f.write(f"{acc['name']} {acc['email']}|{acc['pin']}\n")

def read_valid_niks(file_path: Path) -> list[str]:
    """Membaca NIK 16 digit yang valid dari file"""
    if not file_path.exists():
        return []
    niks = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            digits = "".join(filter(str.isdigit, line))
            if len(digits) == 16 and digits not in niks:
                niks.append(digits)
    return niks

def write_niks_to_file(file_path: Path, niks: list[str]):
    """Menyimpan sisa NIK ke file"""
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("# Daftar NIK Antrean Semi-Manual:\n")
        for nik in niks:
            f.write(nik.strip() + "\n")

def setup_single_account() -> dict:
    """Memastikan ada akun di akun.txt"""
    saved_acc = get_saved_account()
    if saved_acc:
        return saved_acc

    print("\n🔍 File 'akun.txt' belum terisi.")
    print("Silakan masukkan data akun pangkalan:")
    print("----------------------------------------------------------------------")
    nama = input("Nama Pangkalan/Akun : ").strip() or "PANGKALAN"
    email = input("Email / No Handphone : ").strip()
    pin = input("PIN Akun Pertamina   : ").strip()
    acc = {"name": nama, "email": email, "pin": pin}
    save_account_to_file(acc)
    print(f"✅ Akun [{nama}] berhasil disimpan ke akun.txt.")
    return acc

def main():
    clear_screen()
    print("""
======================================================================
     🔥 TOOLS PROSES NIK SEMI-MANUAL (TERMINAL MURNI - 1 AKUN) 🔥
======================================================================
  [Otomatis] : Login -> Masuk Catat Penjualan -> Input NIK -> Verifikasi
  [MANUAL]   : Halaman /merchant/app/sale (Atur Qty, Bayar & Captcha)
  [Otomatis] : Selesai -> Kembali ke Input NIK -> Lanjut NIK Berikutnya
======================================================================
    """)

    # 1. Pastikan Akun Tunggal
    account = setup_single_account()
    print(f"👤 AKUN AKTIF : {account['name']} ({account['email']})")
    print(f"   (Jika ingin ganti akun, cukup edit file: {AKUN_FILE.name})")

    # 2. Baca NIK dari nik.txt
    if not NIK_FILE.exists():
        NIK_FILE.touch()

    nik_queue = read_valid_niks(NIK_FILE)

    if not nik_queue:
        print(f"\n⚠️ File '{NIK_FILE.name}' masih kosong.")
        print("Silakan tempelkan (paste) NIK di terminal sekarang (1 NIK per baris).")
        print("Ketik baris kosong lalu tekan [ENTER] jika sudah selesai:")
        while True:
            line = input().strip()
            if not line:
                break
            digits = "".join(filter(str.isdigit, line))
            if len(digits) == 16 and digits not in nik_queue:
                nik_queue.append(digits)
            elif digits:
                print(f"⚠️ NIK tidak valid (harus 16 digit): {line}")

        if nik_queue:
            write_niks_to_file(NIK_FILE, nik_queue)

    if not nik_queue:
        print(f"\n❌ Tidak ada NIK untuk diproses. Silakan isi NIK di file '{NIK_FILE.name}'.")
        print("Program selesai.")
        sys.exit(0)

    print(f"\n📊 TOTAL NIK SIAP DIPROSES: {len(nik_queue)} NIK")
    print("----------------------------------------------------------------------")
    print("💡 Browser akan terbuka di layar Anda.")
    print("   Setiap NIK akan di-input otomatis.")
    print("   Saat tiba di halaman /merchant/app/sale, giliran Anda secara MANUAL:")
    print("   - Tentukan kuantitas tabung LPG")
    print("   - Klik Cek Pesanan & Bayar")
    print("   - Geser Slider Captcha")
    print("   Setelah transaksi selesai, bot OTOMATIS lanjut ke NIK berikutnya!")
    print("----------------------------------------------------------------------")

    input("\nTekan [ENTER] untuk membuka browser dan mulai...")

    # Simpan antrean awal
    write_niks_to_file(NIK_FILE, nik_queue)

    # 3. Jalankan Engine Semi-Auto
    processor = SemiAutoProcessor(
        account_name=account["name"],
        email=account["email"],
        pin=account["pin"],
        allowed_types=DEFAULT_ALLOWED_TYPES
    )

    stat_sukses = 0
    stat_limit = 0
    stat_tidak_ditemukan = 0
    stat_skip = 0

    try:
        processor.start_browser()
        if not processor.login():
            print("❌ Gagal login. Periksa kembali email dan PIN di akun.txt.")
            return

        if not processor.buka_halaman_input_nik():
            print("❌ Gagal membuka halaman input NIK.")
            return

        total_antrian = len(nik_queue)
        idx = 0

        while nik_queue:
            nik = nik_queue.pop(0)
            idx += 1
            # Update sisa NIK di file secara real-time
            write_niks_to_file(NIK_FILE, nik_queue)

            print(f"\n{'='*70}")
            print(f"🔄 [{idx}/{total_antrian}] Memproses NIK: {nik}")
            print(f"{'='*70}")

            # 1. Otomatis Input NIK dan lanjut ke Sale
            ok, status = processor.input_nik_dan_periksa(nik)

            if not ok:
                if status == "LIMIT":
                    print(f"❌ NIK {nik} terdeteksi LIMIT. Disimpan ke riwayat/limit.txt")
                    append_to_file(LIMIT_FILE, f"{nik} | {time.strftime('%Y-%m-%d %H:%M:%S')}")
                    stat_limit += 1
                elif status == "TIDAK_DITEMUKAN":
                    print(f"❌ NIK {nik} TIDAK DITEMUKAN. Disimpan ke riwayat/tidak_ditemukan.txt")
                    append_to_file(TIDAK_DITEMUKAN_FILE, f"{nik} | {time.strftime('%Y-%m-%d %H:%M:%S')}")
                    stat_tidak_ditemukan += 1
                else:
                    print(f"⚠️ NIK {nik} Gagal/Skip (Status: {status}).")
                    append_to_file(SKIP_FILE, f"{nik} | {status} | {time.strftime('%Y-%m-%d %H:%M:%S')}")
                    stat_skip += 1

                processor.buka_halaman_input_nik()
                time.sleep(1)
                continue

            # 2. Tiba di Halaman Sale -> BAGIAN MANUAL
            hasil_manual = processor.tunggu_proses_manual_di_sale(nik)

            if hasil_manual == "STOP":
                # Kembalikan NIK yang belum selesai ke awal antrean
                nik_queue.insert(0, nik)
                write_niks_to_file(NIK_FILE, nik_queue)
                print("\n🛑 Proses dihentikan oleh user. Sisa NIK tersimpan aman di nik.txt.")
                break
            elif hasil_manual == "SKIP":
                print(f"⏭️ NIK {nik} di-SKIP oleh user.")
                append_to_file(SKIP_FILE, f"{nik} | USER_SKIP | {time.strftime('%Y-%m-%d %H:%M:%S')}")
                stat_skip += 1
            else: # SUKSES
                print(f"🎉 NIK {nik} TRANSAKSI SUKSES! Disimpan ke riwayat/sukses.txt")
                append_to_file(SUKSES_FILE, f"{nik} | {time.strftime('%Y-%m-%d %H:%M:%S')}")
                stat_sukses += 1

            # 3. Otomatis kembali ke input NIK untuk NIK berikutnya
            print("⏳ Menyiapkan NIK berikutnya secara otomatis...")
            processor.buka_halaman_input_nik()
            time.sleep(1)

    except KeyboardInterrupt:
        print("\n🛑 Program dihentikan (Ctrl+C). Sisa NIK tersimpan di nik.txt.")
    except Exception as e:
        print(f"\n❌ Terjadi kesalahan: {e}")
    finally:
        print("\n" + "="*70)
        print("📊 REKAPITULASI HASIL:")
        print(f"   ✅ Sukses         : {stat_sukses}")
        print(f"   ❌ Limit          : {stat_limit}")
        print(f"   ❓ Tidak Ditemukan: {stat_tidak_ditemukan}")
        print(f"   ⏭️ Skip/Lainnya    : {stat_skip}")
        print(f"   📁 Riwayat tersimpan di: {CURRENT_DIR / 'riwayat'}")
        print(f"   📄 Sisa NIK tersimpan di: {NIK_FILE.name} ({len(nik_queue)} NIK)")
        print("="*70)

        tutup = input("\nApakah ingin menutup jendela browser? (y/n, default y): ").strip().lower()
        if tutup != "n":
            processor.close()
            print("🔒 Browser ditutup.")

if __name__ == "__main__":
    main()
