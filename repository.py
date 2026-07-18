from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path


def connect(database_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(database_path: str) -> None:
    database_dir = Path(database_path).parent
    if database_dir != Path("."):
        database_dir.mkdir(parents=True, exist_ok=True)
    with connect(database_path) as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                code TEXT PRIMARY KEY,
                description TEXT NOT NULL,
                capacity TEXT,
                duration TEXT,
                color TEXT
            );

            CREATE TABLE IF NOT EXISTS schedule_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                person TEXT NOT NULL,
                date TEXT NOT NULL,
                start_time TEXT,
                starts_at TEXT NOT NULL,
                task_code TEXT NOT NULL,
                description TEXT NOT NULL,
                raw_value TEXT NOT NULL,
                color TEXT,
                sent_at TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_schedule_date ON schedule_events(date);
            CREATE INDEX IF NOT EXISTS idx_schedule_starts_at
                ON schedule_events(starts_at);

            CREATE TABLE IF NOT EXISTS schedule_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )
        _ensure_column(conn, "tasks", "color", "TEXT")
        _ensure_column(conn, "schedule_events", "color", "TEXT")


def _ensure_column(
    conn: sqlite3.Connection,
    table: str,
    column: str,
    definition: str,
) -> None:
    columns = [
        row["name"]
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    ]
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def insert_tasks(database_path: str, tasks: dict[str, dict]) -> int:
    with connect(database_path) as conn:
        _insert_task_rows(conn, tasks)
    return len(tasks)


def insert_events(database_path: str, events: Iterable[dict]) -> int:
    event_rows = list(events)
    with connect(database_path) as conn:
        _insert_event_rows(conn, event_rows)
    return len(event_rows)


def clear_events(database_path: str) -> None:
    with connect(database_path) as conn:
        conn.execute("DELETE FROM schedule_events")
        conn.execute("DELETE FROM schedule_meta")


def clear_tasks(database_path: str) -> None:
    with connect(database_path) as conn:
        conn.execute("DELETE FROM tasks")


def replace_schedule(
    database_path: str,
    events: Iterable[dict],
    tasks: dict[str, dict],
    month: int,
    year: int,
) -> tuple[int, int]:
    init_db(database_path)
    event_rows = list(events)
    with connect(database_path) as conn:
        conn.execute("DELETE FROM schedule_events")
        conn.execute("DELETE FROM tasks")
        conn.execute("DELETE FROM schedule_meta")
        _insert_task_rows(conn, tasks)
        _insert_event_rows(conn, event_rows)
        _set_schedule_meta(conn, month, year)
    return len(event_rows), len(tasks)


def clear_schedule(database_path: str) -> None:
    init_db(database_path)
    with connect(database_path) as conn:
        conn.execute("DELETE FROM schedule_events")
        conn.execute("DELETE FROM tasks")
        conn.execute("DELETE FROM schedule_meta")


def get_events(database_path: str) -> list[sqlite3.Row]:
    init_db(database_path)
    with connect(database_path) as conn:
        return conn.execute(
            "SELECT * FROM schedule_events ORDER BY date, start_time, person, task_code"
        ).fetchall()


def get_tasks(database_path: str) -> list[sqlite3.Row]:
    init_db(database_path)
    with connect(database_path) as conn:
        return conn.execute("SELECT * FROM tasks ORDER BY code").fetchall()


def get_calendar_month(database_path: str) -> tuple[int, int] | None:
    init_db(database_path)
    with connect(database_path) as conn:
        rows = conn.execute("SELECT key, value FROM schedule_meta").fetchall()
    meta = {row["key"]: row["value"] for row in rows}
    if "month" not in meta or "year" not in meta:
        return None
    return int(meta["month"]), int(meta["year"])


def set_schedule_meta(database_path: str, month: int, year: int) -> None:
    with connect(database_path) as conn:
        _set_schedule_meta(conn, month, year)


def get_events_for_date(database_path: str, date_text: str) -> list[sqlite3.Row]:
    init_db(database_path)
    with connect(database_path) as conn:
        return conn.execute(
            """
            SELECT * FROM schedule_events
            WHERE date = ?
            ORDER BY start_time, person, task_code
            """,
            (date_text,),
        ).fetchall()


def get_pending_events(
    database_path: str,
    start_iso: str,
    end_iso: str,
) -> list[sqlite3.Row]:
    init_db(database_path)
    with connect(database_path) as conn:
        return conn.execute(
            """
            SELECT * FROM schedule_events
            WHERE sent_at IS NULL
              AND starts_at >= ?
              AND starts_at <= ?
              AND start_time IS NOT NULL
              AND lower(task_code) <> 'off'
            ORDER BY starts_at, person
            """,
            (start_iso, end_iso),
        ).fetchall()


def mark_event_sent(database_path: str, event_id: int) -> None:
    with connect(database_path) as conn:
        conn.execute(
            "UPDATE schedule_events SET sent_at = datetime('now') WHERE id = ?",
            (event_id,),
        )


def _insert_task_rows(conn: sqlite3.Connection, tasks: dict[str, dict]) -> None:
    conn.executemany(
        """
        INSERT INTO tasks (code, description, capacity, duration, color)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (
                code,
                task.get("description", ""),
                task.get("capacity", ""),
                task.get("duration", ""),
                task.get("color", ""),
            )
            for code, task in sorted(tasks.items())
        ],
    )


def _insert_event_rows(conn: sqlite3.Connection, event_rows: list[dict]) -> None:
    conn.executemany(
        """
        INSERT INTO schedule_events
            (
                person,
                date,
                start_time,
                starts_at,
                task_code,
                description,
                raw_value,
                color
            )
        VALUES
            (
                :person,
                :date,
                :start_time,
                :starts_at,
                :task_code,
                :description,
                :raw_value,
                :color
            )
        """,
        event_rows,
    )


def _set_schedule_meta(conn: sqlite3.Connection, month: int, year: int) -> None:
    conn.execute("DELETE FROM schedule_meta")
    conn.executemany(
        "INSERT INTO schedule_meta (key, value) VALUES (?, ?)",
        [("month", str(month)), ("year", str(year))],
    )
