from __future__ import annotations

import logging
from pathlib import Path

from config import Config
from repository import init_db, replace_schedule
from schedule_parser import parse_schedule_file
from services import (
    send_daily_summary,
    send_due_event_reminders,
    sync_default_holidays,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def rebuild_schedule_database() -> tuple[int, int]:
    schedule_path = Path(Config.SCHEDULE_FILE)
    if not schedule_path.exists():
        raise FileNotFoundError(
            f"Schedule file not found: {schedule_path}. "
            "Upload Schedule.xlsx through GitHub Pages first."
        )

    parsed = parse_schedule_file(
        schedule_path,
        default_start_time=Config.DAILY_NOTIFY_TIME,
    )
    logger.info("Schedule Parsed")
    event_count, task_count = replace_schedule(
        Config.DATABASE_PATH,
        parsed.events,
        parsed.tasks,
        parsed.month,
        parsed.year,
    )
    logger.info("Tasks Imported: %s", task_count)
    logger.info("Events Imported: %s", event_count)
    return task_count, event_count


def run_step(name: str, success_message: str, action) -> None:
    try:
        action()
        logger.info(success_message)
    except Exception:
        logger.exception("%s failed", name)


def main() -> None:
    logger.info("Scheduler Started")
    init_db(Config.DATABASE_PATH)
    logger.info("Database Initialized")
    rebuild_schedule_database()
    run_step("Holiday Sync", "Holiday Synced", sync_default_holidays)
    run_step("Daily Summary", "Daily Summary Sent", send_daily_summary)
    run_step("Reminder", "Reminder Sent", send_due_event_reminders)
    logger.info("Scheduler Finished")


if __name__ == "__main__":
    main()
