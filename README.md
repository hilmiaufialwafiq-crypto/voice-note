# Voice to Notes

Aplikasi pencatat materi berbasis Flask. Pengguna dapat merekam suara dari browser atau mengunggah audio, mengedit hasil transkripsi, menyimpan catatan ke SQLite, mencari, mengedit, menghapus, dan mengunduh catatan sebagai TXT atau PDF.

## Persyaratan

- Python 3.10 atau lebih baru
- Koneksi internet untuk layanan transkripsi Google Speech Recognition
- FFmpeg untuk memproses MP3, M4A, WebM, dan OGG di server
- Browser modern dengan akses mikrofon untuk fitur rekam langsung

Browser yang mendukung Web Speech API akan menampilkan transkripsi langsung. Jika tidak didukung, audio rekaman tetap disimpan dan dapat dicoba ditranskripsikan oleh server. Transkripsi server memerlukan koneksi internet.

## Menjalankan aplikasi

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Buka `http://127.0.0.1:5000` di browser. Jika PowerShell membatasi aktivasi virtual environment, jalankan perintah `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` lalu `.\.venv\Scripts\python.exe app.py`.

Untuk produksi, atur variabel lingkungan `SECRET_KEY` ke nilai rahasia yang kuat. Mode debug hanya dapat diaktifkan dengan `FLASK_DEBUG=1` dan tidak boleh digunakan di server publik.

## Penyimpanan

- Database SQLite dibuat otomatis di `voice_notes.db`.
- Audio tersimpan di folder `uploads/`.
- Batas unggah audio adalah 100 MB.
- Format yang diterima: WAV, MP3, M4A, WebM, OGG, FLAC, dan AIFF.

Rekaman harus dilakukan dengan izin orang yang berbicara. Hasil pengenalan suara perlu diperiksa karena kualitas audio dan kebisingan dapat memengaruhi akurasi.
