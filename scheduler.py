from __future__ import annotations

import logging

from config import Config
from models import init_db
from services import (
    send_daily_summary,
    send_due_event_reminders,
    sync_default_holidays,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


def main() -> None:
    logging.info("===== DingTalk Scheduler Started =====")

    init_db(Config.DATABASE_PATH)

    try:
        sync_default_holidays()
    except Exception:
        logging.exception("Holiday sync failed")

    try:
        send_daily_summary()
    except Exception:
        logging.exception("Daily summary failed")

    try:
        send_due_event_reminders()
    except Exception:
        logging.exception("Reminder failed")

    logging.info("===== Scheduler Finished =====")


if __name__ == "__main__":
    main()
