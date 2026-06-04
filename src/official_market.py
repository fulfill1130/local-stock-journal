from __future__ import annotations

import json
import ssl
import subprocess
import time
from datetime import date, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import pandas as pd
import yfinance as yf
import certifi


TWSE_STOCK_DAY_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
TPEX_TRADING_STOCK_URL = "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock"


def fetch_twse_daily_range(
    ticker: str,
    start_date: date,
    end_date: date,
    pause_seconds: float = 0.0,
) -> list[dict[str, Any]]:
    ticker = str(ticker).strip().upper()
    rows: list[dict[str, Any]] = []
    months = month_starts(start_date, end_date)
    for index, month_start in enumerate(months):
        rows.extend(fetch_twse_month(ticker, month_start))
        if pause_seconds > 0 and index < len(months) - 1:
            time.sleep(pause_seconds)
    return [
        row
        for row in rows
        if start_date.isoformat() <= row["trade_date"] <= end_date.isoformat()
    ]


def fetch_twse_name(ticker: str, month_start: date) -> str:
    query = urlencode(
        {
            "date": month_start.strftime("%Y%m01"),
            "stockNo": str(ticker).strip().upper(),
            "response": "json",
        }
    )
    payload = read_json_url(f"{TWSE_STOCK_DAY_URL}?{query}")
    return parse_twse_name(payload.get("title", ""), ticker)


def fetch_twse_month(ticker: str, month_start: date) -> list[dict[str, Any]]:
    query = urlencode(
        {
            "date": month_start.strftime("%Y%m01"),
            "stockNo": ticker,
            "response": "json",
        }
    )
    url = f"{TWSE_STOCK_DAY_URL}?{query}"
    payload = read_json_url(url)

    stat = str(payload.get("stat", "") or "")
    if stat != "OK":
        if is_no_data_status(stat):
            return []
        raise ValueError(f"TWSE 回傳非 OK：{stat or 'unknown'}")

    fetched_at_ts = time.time()
    return [
        {
            "ticker": ticker,
            "trade_date": roc_date_to_iso(raw[0]),
            "volume": parse_int(raw[1]),
            "turnover": parse_float(raw[2]),
            "open": parse_float(raw[3]),
            "high": parse_float(raw[4]),
            "low": parse_float(raw[5]),
            "close": parse_float(raw[6]),
            "transactions": parse_int(raw[8]),
            "source": "TWSE_STOCK_DAY",
            "source_market": "TWSE",
            "fetched_at_ts": fetched_at_ts,
        }
        for raw in payload.get("data", [])
    ]


def fetch_tpex_daily_range(
    ticker: str,
    start_date: date,
    end_date: date,
    pause_seconds: float = 0.0,
) -> list[dict[str, Any]]:
    ticker = str(ticker).strip().upper()
    rows: list[dict[str, Any]] = []
    months = month_starts(start_date, end_date)
    for index, month_start in enumerate(months):
        rows.extend(fetch_tpex_month(ticker, month_start))
        if pause_seconds > 0 and index < len(months) - 1:
            time.sleep(pause_seconds)
    return [
        row
        for row in rows
        if start_date.isoformat() <= row["trade_date"] <= end_date.isoformat()
    ]


def fetch_tpex_name(ticker: str, month_start: date) -> str:
    query = urlencode(
        {
            "code": str(ticker).strip().upper(),
            "date": month_start.strftime("%Y/%m/01"),
            "response": "json",
        }
    )
    payload = read_json_url(f"{TPEX_TRADING_STOCK_URL}?{query}")
    return str(payload.get("name", "") or "").strip()


