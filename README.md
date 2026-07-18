# Task DingTalk Scheduler

Aplikasi Python untuk upload file `Schedule TS` `.csv` atau `.xlsx`, menampilkan hasilnya sebagai kalender, lalu mengirim jadwal on duty otomatis ke DingTalk melalui incoming robot webhook.

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
4. Scheduler mengirim summary jadwal hari ini ke DingTalk setiap hari sesuai `DAILY_NOTIFY_TIME`.
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
HOLIDAY_SYNC_TIME=02:30
```

Aplikasi akan mencoba sync saat start, setiap hari pada `HOLIDAY_SYNC_TIME`, saat upload schedule, dan lewat tombol `Sync Libur` di dashboard. Jika sync gagal, data lokal terakhir tetap dipakai.
