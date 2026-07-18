from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
import re

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from flask import Flask, flash, redirect, render_template, request, url_for

from config import Config
from dingtalk import DingTalkClient, DingTalkConfigError
from holidays_id import holiday_label, load_holidays, sync_holidays
from models import (
    build_month_calendar,
    delete_all_schedule_data,
    get_all_events,
    get_calendar_month,
    get_events_for_date,
    get_pending_events,
    init_db,
    mark_event_sent,
    replace_schedule,
)
from schedule_parser import parse_schedule_file


app = Flask(__name__)
app.config.from_object(Config)

timezone = pytz.timezone(app.config["TIMEZONE"])
scheduler = BackgroundScheduler(timezone=timezone)

DAY_NAMES_ID = {
    0: "Senin",
    1: "Selasa",
    2: "Rabu",
    3: "Kamis",
    4: "Jumat",
    5: "Sabtu",
    6: "Minggu",
}

MONTH_NAMES_ID = {
    1: "Januari",
    2: "Februari",
    3: "Maret",
    4: "April",
    5: "Mei",
    6: "Juni",
    7: "Juli",
    8: "Agustus",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Desember",
}


def local_now() -> datetime:
    return datetime.now(timezone)


def format_date_id(date_text: str) -> str:
    value = datetime.strptime(date_text, "%Y-%m-%d").date()
    return f"{DAY_NAMES_ID[value.weekday()]}, {value.day} {MONTH_NAMES_ID[value.month]} {value.year}"


def get_holiday_label(date_text: str) -> str:
    holidays = load_holidays(app.config["HOLIDAY_FILE"])
    return holiday_label(holidays.get(date_text, []))


def sync_holiday_years(years: list[int]) -> int:
    if not app.config["HOLIDAY_SYNC_ENABLED"]:
        return 0
    return sync_holidays(
        app.config["HOLIDAY_FILE"],
        app.config["HOLIDAY_SYNC_URL_TEMPLATE"],
        years,
    )


def sync_default_holidays() -> None:
    now = local_now()
    try:
        sync_holiday_years([now.year, now.year + 1])
    except Exception as exc:
        app.logger.warning("Holiday sync failed: %s", exc)


def task_sort_key(task_code: str) -> tuple[int, int, str]:
    match = re.search(r"\btask\s*(\d+)\b", task_code, re.IGNORECASE)
    if match:
        return (0, int(match.group(1)), task_code)
    if task_code.lower() == "duty":
        return (1, 0, task_code)
    return (2, 0, task_code)


TASK_MESSAGE_LINES = {
    "Task 1": [
        "Monitoring CAMUNDA (Daily Recon, Incident )",
        "External dan Internal Request (WAG, DING dan Email)",
        "Reporting Regulator (Awal Bulan)",
        "User Request Email: \n • Penomoran DACOR \n • Penomoran BISREQ \n • Penomoran User Access \n • Circulate digital sign, dll",
    ],
    "Task 2": [
        "Monitoring Dashboard (Channeling, Traffic, Issue)",
        "Grafana + Kibana Alert",
    ],
    "Task 3": [
        "JIRA (Creation dan Follow Up)",
    ],
    "Duty": [
        "Monitoring Payment, Repayment & MDR",
    ],
}


def short_person_name(full_name: str) -> str:
    return full_name.split()[0] if full_name else full_name


def event_task_lines(event) -> list[str]:
    if event["task_code"] in TASK_MESSAGE_LINES:
        return TASK_MESSAGE_LINES[event["task_code"]]
    return [event["description"]]


def format_send_at() -> str:
    return local_now().strftime("%d/%m/%Y %H:%M:%S WIB")


def build_on_duty_message(date_text: str, events: list) -> tuple[str, str]:
    title = "Info yg bikin puyeng:"
    active_events = [event for event in events if event["task_code"].lower() != "off"]
    pic_names = ", ".join(short_person_name(event["person"]) for event in active_events)
    holiday_text = get_holiday_label(date_text)
    lines = [
        f"### {title}",
        f"Hari ini ({format_date_id(date_text)})",
    ]
    if holiday_text:
        lines.append(holiday_text)
    lines.extend([
        "",
        "---",
        "",
        "**On Duty**  ",
        f"PIC: {pic_names}",
    ])

    lines.extend([
        "",
        "---",
        f"_send at {format_send_at()}_",
    ])
    return title, "\n".join(lines)


