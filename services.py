from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timedelta
from sqlite3 import Row

import pytz

from config import Config
from dingtalk import DingTalkClient
from holidays_id import holiday_label, load_holidays, sync_holidays
from models import get_events_for_date, get_pending_events, mark_event_sent


logger = logging.getLogger(__name__)
timezone = pytz.timezone(Config.TIMEZONE)

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

TASK_MESSAGE_LINES = {
    "Task 1": [
        "Monitoring CAMUNDA (Daily Recon, Incident )",
        "External dan Internal Request (WAG, DING dan Email)",
        "Reporting Regulator (Awal Bulan)",
        "User Request Email: \n "
        "\u2022 Penomoran DACOR \n "
        "\u2022 Penomoran BISREQ \n "
        "\u2022 Penomoran User Access \n "
        "\u2022 Circulate digital sign, dll",
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


def local_now() -> datetime:
    return datetime.now(timezone)


def format_date_id(date_text: str) -> str:
    value = datetime.strptime(date_text, "%Y-%m-%d").date()
    return (
        f"{DAY_NAMES_ID[value.weekday()]}, "
        f"{value.day} {MONTH_NAMES_ID[value.month]} {value.year}"
    )


def get_holiday_label(date_text: str) -> str:
    holidays = load_holidays(Config.HOLIDAY_FILE)
    return holiday_label(holidays.get(date_text, []))


def sync_holiday_years(years: list[int]) -> int:
    if not Config.HOLIDAY_SYNC_ENABLED:
        return 0
    return sync_holidays(
        Config.HOLIDAY_FILE,
        Config.HOLIDAY_SYNC_URL_TEMPLATE,
        years,
    )


def sync_default_holidays() -> None:
    now = local_now()
    try:
        sync_holiday_years([now.year, now.year + 1])
    except Exception:
        logger.exception("Holiday sync failed")


def task_sort_key(task_code: str) -> tuple[int, int, str]:
    match = re.search(r"\btask\s*(\d+)\b", task_code, re.IGNORECASE)
    if match:
        return (0, int(match.group(1)), task_code)
    if task_code.lower() == "duty":
        return (1, 0, task_code)
    return (2, 0, task_code)


def short_person_name(full_name: str) -> str:
    return full_name.split()[0] if full_name else full_name


def event_task_lines(event: Row) -> list[str]:
    if event["task_code"] in TASK_MESSAGE_LINES:
        return TASK_MESSAGE_LINES[event["task_code"]]
    return [event["description"]]


def is_off_event(event: Row) -> bool:
    return event["task_code"].lower() == "off"


def is_duty_event(event: Row) -> bool:
    return event["task_code"].lower() == "duty"


def format_send_at() -> str:
    return local_now().strftime("%d/%m/%Y %H:%M:%S WIB")


def build_on_duty_message(date_text: str, events: list[Row]) -> tuple[str, str]:
    title = "Info yg bikin puyeng:"
    active_events = [event for event in events if not is_off_event(event)]
    pic_names = ", ".join(short_person_name(event["person"]) for event in active_events)
    holiday_text = get_holiday_label(date_text)
    lines = [
        f"### {title}",
        f"Hari ini ({format_date_id(date_text)})",
    ]
    if holiday_text:
        lines.append(holiday_text)
    lines.extend(
        [
            "",
            "---",
            "",
            "**On Duty**  ",
            f"PIC: {pic_names}",
        ]
    )

    lines.extend(
        [
            "",
            "---",
            f"_send at {format_send_at()}_",
        ]
    )
    return title, "\n".join(lines)


def format_pic_names(events: list[Row]) -> str:
    return ", ".join(short_person_name(event["person"]) for event in events)


def person_sort_key(item: tuple[str, list[Row]]) -> tuple[int, int, str]:
    person, person_events = item
    first_task_key = min(task_sort_key(event["task_code"]) for event in person_events)
    return (*first_task_key[:2], short_person_name(person))


def build_daily_summary_message(date_text: str, events: list[Row]) -> tuple[str, str]:
    active_events = [event for event in events if not is_off_event(event)]
    off_events = [event for event in events if is_off_event(event)]

    if active_events and all(is_duty_event(event) for event in active_events):
        return build_on_duty_message(date_text, events)

    title = "Info yg bikin puyeng:"
    holiday_text = get_holiday_label(date_text)
    grouped: dict[str, list[Row]] = defaultdict(list)
    for event in active_events:
        grouped[event["person"]].append(event)

    lines = [
        f"### {title}",
        f"Hari ini ({format_date_id(date_text)})",
    ]
    if holiday_text:
        lines.append(holiday_text)
    lines.extend(["", "---", "", "**Daily Task**  "])

    for index, (person, person_events) in enumerate(
        sorted(grouped.items(), key=person_sort_key)
    ):
        person_events = sorted(
            person_events,
            key=lambda event: task_sort_key(event["task_code"]),
        )
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
    events = get_events_for_date(Config.DATABASE_PATH, today)
    if not events:
        return

    client = DingTalkClient.from_app_config(_dingtalk_config())
    title, message = build_daily_summary_message(today, events)
    client.send_markdown(title, message)


def send_due_event_reminders() -> None:
    now = local_now()
    until = now + timedelta(minutes=Config.REMINDER_LOOKAHEAD_MINUTES)
    events = get_pending_events(
        Config.DATABASE_PATH,
        now.isoformat(timespec="minutes"),
        until.isoformat(timespec="minutes"),
    )
    if not events:
        return

    client = DingTalkClient.from_app_config(_dingtalk_config())
    for event in events:
        title = f"On Duty: {event['person']}"
        message = "\n".join(
            [
                f"### {title}",
                "",
                f"- Tanggal: {event['date']}",
                f"- Jam: {event['start_time'] or Config.DAILY_NOTIFY_TIME}",
                f"- Task: {event['task_code']}",
                f"- Detail: {event['description']}",
            ]
        )
        client.send_markdown(title, message)
        mark_event_sent(Config.DATABASE_PATH, event["id"])


def _dingtalk_config() -> dict[str, str]:
    return {
        "DINGTALK_WEBHOOK_URL": Config.DINGTALK_WEBHOOK_URL,
        "DINGTALK_SECRET": Config.DINGTALK_SECRET,
    }
