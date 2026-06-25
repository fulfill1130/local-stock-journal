from __future__ import annotations

import time
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from central_store import (
    get_instruments_by_ticker,
    ohlcv_daily_stats,
    record_market_data_problem,
    rebuild_health_summary,
    upsert_ohlcv_daily,
)
from official_market import fetch_tpex_daily_range, fetch_twse_daily_range, parse_iso_date


def sync_missing_official_daily_bars(
    central_db_path: Path,
    end_date: date | None = None,
    ticker_pause_seconds: float = 0.5,
) -> dict[str, Any]:
    requested_end_date = end_date or date.today()
    end_date = latest_weekday_on_or_before(requested_end_date)
    instruments = get_instruments_by_ticker(central_db_path)
    updated: list[dict[str, Any]] = []
    no_new_rows: list[dict[str, Any]] = []
    already_current: list[str] = []
    failed: list[dict[str, str]] = []
    rows_written = 0

    ordered = sorted(instruments.items())
    for index, (ticker, instrument) in enumerate(ordered, start=1):
        stats = ohlcv_daily_stats(central_db_path, ticker)
        last_date_text = stats.get("last_date")
        start_date = (
            parse_iso_date(str(last_date_text)) + timedelta(days=1)
            if last_date_text
            else end_date
        )

        if start_date > end_date:
            already_current.append(ticker)
            continue

        if last_date_text and start_date < end_date - timedelta(days=10):
            no_new_rows.append(
                {
                    "ticker": ticker,
                    "source": "BACKFILL",
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat(),
                    "rows": 0,
                    "trade_dates": [],
                    "skip_reason": "history gap is too large for daily sync; waiting for background backfill",
                }
            )
            continue

        source = "tpex" if instrument.get("exchange_suffix") == ".TWO" else "twse"
        try:
            rows = (
                fetch_tpex_daily_range(ticker, start_date, end_date)
                if source == "tpex"
                else fetch_twse_daily_range(ticker, start_date, end_date)
            )
            written = upsert_ohlcv_daily(central_db_path, rows)
            rows_written += written
            trade_dates = sorted({str(row["trade_date"]) for row in rows})
            payload = {
                "ticker": ticker,
                "source": source.upper(),
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "rows": written,
                "trade_dates": trade_dates,
            }
            if written:
                updated.append(payload)
            else:
                no_new_rows.append(payload)
        except Exception as exc:
            error = str(exc)
            failed.append({"ticker": ticker, "error": error})
            record_market_data_problem(
                central_db_path,
                ticker,
                "broken",
                "parse_error",
                "high",
                error[:500],
                next_retry_at=(date.today() + timedelta(days=1)).isoformat(),
            )

        if ticker_pause_seconds > 0 and index < len(ordered):
            time.sleep(ticker_pause_seconds)

    rebuild_health_summary(central_db_path)
    return {
        "end_date": end_date.isoformat(),
        "requested_end_date": requested_end_date.isoformat(),
        "instrument_count": len(instruments),
        "rows_written": rows_written,
        "updated": updated,
        "no_new_rows": no_new_rows,
        "already_current": already_current,
        "failed": failed,
    }


def latest_weekday_on_or_before(value: date) -> date:
    current = value
    while current.weekday() >= 5:
        current -= timedelta(days=1)
    return current
