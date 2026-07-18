import os
from pathlib import Path


def load_dotenv_if_present() -> None:
    env_path = Path(".env")
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


load_dotenv_if_present()


class Config:
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-secret")
    DATABASE_PATH = os.getenv("DATABASE_PATH", "scheduler.sqlite3")
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")
    TIMEZONE = os.getenv("APP_TIMEZONE", "Asia/Jakarta")
    DAILY_NOTIFY_TIME = os.getenv("DAILY_NOTIFY_TIME", "04:00")
    REMINDER_LOOKAHEAD_MINUTES = int(os.getenv("REMINDER_LOOKAHEAD_MINUTES", "1"))
    DINGTALK_WEBHOOK_URL = os.getenv("DINGTALK_WEBHOOK_URL", "")
    DINGTALK_SECRET = os.getenv("DINGTALK_SECRET", "")
    HOLIDAY_FILE = os.getenv("HOLIDAY_FILE", "data/holidays_id_2026.json")
    HOLIDAY_SYNC_ENABLED = os.getenv("HOLIDAY_SYNC_ENABLED", "true").lower() == "true"
    HOLIDAY_SYNC_URL_TEMPLATE = os.getenv(
        "HOLIDAY_SYNC_URL_TEMPLATE",
        "https://api-hari-libur.vercel.app/api?year={year}",
    )
    HOLIDAY_SYNC_TIME = os.getenv("HOLIDAY_SYNC_TIME", "02:30")
