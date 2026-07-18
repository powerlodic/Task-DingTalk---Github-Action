from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

import requests


def load_holidays(path: str) -> dict[str, list[dict]]:
    holiday_path = Path(path)
    if not holiday_path.exists():
        return {}

    data = json.loads(holiday_path.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict]] = defaultdict(list)
    for item in data:
        grouped[item["date"]].append(item)
    return dict(grouped)


def holiday_label(holidays: list[dict]) -> str:
    if not holidays:
        return ""

    national = [item["name"] for item in holidays if item.get("type") == "national"]
    collective_leave = [
        item["name"] for item in holidays if item.get("type") == "collective_leave"
    ]

    parts = []
    if national:
        parts.append(f"Libur National: {', '.join(national)}")
    if collective_leave:
        parts.append(f"Cuti Bersama: {', '.join(collective_leave)}")
    return " | ".join(parts)


def sync_holidays(
    file_path: str,
    url_template: str,
    years: list[int],
    timeout: int = 20,
) -> int:
    existing = _read_holiday_items(file_path)
    by_date_name = {
        (item["date"], item["name"]): item
        for item in existing
        if item.get("date") and item.get("name")
    }

    synced_count = 0
    for year in years:
        url = url_template.format(year=year)
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        items = _extract_remote_items(payload)
        for item in items:
            if not item["date"].startswith(f"{year}-"):
                continue
            by_date_name[(item["date"], item["name"])] = item
            synced_count += 1

    output = sorted(by_date_name.values(), key=lambda item: (item["date"], item["name"]))
    _write_holiday_items(file_path, output)
    return synced_count


def _read_holiday_items(file_path: str) -> list[dict]:
    path = Path(file_path)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _write_holiday_items(file_path: str, items: list[dict]) -> None:
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(items, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _extract_remote_items(payload) -> list[dict]:
    if isinstance(payload, dict):
        raw_items = payload.get("data", [])
    elif isinstance(payload, list):
        raw_items = payload
    else:
        raw_items = []

    items = []
    for raw in raw_items:
        date_text = raw.get("date") or raw.get("holiday_date")
        name = raw.get("description") or raw.get("name") or raw.get("holiday_name")
        if not date_text or not name:
            continue
        items.append(
            {
                "date": date_text,
                "type": "collective_leave"
                if "cuti bersama" in name.lower()
                else "national",
                "name": name,
            }
        )
    return items