def fetch_tpex_month(ticker: str, month_start: date) -> list[dict[str, Any]]:
    query = urlencode(
        {
            "code": ticker,
            "date": month_start.strftime("%Y/%m/01"),
            "response": "json",
        }
    )
    url = f"{TPEX_TRADING_STOCK_URL}?{query}"
    payload = read_json_url(url)

    stat = str(payload.get("stat", "") or "")
    if stat != "ok":
        if is_no_data_status(stat):
            return []
        raise ValueError(f"TPEx 回傳非 ok：{stat or 'unknown'}")

    tables = payload.get("tables") or []
    data = tables[0].get("data", []) if tables else []
    fetched_at_ts = time.time()
    return [
        {
            "ticker": ticker,
            "trade_date": roc_date_to_iso(raw[0]),
            # TPEx 回傳張數與仟元，資料庫統一保存股數與元。
            "volume": scale_int(raw[1], 1000),
            "turnover": scale_float(raw[2], 1000),
            "open": parse_float(raw[3]),
            "high": parse_float(raw[4]),
            "low": parse_float(raw[5]),
            "close": parse_float(raw[6]),
            "transactions": parse_int(raw[8]),
            "source": "TPEX_TRADING_STOCK",
            "source_market": "TPEX",
            "fetched_at_ts": fetched_at_ts,
        }
        for raw in data
    ]


def fetch_yfinance_daily_range(symbol: str, ticker: str, start_date: date, end_date: date) -> list[dict[str, Any]]:
    history = yf.Ticker(symbol).history(
        start=start_date.isoformat(),
        end=(end_date + timedelta(days=1)).isoformat(),
        interval="1d",
        auto_adjust=False,
        actions=False,
        timeout=30,
    )
    if history.empty:
        return []
    fetched_at_ts = time.time()
    rows = []
    for index, row in history.iterrows():
        trade_date = getattr(index, "date", lambda: index)()
        trade_date_text = trade_date.isoformat() if hasattr(trade_date, "isoformat") else str(trade_date)
        rows.append(
            {
                "ticker": str(ticker).strip().upper(),
                "trade_date": trade_date_text,
                "open": pandas_float(row.get("Open")),
                "high": pandas_float(row.get("High")),
                "low": pandas_float(row.get("Low")),
                "close": pandas_float(row.get("Close")),
                "volume": pandas_int(row.get("Volume")),
                "turnover": None,
                "transactions": None,
                "source": "YFINANCE_HISTORY",
                "source_market": "YAHOO",
                "fetched_at_ts": fetched_at_ts,
            }
        )
    return rows


def month_starts(start_date: date, end_date: date) -> list[date]:
    current = start_date.replace(day=1)
    months = []
    while current <= end_date:
        months.append(current)
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return months


def roc_date_to_iso(value: str) -> str:
    year_text, month_text, day_text = str(value).split("/")
    year = int(year_text) + 1911
    return date(year, int(month_text), int(day_text)).isoformat()


def parse_int(value: object) -> int | None:
    number = parse_float(value)
    return int(number) if number is not None else None


def scale_int(value: object, scale: int) -> int | None:
    number = parse_int(value)
    return number * scale if number is not None else None


def parse_float(value: object) -> float | None:
    text = str(value or "").strip().replace(",", "")
    if not text or text in {"--", "---"}:
        return None
    return float(text)


def scale_float(value: object, scale: float) -> float | None:
    number = parse_float(value)
    return number * scale if number is not None else None


def parse_twse_name(title: object, ticker: str) -> str:
    text = str(title or "").strip()
    ticker = str(ticker).strip().upper()
    marker = f" {ticker} "
    if marker not in text:
        return ""
    remainder = text.split(marker, 1)[1]
    return remainder.rsplit("各日成交資訊", 1)[0].strip()


def is_no_data_status(value: object) -> bool:
    text = str(value or "").strip()
    return "沒有符合條件的資料" in text or text.lower() in {"no data", "nodata"}


def pandas_float(value: object) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def pandas_int(value: object) -> int | None:
    number = pandas_float(value)
    return int(number) if number is not None else None


def read_json_url(url: str) -> dict[str, Any]:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 stock-daily-helper/1.0",
            "Accept": "application/json",
        },
    )
    ssl_context = ssl.create_default_context(cafile=certifi.where())
    try:
        with urlopen(request, timeout=30, context=ssl_context) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code not in {301, 302, 303, 307, 308}:
            raise
        return read_json_url_with_curl(url)
    except URLError as exc:
        if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
            raise
        return read_json_url_with_curl(url)


def read_json_url_with_curl(url: str) -> dict[str, Any]:
        completed = subprocess.run(
            [
                "curl.exe",
                "-fsSL",
                "-A",
                "Mozilla/5.0 stock-daily-helper/1.0",
                "-H",
                "Accept: application/json",
                url,
            ],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        return json.loads(completed.stdout)


def parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()