def format_pic_names(events: list) -> str:
    return ", ".join(short_person_name(event["person"]) for event in events)


def person_sort_key(item) -> tuple[int, int, str]:
    person, person_events = item
    first_task_key = min(task_sort_key(event["task_code"]) for event in person_events)
    return (*first_task_key[:2], short_person_name(person))


def build_daily_summary_message(date_text: str, events: list) -> tuple[str, str]:
    active_events = [event for event in events if event["task_code"].lower() != "off"]
    off_events = [event for event in events if event["task_code"].lower() == "off"]

    if active_events and all(event["task_code"].lower() == "duty" for event in active_events):
        return build_on_duty_message(date_text, events)

    title = "Info yg bikin puyeng:"
    holiday_text = get_holiday_label(date_text)
    grouped = defaultdict(list)
    for event in active_events:
        grouped[event["person"]].append(event)

    lines = [
        f"### {title}",
        f"Hari ini ({format_date_id(date_text)})",
    ]
    if holiday_text:
        lines.append(holiday_text)
    lines.extend(["", "---", "", "**Daily Task**  "])

    for index, (person, person_events) in enumerate(sorted(grouped.items(), key=person_sort_key)):
        person_events = sorted(grouped[person], key=lambda event: task_sort_key(event["task_code"]))
        if index > 0:
            lines.append("")
        lines.append(f"{short_person_name(person)}:  ")

        number = 1
        for event in person_events:
            for task_line in event_task_lines(event):
                lines.append(f"{number}. {task_line}")
                number += 1

    if off_events:
        lines.extend(["", "**Off Duty**  ", f"PIC: {format_pic_names(off_events)}"])

    lines.extend(
        [
            "",
            "---",
            f"_send at {format_send_at()}_",
        ]
    )
    return title, "\n".join(lines)


def send_daily_summary() -> None:
    today = local_now().date().isoformat()
    events = get_events_for_date(app.config["DATABASE_PATH"], today)
    if not events:
        return

    client = DingTalkClient.from_app_config(app.config)
    title, message = build_daily_summary_message(today, events)
    client.send_markdown(title, message)


def send_due_event_reminders() -> None:
    now = local_now()
    until = now + timedelta(minutes=app.config["REMINDER_LOOKAHEAD_MINUTES"])
    events = get_pending_events(
        app.config["DATABASE_PATH"],
        now.isoformat(timespec="minutes"),
        until.isoformat(timespec="minutes"),
    )
    if not events:
        return

    client = DingTalkClient.from_app_config(app.config)
    for event in events:
        title = f"On Duty: {event['person']}"
        message = "\n".join(
            [
                f"### {title}",
                "",
                f"- Tanggal: {event['date']}",
                f"- Jam: {event['start_time'] or app.config['DAILY_NOTIFY_TIME']}",
                f"- Task: {event['task_code']}",
                f"- Detail: {event['description']}",
            ]
        )
        client.send_markdown(title, message)
        mark_event_sent(app.config["DATABASE_PATH"], event["id"])


def configure_scheduler() -> None:
    hour, minute = app.config["DAILY_NOTIFY_TIME"].split(":", 1)
    sync_hour, sync_minute = app.config["HOLIDAY_SYNC_TIME"].split(":", 1)
    scheduler.add_job(
        send_daily_summary,
        CronTrigger(hour=int(hour), minute=int(minute), timezone=timezone),
        id="daily-summary",
        replace_existing=True,
    )
    scheduler.add_job(
        send_due_event_reminders,
        "interval",
        minutes=1,
        id="due-event-reminders",
        replace_existing=True,
    )
    scheduler.add_job(
        sync_default_holidays,
        CronTrigger(hour=int(sync_hour), minute=int(sync_minute), timezone=timezone),
        id="holiday-sync",
        replace_existing=True,
    )
    scheduler.start()


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
    target = upload_dir / uploaded.filename
    uploaded.save(target)

    try:
        parsed = parse_schedule_file(target, default_start_time=app.config["DAILY_NOTIFY_TIME"])
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
        f"File berhasil disync: {len(parsed.events)} jadwal, {len(parsed.tasks)} definisi task, {synced} data libur.",
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
        years = [meta_month[1]] if meta_month else [local_now().year, local_now().year + 1]
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
    configure_scheduler()
    scheduler.add_job(sync_default_holidays, id="holiday-sync-on-start", replace_existing=True)
    app.run(host="127.0.0.1", port=5000, debug=False)
