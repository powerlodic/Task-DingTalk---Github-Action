from __future__ import annotations

import calendar
import json
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from config import Config
from schedule_parser import parse_schedule_file


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


def main() -> None:
    schedule_path = Path(os.getenv("SCHEDULE_FILE", Config.SCHEDULE_FILE))
    output_path = Path(os.getenv("CALENDAR_JSON_PATH", "docs/data/schedule.json"))

    if not schedule_path.exists():
        raise FileNotFoundError(
            f"Schedule file not found: {schedule_path}. "
            "Expected uploaded file at uploads/Schedule.xlsx."
        )

    parsed = parse_schedule_file(
        schedule_path,
        default_start_time=Config.DAILY_NOTIFY_TIME,
    )
    payload = build_calendar_payload(parsed, schedule_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Calendar JSON generated: {output_path}")
    print(f"Events: {len(parsed.events)}")
    print(f"Engineers: {len(payload['engineers'])}")


def build_calendar_payload(parsed, schedule_path: Path) -> dict:
    events = sorted(
        parsed.events,
        key=lambda event: (
            event["date"],
            event.get("start_time") or "",
            event["person"],
            event["task_code"],
        ),
    )
    engineers = sorted({event["person"] for event in events})
    tasks = [
        {"code": code, **task}
        for code, task in sorted(parsed.tasks.items())
    ]

    return {
        "generated_at": local_timestamp(),
        "source_path": schedule_path.as_posix(),
        "month": parsed.month,
        "month_name": MONTH_NAMES_ID.get(parsed.month, str(parsed.month)),
        "year": parsed.year,
        "engineers": engineers,
        "tasks": tasks,
        "events": events,
        "stats": {
            "total_engineers": len(engineers),
            "total_events": len(events),
            "total_tasks": len(tasks),
        },
        "calendar": {
            "weeks": build_calendar_weeks(parsed.month, parsed.year, events),
        },
    }


def build_calendar_weeks(month: int, year: int, events: list[dict]) -> list[list[dict | None]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for event in events:
        grouped[event["date"]].append(event)

    weeks = []
    for week in calendar.Calendar(firstweekday=0).monthdatescalendar(year, month):
        weeks.append(
            [
                None
                if day.month != month
                else {
                    "date": day.isoformat(),
                    "day": day.day,
                    "events": grouped.get(day.isoformat(), []),
                }
                for day in week
            ]
        )
    return weeks


def local_timestamp() -> str:
    timezone = ZoneInfo(Config.TIMEZONE)
    return datetime.now(timezone).isoformat(timespec="seconds")


if __name__ == "__main__":
    main()
