from __future__ import annotations

from datetime import datetime
from typing import Any


TAIPEI_TZ_NAME = "Asia/Taipei"


def now_string() -> str:
    return datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def as_float(value: Any, default: float | None = None) -> float | None:
    if value is None:
        return default
    try:
        text = str(value).strip().replace(",", "").replace("%", "")
        if not text:
            return default
        return float(text)
    except (TypeError, ValueError):
        return default


def as_int(value: Any, default: int = 0) -> int:
    number = as_float(value)
    if number is None:
        return default
    return int(number)


def yahoo_symbol(ticker: str, suffix: str | None = ".TW") -> str:
    ticker = str(ticker).strip().upper()
    suffix = ".TW" if suffix in (None, "") else str(suffix).strip().upper()
    if ticker.startswith("^") or "." in ticker:
        return ticker
    return f"{ticker}{suffix}"


def fmt_money(value: Any, decimals: int = 0) -> str:
    number = as_float(value)
    if number is None:
        return "N/A"
    return f"{number:,.{decimals}f}"


def fmt_pct(value: Any) -> str:
    number = as_float(value)
    if number is None:
        return "N/A"
    return f"{number:+.2f}%"


def pct(change: float | None, base: float | None) -> float | None:
    if change is None or base in (None, 0):
        return None
    return change / base * 100


def safe_subtract(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return a - b
