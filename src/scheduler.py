from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable


def start_interval_refresh_scheduler(
    refresh_callback: Callable[[], None],
    log_path: Path,
    interval_minutes: int = 15,
    offset_minutes: int = 0,
    name: str = "interval-price-refresh",
) -> None:
    interval_minutes = max(1, int(interval_minutes))
    offset_minutes = int(offset_minutes) % interval_minutes
    thread = threading.Thread(
        target=_interval_scheduler_loop,
        args=(refresh_callback, log_path, interval_minutes, offset_minutes, name),
        daemon=True,
        name=name,
    )
    thread.start()


def start_daily_time_scheduler(
    refresh_callback: Callable[[], None],
    log_path: Path,
    run_times: list[str],
    name: str,
) -> None:
    parsed_times = {_hhmm_to_minutes(value) for value in run_times}
    thread = threading.Thread(
        target=_daily_time_scheduler_loop,
        args=(refresh_callback, log_path, parsed_times, name),
        daemon=True,
        name=name,
    )
    thread.start()


def append_refresh_log(log_path: Path, source: str, status: str, message: str = "") -> None:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    rows = _read_log(log_path)
    rows.append(
        {
            "time": datetime.now().astimezone().isoformat(timespec="seconds"),
            "source": source,
            "status": status,
            "message": message,
        }
    )
    log_path.write_text(json.dumps(rows[-100:], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _interval_scheduler_loop(
    refresh_callback: Callable[[], None],
    log_path: Path,
    interval_minutes: int,
    offset_minutes: int,
    name: str,
) -> None:
    ran_slots: set[str] = set()
    while True:
        now = datetime.now().astimezone()
        if (now.minute - offset_minutes) % interval_minutes == 0:
            slot = now.strftime("%Y-%m-%d %H:%M")
            if slot not in ran_slots:
                try:
                    refresh_callback()
                except Exception as exc:
                    append_refresh_log(log_path, name, "error", str(exc))
                ran_slots.add(slot)

        if len(ran_slots) > 128:
            today_key = now.strftime("%Y-%m-%d")
            ran_slots = {item for item in ran_slots if item.startswith(today_key)}

        time.sleep(20)


def _daily_time_scheduler_loop(
    refresh_callback: Callable[[], None],
    log_path: Path,
    run_times: set[int],
    name: str,
) -> None:
    ran_slots: set[str] = set()
    while True:
        now = datetime.now().astimezone()
        current = now.hour * 60 + now.minute
        if current in run_times:
            slot = now.strftime("%Y-%m-%d %H:%M")
            if slot not in ran_slots:
                try:
                    refresh_callback()
                except Exception as exc:
                    append_refresh_log(log_path, name, "error", str(exc))
                ran_slots.add(slot)

        if len(ran_slots) > 32:
            today_key = now.strftime("%Y-%m-%d")
            ran_slots = {item for item in ran_slots if item.startswith(today_key)}

        time.sleep(20)


def _read_log(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    try:
        data = json.loads(log_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _hhmm_to_minutes(value: str) -> int:
    hour_text, minute_text = value.split(":", 1)
    return int(hour_text) * 60 + int(minute_text)
