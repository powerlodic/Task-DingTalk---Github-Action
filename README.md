# Task DingTalk

Aplikasi Python untuk upload file `Schedule TS` `.csv` atau `.xlsx`, menampilkan hasilnya sebagai kalender, lalu mengirim jadwal on duty ke DingTalk melalui incoming robot webhook.

Proyek ini punya dua entry point:

- `app.py` menjalankan dashboard Flask lokal.
- `scheduler.py` dijalankan GitHub Actions untuk sync libur dan mengirim notifikasi.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
```

Edit `.env` dan isi `DINGTALK_WEBHOOK_URL`. Jika robot DingTalk memakai signature, isi juga `DINGTALK_SECRET`.

## Run

```powershell
python app.py
```

Buka dashboard:

```text
http://127.0.0.1:5000
```

## Alur

1. Upload file `Schedule TS`.
2. Aplikasi parse blok mingguan, nama engineer, tanggal, dan isi cell task. Untuk `.xlsx`, warna cell jadwal otomatis dicocokkan dengan warna legenda task.
3. Kalender dashboard otomatis sama dengan isi file.
4. GitHub Actions menjalankan `python scheduler.py` pada hari kerja untuk mengirim summary jadwal hari ini ke DingTalk.
5. Event yang punya jam eksplisit, misalnya `Task 1 13:30`, juga akan dikirim saat waktunya mendekat.
6. Kalender libur nasional/cuti bersama dibaca dari `HOLIDAY_FILE` dan ditampilkan di dashboard serta pesan DingTalk.

## Format yang Dibaca

Grid jadwal dibaca dari baris `No,Nama,...` dan baris tanggal setelahnya. Isi sel tanggal pada CSV bisa berupa:

```text
Task 1
Task 2
Duty
Off
Task 1, Duty
Task 2 13:30
```

Definisi task di bagian bawah seperti `Task 1,"Monitoring ..."` otomatis dipakai sebagai deskripsi.

Untuk XLSX, definisi task di bagian bawah juga dipakai sebagai legenda warna. Contohnya jika `Task 1` berwarna hijau, semua cell jadwal dengan warna hijau akan dibuat sebagai event `Task 1`.

## Kalender Libur

Data awal libur nasional dan cuti bersama 2026 ada di:

```text
data/holidays_id_2026.json
```

Jika ada perubahan keputusan pemerintah, update file JSON tersebut atau arahkan `.env` `HOLIDAY_FILE` ke file baru.

Auto-sync libur bisa dikontrol dari `.env`:

```text
HOLIDAY_SYNC_ENABLED=true
HOLIDAY_SYNC_URL_TEMPLATE=https://api-hari-libur.vercel.app/api?year={year}
```

Aplikasi akan mencoba sync saat `scheduler.py` dijalankan GitHub Actions, saat upload schedule, dan lewat tombol `Sync Libur` di dashboard. Jika sync gagal, data lokal terakhir tetap dipakai.

## GitHub Actions

Workflow ada di `.github/workflows/dingtalk.yml`.

Tambahkan repository secrets:

```text
DINGTALK_WEBHOOK_URL
DINGTALK_SECRET
```

`DINGTALK_SECRET` boleh kosong jika robot DingTalk tidak memakai signature. Workflow bisa dijalankan manual lewat `workflow_dispatch`.
