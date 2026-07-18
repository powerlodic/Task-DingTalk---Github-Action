from __future__ import annotations

import calendar
import sqlite3
from collections.abc import Iterable

from repository import (
    clear_schedule as delete_all_schedule_data,
    get_calendar_month,
    get_events as get_all_events,
    get_events_for_date,
    get_pending_events,
    init_db,
    mark_event_sent,
    replace_schedule,
)


def build_month_calendar(
    month: int,
    year: int,
    events: Iterable[sqlite3.Row],
) -> list[list[dict | None]]:
    grouped: dict[str, list[sqlite3.Row]] = {}
    for event in events:
        grouped.setdefault(event["date"], []).append(event)

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
