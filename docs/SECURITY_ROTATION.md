# Rotasi dan pembersihan history — tindakan pemilik

Anggap seluruh secret yang pernah committed telah bocor, walaupun repo private. Jangan menempel nilai ke chat, tiket, log atau command line.

1. Hentikan instance bot lama yang dimiliki dan jadwalkan maintenance; jangan ganggu instance produksi tanpa persetujuan pemilik.
2. Cabut/regenerasi token bot melalui BotFather; periksa webhook dan aktivitas. Update secret store secara aman. Jangan menggunakan token lama dari file repository.
3. Rotasi PIN/password merchant melalui prosedur resmi; invalidasi seluruh cookie/session pada penyedia. Tinjau sesi yang tidak dikenal dan hak akses. Tinjau token GitHub/SSH jika ditemukan di clone/fork lain. Tidak ada token GitHub yang terdeteksi oleh pola awal bukan bukti ketiadaan.
4. Batasi akses salinan repo, artefak, Pages, log dan backup. Hapus data.json publik melalui perubahan terencana. Tentukan kewajiban retensi/pemberitahuan privasi untuk NIK, akun, chat ID dan aset gambar. Jangan otomatis mengimpor data pribadi legacy.
5. Salinan lokal sensitive yang telah di-untrack tetap ada. Simpan hanya backup terenkripsi yang aksesnya terbatas; jangan menyalinnya ke image Docker. Hapus lokal hanya setelah pemilik menyetujui retensi/pemusnahan.

Jalur `semiauto/` sudah dihapus dari checkout saat ini. Jalur itu tetap tercantum di bawah karena commit lama masih menyimpannya; penghapusan checkout tidak membersihkan history, fork, atau cache.

## Rewrite history (BELUM DIJALANKAN)

Rewrite mengubah SHA seluruh descendant dan tidak membatalkan secret. Rotasi dahulu. Butuh persetujuan eksplisit, jendela maintenance, daftar branch/tag/fork, backup terenkripsi terverifikasi dan koordinasi kolaborator. Jangan menjalankan pada working checkout berisi data.

Di clone mirror sementara yang terisolasi, setelah persetujuan:

```sh
git clone --mirror https://github.com/rigeladex44/mapauto.git mapauto-sanitized.git
cd mapauto-sanitized.git
git filter-repo --invert-paths \
  --path BOT1_CAPTCHA.env --path user_data/ --path durations.json \
  --path semiauto/akun.txt --path semiauto/nik.txt \
  --path semiauto/cookies/ --path semiauto/riwayat/ \
  --path __pycache__/ --path modules/__pycache__/ --path semiauto/__pycache__/ \
  --path webapp/data.json
```

Ini hanya daftar awal. Audit seluruh branch/tag, nama/path lama, blob orphan, string hardcoded, kontak dan binary. Siapkan replacement file rahasia di luar repo bila perlu, jangan cetak nilainya. Verifikasi hasil dengan scanner independen serta review manual. Minta GitHub Support menghapus cached views/PR refs bila relevan. Fork dan clone kolaborator perlu dibersihkan atau clone ulang.

**Jangan push dari prosedur ini secara otomatis.** Tinjau diff dan refs hasil, dapatkan persetujuan force push untuk refs tertentu, lalu lakukan terkontrol; jangan `push --mirror` karena dapat menghapus refs yang tidak dimaksud. Backup remote dan proteksi branch harus ditangani pemilik. Catat bukti rotasi tanpa nilai secret. Audit lagi sesudah rewrite dan clone baru. Sampai selesai, history lama tetap sensitif.
