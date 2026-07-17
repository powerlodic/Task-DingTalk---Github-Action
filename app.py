from __future__ import annotations

from pathlib import Path

from flask import Flask, flash, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

from config import Config
from dingtalk import DingTalkClient, DingTalkConfigError
from holidays_id import holiday_label, load_holidays
from models import (
    build_month_calendar,
    delete_all_schedule_data,
    get_all_events,
    get_calendar_month,
    init_db,
    replace_schedule,
)
from schedule_parser import parse_schedule_file
from services import local_now, send_daily_summary, sync_holiday_years


app = Flask(__name__)
app.config.from_object(Config)


@app.route("/", methods=["GET"])
def dashboard():
    events = get_all_events(app.config["DATABASE_PATH"])
    holidays = load_holidays(app.config["HOLIDAY_FILE"])
    meta_month = get_calendar_month(app.config["DATABASE_PATH"])
    if meta_month:
        month, year = meta_month
    elif events:
        year, month = [int(part) for part in events[0]["date"].split("-")[:2]]
    else:
        now = local_now()
        month, year = now.month, now.year

    return render_template(
        "dashboard.html",
        events=events,
        calendar_weeks=build_month_calendar(month, year, events),
        calendar_title=f"{year}-{month:02d}",
        holidays=holidays,
        holiday_label=holiday_label,
        dingtalk_ready=bool(app.config["DINGTALK_WEBHOOK_URL"]),
        daily_time=app.config["DAILY_NOTIFY_TIME"],
    )


@app.route("/upload", methods=["POST"])
def upload_schedule():
    uploaded = request.files.get("schedule_file")
    if not uploaded or uploaded.filename == "":
        flash("Pilih file Schedule TS terlebih dahulu.", "error")
        return redirect(url_for("dashboard"))

    upload_dir = Path(app.config["UPLOAD_FOLDER"])
    upload_dir.mkdir(parents=True, exist_ok=True)
    filename = secure_filename(uploaded.filename)
    if not filename:
        flash("Nama file schedule tidak valid.", "error")
        return redirect(url_for("dashboard"))

    target = upload_dir / filename
    uploaded.save(target)

    try:
        parsed = parse_schedule_file(
            target,
            default_start_time=app.config["DAILY_NOTIFY_TIME"],
        )
    except Exception as exc:
        flash(f"Gagal membaca file schedule: {exc}", "error")
        return redirect(url_for("dashboard"))

    try:
        synced = sync_holiday_years([parsed.year])
    except Exception as exc:
        app.logger.warning("Holiday sync failed after upload: %s", exc)
        synced = 0

    replace_schedule(
        app.config["DATABASE_PATH"],
        parsed.events,
        parsed.tasks,
        parsed.month,
        parsed.year,
    )

    flash(
        f"File berhasil disync: {len(parsed.events)} jadwal, "
        f"{len(parsed.tasks)} definisi task, {synced} data libur.",
        "success",
    )
    return redirect(url_for("dashboard"))


@app.route("/send-test", methods=["POST"])
def send_test():
    try:
        client = DingTalkClient.from_app_config(app.config)
        client.send_text("Test koneksi dari Task DingTalk Scheduler berhasil.")
        flash("Pesan test berhasil dikirim ke DingTalk.", "success")
    except DingTalkConfigError as exc:
        flash(str(exc), "error")
    except Exception as exc:
        flash(f"Gagal kirim test DingTalk: {exc}", "error")
    return redirect(url_for("dashboard"))


@app.route("/send-today", methods=["POST"])
def send_today():
    try:
        send_daily_summary()
        flash("Summary jadwal hari ini diproses.", "success")
    except DingTalkConfigError as exc:
        flash(str(exc), "error")
    except Exception as exc:
        flash(f"Gagal kirim summary: {exc}", "error")
    return redirect(url_for("dashboard"))


@app.route("/sync-holidays", methods=["POST"])
def sync_holidays_now():
    try:
        meta_month = get_calendar_month(app.config["DATABASE_PATH"])
        years = (
            [meta_month[1]]
            if meta_month
            else [local_now().year, local_now().year + 1]
        )
        synced = sync_holiday_years(years)
        flash(f"Kalender libur berhasil disync: {synced} item.", "success")
    except Exception as exc:
        flash(f"Gagal sync kalender libur: {exc}", "error")
    return redirect(url_for("dashboard"))


@app.route("/reset", methods=["POST"])
def reset_schedule():
    delete_all_schedule_data(app.config["DATABASE_PATH"])
    flash("Data schedule sudah dikosongkan.", "success")
    return redirect(url_for("dashboard"))


if __name__ == "__main__":
    init_db(app.config["DATABASE_PATH"])
    app.run(host="127.0.0.1", port=5000, debug=False)
