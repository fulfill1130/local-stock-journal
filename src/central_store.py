from __future__ import annotations

import json
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from utils import pct, safe_subtract, yahoo_symbol


SEGMENT_FILES = {
    "etf": "etf.sqlite",
    "twse": "twse.sqlite",
    "tpex": "tpex.sqlite",
}


def ensure_central_db(path: Path) -> None:
    if _is_legacy_file(path):
        _ensure_database_file(path)
        return
    path.mkdir(parents=True, exist_ok=True)
    for db_path in segment_db_paths(path).values():
        _ensure_database_file(db_path)


def segment_db_paths(path: Path) -> dict[str, Path]:
    if _is_legacy_file(path):
        return {"legacy": path}
    return {segment: path / filename for segment, filename in SEGMENT_FILES.items()}


def begin_update_status(
    path: Path,
    job_name: str,
    source: str,
    started_at: str,
    next_run_at: str = "",
    message: str = "",
) -> None:
    ensure_central_db(path)
    for db_path in segment_db_paths(path).values():
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO update_status (
                    job_name,
                    source,
                    last_started_at,
                    last_finished_at,
                    next_run_at,
                    last_status,
                    success_count,
                    fail_count,
                    message
                )
                VALUES (?, ?, ?, '', ?, 'running', 0, 0, ?)
                ON CONFLICT(job_name) DO UPDATE SET
                    source = excluded.source,
                    last_started_at = excluded.last_started_at,
                    next_run_at = excluded.next_run_at,
                    last_status = excluded.last_status,
                    message = excluded.message
                """,
                (job_name, source, started_at, next_run_at, message),
            )


def finish_update_status(
    path: Path,
    job_name: str,
    source: str,
    started_at: str,
    finished_at: str,
    next_run_at: str = "",
    status: str = "success",
    message: str = "",
) -> None:
    ensure_central_db(path)
    normalized_status = "success" if status == "success" else "failed"
    success_delta = 1 if normalized_status == "success" else 0
    fail_delta = 1 if normalized_status == "failed" else 0
    for db_path in segment_db_paths(path).values():
        with sqlite3.connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO update_status (
                    job_name,
                    source,
                    last_started_at,
                    last_finished_at,
                    next_run_at,
                    last_status,
                    success_count,
                    fail_count,
                    message
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(job_name) DO UPDATE SET
                    source = excluded.source,
                    last_started_at = excluded.last_started_at,
                    last_finished_at = excluded.last_finished_at,
                    next_run_at = excluded.next_run_at,
                    last_status = excluded.last_status,
                    success_count = update_status.success_count + ?,
                    fail_count = update_status.fail_count + ?,
                    message = excluded.message
                """,
                (
                    job_name,
                    source,
                    started_at,
                    finished_at,
                    next_run_at,
                    normalized_status,
                    success_delta,
                    fail_delta,
                    message,
                    success_delta,
                    fail_delta,
                ),
            )


def list_update_status(path: Path) -> list[dict[str, Any]]:
    ensure_central_db(path)
    by_job: dict[str, dict[str, Any]] = {}
    for segment, db_path in segment_db_paths(path).items():
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = [dict(row) for row in conn.execute("SELECT * FROM update_status").fetchall()]
        for row in rows:
            row["segment"] = segment
            existing = by_job.get(row["job_name"])
            if existing is None or str(row.get("last_started_at") or "") > str(existing.get("last_started_at") or ""):
                by_job[row["job_name"]] = row
    return sorted(by_job.values(), key=lambda row: str(row.get("job_name", "")))


def cleanup_market_data(path: Path, today: date | None = None) -> list[dict[str, Any]]:
    ensure_central_db(path)
    today = today or date.today()
    daily_cutoff = _retention_daily_cutoff(today)
    intraday_cutoff = today - timedelta(days=6)
    results: list[dict[str, Any]] = []
    for segment, db_path in segment_db_paths(path).items():
        with sqlite3.connect(db_path) as conn:
            for table, column, cutoff in (
                ("ohlcv_daily", "trade_date", daily_cutoff.isoformat()),
                ("quote_snapshots_15m", "trade_date", intraday_cutoff.isoformat()),
                ("ohlcv_intraday_15m", "trade_date", intraday_cutoff.isoformat()),
            ):
                cursor = conn.execute(f"DELETE FROM {table} WHERE {column} < ?", (cutoff,))
                results.append(
                    {
                        "segment": segment,
                        "database": str(db_path),
                        "table": table,
                        "cutoff": cutoff,
                        "deleted": cursor.rowcount if cursor.rowcount is not None else 0,
                    }
                )
    return results


def migrate_legacy_central_db(legacy_path: Path, segmented_root: Path) -> dict[str, int]:
    ensure_central_db(segmented_root)
    marker = segmented_root / ".migrated_from_central_v1"
    if marker.exists():
        return {"instruments": 0, "bars": 0}
    if not legacy_path.exists():
        return {"instruments": 0, "bars": 0}

    with sqlite3.connect(legacy_path) as conn:
        conn.row_factory = sqlite3.Row
        instruments = [dict(row) for row in conn.execute("SELECT * FROM instruments").fetchall()]
        bars = [dict(row) for row in conn.execute("SELECT * FROM ohlcv_daily").fetchall()]

    for instrument in instruments:
        set_instrument(
            segmented_root,
            ticker=instrument["ticker"],
            name=instrument["name"],
            asset_type=instrument["type"],
            exchange_suffix=instrument["exchange_suffix"],
            source=instrument["source"],
        )

    bars_by_ticker: dict[str, list[dict[str, Any]]] = {}
    for row in bars:
        bars_by_ticker.setdefault(str(row["ticker"]).upper(), []).append(row)
    for ticker, rows in bars_by_ticker.items():
        upsert_ohlcv_daily(segmented_root, rows)

    marker.write_text(
        json.dumps(
            {
                "source": str(legacy_path),
                "instruments": len(instruments),
                "bars": len(bars),
                "migrated_at_ts": time.time(),
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    return {"instruments": len(instruments), "bars": len(bars)}


def seed_instruments_from_state(path: Path, state: dict[str, Any]) -> None:
    for item in state.get("holdings", []) + state.get("watchlist", []):
        register_instrument(
            path,
            ticker=str(item.get("ticker", "")),
            name=str(item.get("name", "") or ""),
            asset_type=str(item.get("type", "") or ""),
            exchange_suffix=str(item.get("exchange_suffix", "") or ".TW"),
            source="profile",
        )


def register_instrument(
    path: Path,
    ticker: str,
    name: str = "",
    asset_type: str = "",
    exchange_suffix: str = ".TW",
    source: str = "profile",
) -> dict[str, Any]:
    ticker = str(ticker).strip().upper()
    if not ticker:
        return {}
    exchange_suffix = ".TW" if exchange_suffix in ("", None) else str(exchange_suffix).strip().upper()
    inferred_type = infer_asset_type(ticker)
    incoming = {
        "ticker": ticker,
        "symbol": yahoo_symbol(ticker, exchange_suffix),
        "name": clean_name(name, ticker),
        "type": str(asset_type or inferred_type).strip().upper(),
        "exchange_suffix": exchange_suffix,
        "source": source,
        "listing_date": "",
        "history_status": "",
        "history_checked_at": "",
        "updated_at_ts": time.time(),
    }
    existing = get_instrument(path, ticker)
    row = merge_instrument(existing, incoming) if existing else incoming
    return _upsert_instrument(path, row)


def get_instruments_by_ticker(path: Path) -> dict[str, dict[str, Any]]:
    ensure_central_db(path)
    rows: dict[str, dict[str, Any]] = {}
    for segment, db_path in segment_db_paths(path).items():
        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                records = conn.execute("SELECT * FROM instruments").fetchall()
        except sqlite3.DatabaseError:
            continue
        for record in records:
            row = dict(record)
            row["segment"] = segment_for_instrument(row["type"], row["exchange_suffix"])
            rows[str(row["ticker"]).upper()] = row
    return rows


def get_instrument(path: Path, ticker: str) -> dict[str, Any] | None:
    ensure_central_db(path)
    ticker = str(ticker).strip().upper()
    for segment, db_path in segment_db_paths(path).items():
        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT * FROM instruments WHERE ticker = ?", (ticker,)).fetchone()
        except sqlite3.DatabaseError:
            continue
        if row:
            result = dict(row)
            result["segment"] = segment_for_instrument(result["type"], result["exchange_suffix"])
            return result
    return None


def set_instrument(
    path: Path,
    ticker: str,
    name: str,
    asset_type: str,
    exchange_suffix: str,
    source: str = "manual",
    listing_date: str = "",
) -> dict[str, Any]:
    ticker = str(ticker or "").strip().upper()
    if not ticker:
        raise ValueError("ticker is required")

    exchange_suffix = str(exchange_suffix or ".TW").strip().upper()
    if exchange_suffix not in {".TW", ".TWO"}:
        raise ValueError("exchange_suffix must be .TW or .TWO")

    asset_type = str(asset_type or infer_asset_type(ticker)).strip().upper()
    if asset_type not in {"ETF", "STOCK"}:
        raise ValueError("type must be ETF or STOCK")

    row = {
        "ticker": ticker,
        "symbol": yahoo_symbol(ticker, exchange_suffix),
        "name": clean_name(name, ticker),
        "type": asset_type,
        "exchange_suffix": exchange_suffix,
        "source": source,
        "listing_date": str(listing_date or "").strip(),
        "history_status": "",
        "history_checked_at": "",
        "updated_at_ts": time.time(),
    }
    return _upsert_instrument(path, row)


def list_instruments(path: Path, quote_cache: dict[str, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    ensure_central_db(path)
    quote_cache = quote_cache or {}
    rows: list[dict[str, Any]] = []
    for segment, db_path in segment_db_paths(path).items():
        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                records = conn.execute(
                    """
                    SELECT
                        i.ticker,
                        i.symbol,
                        i.name,
                        i.type,
                        i.exchange_suffix,
                        i.source,
                        i.listing_date,
                        i.history_status,
                        i.history_checked_at,
                        i.updated_at_ts,
                        o.daily_bar_count,
                        o.daily_first_date,
                        o.daily_last_date
                    FROM instruments i
                    LEFT JOIN (
                        SELECT
                            ticker,
                            COUNT(*) AS daily_bar_count,
                            MIN(trade_date) AS daily_first_date,
                            MAX(trade_date) AS daily_last_date
                        FROM ohlcv_daily
                        GROUP BY ticker
                    ) o ON o.ticker = i.ticker
                    ORDER BY i.ticker
                    """
                ).fetchall()
        except sqlite3.DatabaseError:
            continue

        for record in records:
            row = dict(record)
            row["segment"] = segment_for_instrument(row["type"], row["exchange_suffix"])
            quote = latest_daily_quote(path, row["ticker"]) or quote_cache.get(row["symbol"], {})
            row["close"] = quote.get("close")
            row["prev_close"] = quote.get("prev_close")
            row["change"] = quote.get("change")
            row["change_pct"] = quote.get("change_pct")
            row["price_time"] = quote.get("price_time", "")
            row["quote_source"] = quote.get("source", "")
            row["quote_status"] = quote.get("status", "")
            row["quote_error"] = quote.get("error", "")
            rows.append(row)
    return sorted(rows, key=lambda row: str(row["ticker"]))


def apply_daily_quote_fallbacks(
    path: Path,
    quotes: dict[str, dict[str, Any]],
    tickers: Iterable[str],
    force_tickers: Iterable[str] | None = None,
) -> dict[str, dict[str, Any]]:
    patched = dict(quotes)
    forced = {str(value).strip().upper() for value in (force_tickers or []) if value}
    for ticker in {str(value).strip().upper() for value in tickers if value}:
        instrument = get_instrument(path, ticker)
        if not instrument:
            continue
        symbol = instrument["symbol"]
        current = patched.get(symbol, {})
        if current.get("close") is not None and ticker not in forced:
            continue
        fallback = latest_daily_quote(path, ticker)
        if fallback:
            patched[symbol] = fallback
    return patched


def latest_daily_quote(path: Path, ticker: str) -> dict[str, Any] | None:
    rows = list_ohlcv_daily(path, ticker, limit=2)
    valid_rows = [row for row in rows if row.get("close") is not None]
    if not valid_rows:
        return None
    latest = valid_rows[0]
    previous = valid_rows[1] if len(valid_rows) > 1 else None
    close = latest.get("close")
    prev_close = previous.get("close") if previous else None
    change = safe_subtract(close, prev_close)
    instrument = get_instrument(path, ticker)
    return {
        "symbol": instrument["symbol"] if instrument else str(ticker).strip().upper(),
        "close": close,
        "prev_close": prev_close,
        "change": change,
        "change_pct": pct(change, prev_close),
        "price_time": latest.get("trade_date", ""),
        "fetched_at_ts": latest.get("fetched_at_ts", 0),
        "fetched_at": latest.get("trade_date", ""),
        "source": "official_daily_fallback",
        "source_market": latest.get("source_market", ""),
        "status": "historical-fallback",
        "error": "quote cache missing; using latest official daily close",
    }


def enrich_items_with_instruments(path: Path, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    instruments = get_instruments_by_ticker(path)
    enriched = []
    for item in items:
        ticker = str(item.get("ticker", "")).strip().upper()
        if ticker:
            instrument = instruments.get(ticker) or register_instrument(
                path,
                ticker=ticker,
                name=str(item.get("name", "") or ""),
                asset_type=str(item.get("type", "") or ""),
                exchange_suffix=str(item.get("exchange_suffix", "") or ".TW"),
                source="profile",
            )
        else:
            instrument = {}

        canonical = dict(item)
        if instrument:
            canonical["ticker"] = instrument["ticker"]
            canonical["name"] = instrument["name"]
            canonical["type"] = instrument["type"]
            canonical["exchange_suffix"] = instrument["exchange_suffix"]
            canonical["symbol"] = instrument["symbol"]
            canonical["segment"] = instrument["segment"]
        enriched.append(canonical)
    return enriched


def load_quote_cache(path: Path) -> dict[str, dict[str, Any]]:
    if path.suffix.lower() in {".sqlite", ".db"}:
        ensure_central_db(path)
        with sqlite3.connect(path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("SELECT symbol, quote_json FROM quotes").fetchall()
        cache: dict[str, dict[str, Any]] = {}
        for row in rows:
            try:
                cache[row["symbol"]] = json.loads(row["quote_json"])
            except json.JSONDecodeError:
                continue
        return cache

    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def save_quote_cache(path: Path, cache: dict[str, dict[str, Any]]) -> None:
    if path.suffix.lower() in {".sqlite", ".db"}:
        ensure_central_db(path)
        now = time.time()
        with sqlite3.connect(path) as conn:
            for symbol, quote in cache.items():
                fetched_at_ts = float(quote.get("fetched_at_ts", 0) or 0)
                conn.execute(
                    """
                    INSERT INTO quotes (symbol, quote_json, fetched_at_ts, updated_at_ts)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(symbol) DO UPDATE SET
                        quote_json = excluded.quote_json,
                        fetched_at_ts = excluded.fetched_at_ts,
                        updated_at_ts = excluded.updated_at_ts
                    """,
                    (
                        symbol,
                        json.dumps(quote, ensure_ascii=False),
                        fetched_at_ts,
                        now,
                    ),
                )
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def upsert_ohlcv_daily(path: Path, rows: list[dict[str, Any]]) -> int:
    ensure_central_db(path)
    if not rows:
        return 0
    now = time.time()
    rows_by_path: dict[Path, list[dict[str, Any]]] = {}
    for row in rows:
        db_path = _db_path_for_ticker(path, str(row["ticker"]).upper(), row.get("source_market"))
        rows_by_path.setdefault(db_path, []).append(row)

    for db_path, batch in rows_by_path.items():
        with sqlite3.connect(db_path) as conn:
            conn.executemany(
                """
                INSERT INTO ohlcv_daily (
                    ticker,
                    trade_date,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    turnover,
                    transactions,
                    source,
                    source_market,
                    fetched_at_ts
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, trade_date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    turnover = excluded.turnover,
                    transactions = excluded.transactions,
                    source = excluded.source,
                    source_market = excluded.source_market,
                    fetched_at_ts = excluded.fetched_at_ts
                """,
                [
                    (
                        row["ticker"],
                        row["trade_date"],
                        row.get("open"),
                        row.get("high"),
                        row.get("low"),
                        row.get("close"),
                        row.get("volume"),
                        row.get("turnover"),
                        row.get("transactions"),
                        row.get("source", ""),
                        row.get("source_market", ""),
                        row.get("fetched_at_ts", now),
                    )
                    for row in batch
                ],
            )
    return len(rows)


def upsert_ohlcv_intraday_15m(path: Path, rows: list[dict[str, Any]]) -> int:
    ensure_central_db(path)
    if not rows:
        return 0
    now = time.time()
    rows_by_path: dict[Path, list[dict[str, Any]]] = {}
    for row in rows:
        db_path = _db_path_for_ticker(path, str(row["ticker"]).upper(), row.get("source_market"))
        rows_by_path.setdefault(db_path, []).append(row)

    for db_path, batch in rows_by_path.items():
        with sqlite3.connect(db_path) as conn:
            conn.executemany(
                """
                INSERT INTO ohlcv_intraday_15m (
                    ticker,
                    bar_time,
                    trade_date,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    source,
                    source_market,
                    fetched_at_ts
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, bar_time) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    source = excluded.source,
                    source_market = excluded.source_market,
                    fetched_at_ts = excluded.fetched_at_ts
                """,
                [
                    (
                        row["ticker"],
                        row["bar_time"],
                        row["trade_date"],
                        row.get("open"),
                        row.get("high"),
                        row.get("low"),
                        row.get("close"),
                        row.get("volume"),
                        row.get("source", ""),
                        row.get("source_market", ""),
                        row.get("fetched_at_ts", now),
                    )
                    for row in batch
                ],
            )
    return len(rows)


def upsert_quote_snapshots_15m(path: Path, rows: list[dict[str, Any]]) -> int:
    ensure_central_db(path)
    if not rows:
        return 0
    now = time.time()
    rows_by_path: dict[Path, list[dict[str, Any]]] = {}
    for row in rows:
        db_path = _db_path_for_ticker(path, str(row["ticker"]).upper(), row.get("source_market"))
        rows_by_path.setdefault(db_path, []).append(row)

    for db_path, batch in rows_by_path.items():
        with sqlite3.connect(db_path) as conn:
            conn.executemany(
                """
                INSERT INTO quote_snapshots_15m (
                    ticker,
                    captured_at,
                    trade_date,
                    close,
                    prev_close,
                    change,
                    change_pct,
                    source,
                    source_market,
                    fetched_at_ts
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, captured_at) DO UPDATE SET
                    close = excluded.close,
                    prev_close = excluded.prev_close,
                    change = excluded.change,
                    change_pct = excluded.change_pct,
                    source = excluded.source,
                    source_market = excluded.source_market,
                    fetched_at_ts = excluded.fetched_at_ts
                """,
                [
                    (
                        row["ticker"],
                        row["captured_at"],
                        row["trade_date"],
                        row.get("close"),
                        row.get("prev_close"),
                        row.get("change"),
                        row.get("change_pct"),
                        row.get("source", ""),
                        row.get("source_market", ""),
                        row.get("fetched_at_ts", now),
                    )
                    for row in batch
                ],
            )
    return len(rows)


def upsert_after_close_quotes(path: Path, rows: list[dict[str, Any]]) -> int:
    ensure_central_db(path)
    if not rows:
        return 0
    now = time.time()
    rows_by_path: dict[Path, list[dict[str, Any]]] = {}
    for row in rows:
        db_path = _db_path_for_ticker(path, str(row["ticker"]).upper(), row.get("source_market"))
        rows_by_path.setdefault(db_path, []).append(row)

    for db_path, batch in rows_by_path.items():
        with sqlite3.connect(db_path) as conn:
            conn.executemany(
                """
                INSERT INTO after_close_quotes (
                    ticker,
                    trade_date,
                    captured_at,
                    close,
                    prev_close,
                    change,
                    change_pct,
                    source,
                    source_market,
                    fetched_at_ts
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, trade_date) DO UPDATE SET
                    captured_at = excluded.captured_at,
                    close = excluded.close,
                    prev_close = excluded.prev_close,
                    change = excluded.change,
                    change_pct = excluded.change_pct,
                    source = excluded.source,
                    source_market = excluded.source_market,
                    fetched_at_ts = excluded.fetched_at_ts
                """,
                [
                    (
                        row["ticker"],
                        row["trade_date"],
                        row["captured_at"],
                        row.get("close"),
                        row.get("prev_close"),
                        row.get("change"),
                        row.get("change_pct"),
                        row.get("source", ""),
                        row.get("source_market", ""),
                        row.get("fetched_at_ts", now),
                    )
                    for row in batch
                ],
            )
    return len(rows)


def upsert_etf_dividends(path: Path, rows: list[dict[str, Any]]) -> int:
    ensure_central_db(path)
    if not rows:
        return 0
    now = time.time()
    rows_by_path: dict[Path, list[dict[str, Any]]] = {}
    for row in rows:
        ticker = str(row.get("ticker", "")).strip().upper()
        if not ticker:
            continue
        db_path = _db_path_for_dividend(path, ticker)
        rows_by_path.setdefault(db_path, []).append({**row, "ticker": ticker})

    written = 0
    for db_path, batch in rows_by_path.items():
        with sqlite3.connect(db_path) as conn:
            before = conn.total_changes
            conn.executemany(
                """
                INSERT INTO etf_dividends (
                    ticker,
                    name,
                    ex_dividend_date,
                    record_date,
                    payout_date,
                    dividend,
                    announcement_year,
                    source,
                    source_url,
                    composition_text,
                    updated_at_ts
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(ticker, ex_dividend_date, record_date, payout_date, dividend) DO UPDATE SET
                    name = excluded.name,
                    announcement_year = excluded.announcement_year,
                    source = excluded.source,
                    source_url = excluded.source_url,
                    composition_text = excluded.composition_text,
                    updated_at_ts = excluded.updated_at_ts
                """,
                [
                    (
                        row["ticker"],
                        str(row.get("name", "") or row["ticker"]),
                        str(row.get("ex_dividend_date", "") or ""),
                        str(row.get("record_date", "") or ""),
                        str(row.get("payout_date", "") or ""),
                        row.get("dividend"),
                        str(row.get("announcement_year", "") or ""),
                        str(row.get("source", "") or "manual"),
                        str(row.get("source_url", "") or ""),
                        str(row.get("composition_text", "") or ""),
                        row.get("updated_at_ts", now),
                    )
                    for row in batch
                    if row.get("ex_dividend_date") and row.get("dividend") is not None
                ],
            )
            written += conn.total_changes - before
    return written


def set_dividend_target(
    path: Path,
    ticker: str,
    name: str = "",
    asset_type: str = "ETF",
    exchange_suffix: str = ".TW",
    source: str = "manual",
) -> dict[str, Any]:
    ensure_central_db(path)
    ticker = str(ticker or "").strip().upper()
    if not ticker:
        raise ValueError("ticker is required")
    asset_type = str(asset_type or infer_asset_type(ticker)).strip().upper()
    if asset_type not in {"ETF", "STOCK"}:
        asset_type = infer_asset_type(ticker)
    exchange_suffix = str(exchange_suffix or ".TW").strip().upper()
    if not exchange_suffix.startswith("."):
        exchange_suffix = f".{exchange_suffix}"
    row = {
        "ticker": ticker,
        "name": clean_name(name, ticker),
        "type": asset_type,
        "exchange_suffix": exchange_suffix,
        "source": str(source or "manual"),
    }
    db_path = _db_path_for_dividend(path, ticker)
    now = time.time()
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dividend_targets (
                ticker,
                name,
                type,
                exchange_suffix,
                source,
                created_at_ts,
                updated_at_ts
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                name = CASE
                    WHEN excluded.name <> excluded.ticker THEN excluded.name
                    ELSE dividend_targets.name
                END,
                type = excluded.type,
                exchange_suffix = excluded.exchange_suffix,
                source = excluded.source,
                updated_at_ts = excluded.updated_at_ts
            """,
            (
                row["ticker"],
                row["name"],
                row["type"],
                row["exchange_suffix"],
                row["source"],
                now,
                now,
            ),
        )
    return row


def list_dividend_targets(path: Path) -> list[dict[str, Any]]:
    ensure_central_db(path)
    by_ticker: dict[str, dict[str, Any]] = {}
    refresh_status = dividend_refresh_status_by_ticker(path)
    for segment, db_path in segment_db_paths(path).items():
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            target_rows = [dict(row) for row in conn.execute("SELECT * FROM dividend_targets").fetchall()]
            dividend_rows = [
                dict(row)
                for row in conn.execute(
                    """
                    SELECT ticker, name, MAX(updated_at_ts) AS updated_at_ts
                    FROM etf_dividends
                    GROUP BY ticker
                    """
                ).fetchall()
            ]
        for row in dividend_rows:
            ticker = str(row.get("ticker") or "").strip().upper()
            if ticker and ticker not in by_ticker:
                by_ticker[ticker] = {
                    "ticker": ticker,
                    "name": clean_name(row.get("name"), ticker),
                    "type": infer_asset_type(ticker),
                    "exchange_suffix": ".TW",
                    "source": "dividend_history",
                    "segment": segment,
                    "updated_at_ts": row.get("updated_at_ts"),
                    "refresh_status": refresh_status.get(ticker),
                }
        for row in target_rows:
            ticker = str(row.get("ticker") or "").strip().upper()
            if ticker:
                existing = by_ticker.get(ticker)
                if existing and not is_specific_name(row.get("name"), ticker):
                    row["name"] = existing.get("name") or ticker
                row["segment"] = segment
                row["refresh_status"] = refresh_status.get(ticker)
                by_ticker[ticker] = row
    for ticker, row in by_ticker.items():
        row.setdefault("refresh_status", refresh_status.get(ticker))
    return sorted(by_ticker.values(), key=lambda row: str(row.get("ticker", "")))


def record_dividend_refresh_status(
    path: Path,
    ticker: str,
    source: str,
    started_at: str,
    finished_at: str,
    status: str,
    fetched_count: int = 0,
    written_count: int = 0,
    message: str = "",
) -> None:
    ensure_central_db(path)
    ticker = str(ticker or "").strip().upper()
    if not ticker:
        return
    db_path = _db_path_for_dividend(path, ticker)
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO dividend_refresh_status (
                ticker,
                source,
                last_started_at,
                last_finished_at,
                last_status,
                fetched_count,
                written_count,
                message
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                source = excluded.source,
                last_started_at = excluded.last_started_at,
                last_finished_at = excluded.last_finished_at,
                last_status = excluded.last_status,
                fetched_count = excluded.fetched_count,
                written_count = excluded.written_count,
                message = excluded.message
            """,
            (
                ticker,
                source,
                started_at,
                finished_at,
                "success" if status == "success" else "failed",
                int(fetched_count or 0),
                int(written_count or 0),
                str(message or "")[:240],
            ),
        )


def dividend_refresh_status_by_ticker(path: Path) -> dict[str, dict[str, Any]]:
    ensure_central_db(path)
    rows: dict[str, dict[str, Any]] = {}
    for segment, db_path in segment_db_paths(path).items():
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            for row in conn.execute("SELECT * FROM dividend_refresh_status").fetchall():
                data = dict(row)
                data["segment"] = segment
                ticker = str(data.get("ticker") or "").strip().upper()
                if ticker:
                    rows[ticker] = data
    return rows


def list_etf_dividends(
    path: Path,
    ticker: str,
    start_year: int | None = None,
    end_year: int | None = None,
) -> list[dict[str, Any]]:
    ensure_central_db(path)
    ticker = str(ticker).strip().upper()
    db_path = _db_path_for_dividend(path, ticker)
    clauses = ["ticker = ?"]
    params: list[Any] = [ticker]
    if start_year is not None:
        clauses.append("ex_dividend_date >= ?")
        params.append(f"{int(start_year):04d}-01-01")
    if end_year is not None:
        clauses.append("ex_dividend_date <= ?")
        params.append(f"{int(end_year):04d}-12-31")
    sql = f"""
        SELECT *
        FROM etf_dividends
        WHERE {' AND '.join(clauses)}
        ORDER BY ex_dividend_date DESC, payout_date DESC
    """
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def list_ohlcv_daily(
    path: Path,
    ticker: str,
    start_date: str | None = None,
    end_date: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    ensure_central_db(path)
    db_path = _db_path_for_ticker(path, str(ticker).strip().upper(), None)
    clauses = ["ticker = ?"]
    params: list[Any] = [str(ticker).strip().upper()]
    if start_date:
        clauses.append("trade_date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("trade_date <= ?")
        params.append(end_date)
    sql = f"""
        SELECT *
        FROM ohlcv_daily
        WHERE {' AND '.join(clauses)}
        ORDER BY trade_date DESC
    """
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def list_ohlcv_intraday_15m(
    path: Path,
    ticker: str,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    ensure_central_db(path)
    db_path = _db_path_for_ticker(path, str(ticker).strip().upper(), None)
    clauses = ["ticker = ?"]
    params: list[Any] = [str(ticker).strip().upper()]
    if start_time:
        clauses.append("bar_time >= ?")
        params.append(start_time)
    if end_time:
        clauses.append("bar_time <= ?")
        params.append(end_time)
    sql = f"""
        SELECT *
        FROM ohlcv_intraday_15m
        WHERE {' AND '.join(clauses)}
        ORDER BY bar_time DESC
    """
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def list_quote_snapshots_15m(
    path: Path,
    ticker: str,
    start_time: str | None = None,
    end_time: str | None = None,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    ensure_central_db(path)
    db_path = _db_path_for_ticker(path, str(ticker).strip().upper(), None)
    clauses = ["ticker = ?"]
    params: list[Any] = [str(ticker).strip().upper()]
    if start_time:
        clauses.append("captured_at >= ?")
        params.append(start_time)
    if end_time:
        clauses.append("captured_at <= ?")
        params.append(end_time)
    sql = f"""
        SELECT *
        FROM quote_snapshots_15m
        WHERE {' AND '.join(clauses)}
        ORDER BY captured_at DESC
    """
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(sql, params).fetchall()
    return [dict(row) for row in rows]


def latest_after_close_quote(path: Path, ticker: str) -> dict[str, Any] | None:
    ensure_central_db(path)
    db_path = _db_path_for_ticker(path, str(ticker).strip().upper(), None)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT *
            FROM after_close_quotes
            WHERE ticker = ?
            ORDER BY trade_date DESC
            LIMIT 1
            """,
            (str(ticker).strip().upper(),),
        ).fetchone()
    return dict(row) if row else None


def ohlcv_daily_stats(path: Path, ticker: str) -> dict[str, Any]:
    ensure_central_db(path)
    db_path = _db_path_for_ticker(path, str(ticker).strip().upper(), None)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS bar_count,
                MIN(trade_date) AS first_date,
                MAX(trade_date) AS last_date
            FROM ohlcv_daily
            WHERE ticker = ?
            """,
            (str(ticker).strip().upper(),),
        ).fetchone()
    return dict(row) if row else {"bar_count": 0, "first_date": None, "last_date": None}


def update_instrument_listing_date(path: Path, ticker: str, listing_date: str) -> None:
    ensure_central_db(path)
    ticker = str(ticker or "").strip().upper()
    listing_date = str(listing_date or "").strip()
    if not ticker or not listing_date:
        return
    instrument = get_instrument(path, ticker)
    if not instrument:
        return
    db_path = segment_db_paths(path)[instrument["segment"]]
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE instruments
            SET listing_date = CASE
                WHEN listing_date = '' OR listing_date IS NULL OR listing_date > ? THEN ?
                ELSE listing_date
            END,
            updated_at_ts = ?
            WHERE ticker = ?
            """,
            (listing_date, listing_date, time.time(), ticker),
        )


def update_instrument_history_status(
    path: Path,
    ticker: str,
    status: str,
    checked_at: str = "",
    listing_date: str = "",
) -> None:
    ensure_central_db(path)
    ticker = str(ticker or "").strip().upper()
    if not ticker:
        return
    instrument = get_instrument(path, ticker)
    if not instrument:
        return
    db_path = segment_db_paths(path)[instrument["segment"]]
    checked_at = checked_at or datetime.now().astimezone().isoformat(timespec="seconds")
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            UPDATE instruments
            SET
                history_status = ?,
                history_checked_at = ?,
                listing_date = CASE
                    WHEN ? = '' THEN listing_date
                    WHEN listing_date = '' OR listing_date IS NULL OR listing_date > ? THEN ?
                    ELSE listing_date
                END,
                updated_at_ts = ?
            WHERE ticker = ?
            """,
            (
                str(status or "").strip(),
                checked_at,
                str(listing_date or "").strip(),
                str(listing_date or "").strip(),
                str(listing_date or "").strip(),
                time.time(),
                ticker,
            ),
        )


def seed_quotes_from_json(path: Path, json_path: Path) -> None:
    if not json_path.exists():
        return
    existing = load_quote_cache(path)
    try:
        cache = json.loads(json_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(cache, dict):
        return
    merged = {**cache, **existing}
    if len(merged) != len(existing):
        save_quote_cache(path, merged)


def segment_for_instrument(asset_type: str, exchange_suffix: str) -> str:
    if str(asset_type or "").strip().upper() == "ETF":
        return "etf"
    if str(exchange_suffix or "").strip().upper() == ".TWO":
        return "tpex"
    return "twse"


def merge_instrument(existing: dict[str, Any] | None, incoming: dict[str, Any]) -> dict[str, Any]:
    if not existing:
        return incoming
    existing_name = clean_name(existing.get("name", ""), existing.get("ticker", ""))
    incoming_name = clean_name(incoming.get("name", ""), incoming.get("ticker", ""))
    ticker = str(existing.get("ticker") or incoming.get("ticker") or "").upper()

    if is_specific_name(existing_name, ticker):
        name = existing_name
    elif is_specific_name(incoming_name, ticker):
        name = incoming_name
    else:
        name = existing_name or incoming_name or ticker

    return {
        "ticker": ticker,
        "symbol": incoming.get("symbol") or existing.get("symbol"),
        "name": name,
        "type": incoming.get("type") or existing.get("type") or infer_asset_type(ticker),
        "exchange_suffix": incoming.get("exchange_suffix") or existing.get("exchange_suffix") or ".TW",
        "source": incoming.get("source") or existing.get("source") or "profile",
        "listing_date": incoming.get("listing_date") or existing.get("listing_date") or "",
        "history_status": incoming.get("history_status") or existing.get("history_status") or "",
        "history_checked_at": incoming.get("history_checked_at") or existing.get("history_checked_at") or "",
        "updated_at_ts": time.time(),
    }


def clean_name(value: object, ticker: object) -> str:
    text = str(value or "").strip()
    ticker_text = str(ticker or "").strip().upper()
    return text or ticker_text


def is_specific_name(name: str | None, ticker: str) -> bool:
    return bool(name) and str(name).strip().upper() != str(ticker).strip().upper()


def infer_asset_type(ticker: str) -> str:
    return "ETF" if str(ticker).startswith("00") else "STOCK"


def _upsert_instrument(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    ensure_central_db(path)
    segment = segment_for_instrument(row["type"], row["exchange_suffix"])
    db_path = segment_db_paths(path)[segment if not _is_legacy_file(path) else "legacy"]
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO instruments (
                ticker,
                symbol,
                name,
                type,
                exchange_suffix,
                source,
                listing_date,
                history_status,
                history_checked_at,
                updated_at_ts
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ticker) DO UPDATE SET
                symbol = excluded.symbol,
                name = excluded.name,
                type = excluded.type,
                exchange_suffix = excluded.exchange_suffix,
                source = excluded.source,
                listing_date = COALESCE(NULLIF(excluded.listing_date, ''), instruments.listing_date),
                history_status = COALESCE(NULLIF(excluded.history_status, ''), instruments.history_status),
                history_checked_at = COALESCE(NULLIF(excluded.history_checked_at, ''), instruments.history_checked_at),
                updated_at_ts = excluded.updated_at_ts
            """,
            (
                row["ticker"],
                row["symbol"],
                row["name"],
                row["type"],
                row["exchange_suffix"],
                row["source"],
                row.get("listing_date", ""),
                row.get("history_status", ""),
                row.get("history_checked_at", ""),
                row["updated_at_ts"],
            ),
        )
    _delete_ticker_from_other_segments(path, row["ticker"], keep_path=db_path)
    return {**row, "segment": segment}


def _delete_ticker_from_other_segments(path: Path, ticker: str, keep_path: Path) -> None:
    if _is_legacy_file(path):
        return
    for db_path in segment_db_paths(path).values():
        if db_path == keep_path:
            continue
        try:
            with sqlite3.connect(db_path) as conn:
                conn.execute("DELETE FROM instruments WHERE ticker = ?", (ticker,))
                conn.execute("DELETE FROM ohlcv_daily WHERE ticker = ?", (ticker,))
                conn.execute("DELETE FROM ohlcv_intraday_15m WHERE ticker = ?", (ticker,))
                conn.execute("DELETE FROM quote_snapshots_15m WHERE ticker = ?", (ticker,))
                conn.execute("DELETE FROM after_close_quotes WHERE ticker = ?", (ticker,))
                conn.execute("DELETE FROM etf_dividends WHERE ticker = ?", (ticker,))
        except sqlite3.DatabaseError:
            continue


def _db_path_for_ticker(path: Path, ticker: str, source_market: str | None) -> Path:
    if _is_legacy_file(path):
        return path
    instrument = get_instrument(path, ticker)
    if instrument:
        return segment_db_paths(path)[instrument["segment"]]
    fallback_segment = "tpex" if str(source_market or "").upper() == "TPEX" else "twse"
    return segment_db_paths(path)[fallback_segment]


def _db_path_for_dividend(path: Path, ticker: str) -> Path:
    if _is_legacy_file(path):
        return path
    instrument = get_instrument(path, ticker)
    if instrument:
        return segment_db_paths(path)[instrument["segment"]]
    return segment_db_paths(path)["etf" if str(ticker).startswith("00") else "twse"]


def _ensure_database_file(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS instruments (
                ticker TEXT PRIMARY KEY,
                symbol TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                exchange_suffix TEXT NOT NULL,
                source TEXT NOT NULL,
                listing_date TEXT NOT NULL DEFAULT '',
                history_status TEXT NOT NULL DEFAULT '',
                history_checked_at TEXT NOT NULL DEFAULT '',
                updated_at_ts REAL NOT NULL
            )
            """
        )
        _ensure_column(conn, "instruments", "listing_date", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "instruments", "history_status", "TEXT NOT NULL DEFAULT ''")
        _ensure_column(conn, "instruments", "history_checked_at", "TEXT NOT NULL DEFAULT ''")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quotes (
                symbol TEXT PRIMARY KEY,
                quote_json TEXT NOT NULL,
                fetched_at_ts REAL NOT NULL,
                updated_at_ts REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ohlcv_daily (
                ticker TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                turnover REAL,
                transactions INTEGER,
                source TEXT NOT NULL,
                source_market TEXT NOT NULL,
                fetched_at_ts REAL NOT NULL,
                PRIMARY KEY (ticker, trade_date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ohlcv_intraday_15m (
                ticker TEXT NOT NULL,
                bar_time TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                volume INTEGER,
                source TEXT NOT NULL,
                source_market TEXT NOT NULL,
                fetched_at_ts REAL NOT NULL,
                PRIMARY KEY (ticker, bar_time)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS quote_snapshots_15m (
                ticker TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                close REAL,
                prev_close REAL,
                change REAL,
                change_pct REAL,
                source TEXT NOT NULL,
                source_market TEXT NOT NULL,
                fetched_at_ts REAL NOT NULL,
                PRIMARY KEY (ticker, captured_at)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS after_close_quotes (
                ticker TEXT NOT NULL,
                trade_date TEXT NOT NULL,
                captured_at TEXT NOT NULL,
                close REAL,
                prev_close REAL,
                change REAL,
                change_pct REAL,
                source TEXT NOT NULL,
                source_market TEXT NOT NULL,
                fetched_at_ts REAL NOT NULL,
                PRIMARY KEY (ticker, trade_date)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS update_status (
                job_name TEXT PRIMARY KEY,
                source TEXT,
                last_started_at TEXT,
                last_finished_at TEXT,
                next_run_at TEXT,
                last_status TEXT,
                success_count INTEGER,
                fail_count INTEGER,
                message TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS etf_dividends (
                ticker TEXT NOT NULL,
                name TEXT NOT NULL,
                ex_dividend_date TEXT NOT NULL,
                record_date TEXT NOT NULL,
                payout_date TEXT NOT NULL,
                dividend REAL NOT NULL,
                announcement_year TEXT,
                source TEXT NOT NULL,
                source_url TEXT,
                composition_text TEXT,
                updated_at_ts REAL NOT NULL,
                PRIMARY KEY (ticker, ex_dividend_date, record_date, payout_date, dividend)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dividend_targets (
                ticker TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                exchange_suffix TEXT NOT NULL,
                source TEXT NOT NULL,
                created_at_ts REAL NOT NULL,
                updated_at_ts REAL NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dividend_refresh_status (
                ticker TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                last_started_at TEXT,
                last_finished_at TEXT,
                last_status TEXT NOT NULL,
                fetched_count INTEGER NOT NULL,
                written_count INTEGER NOT NULL,
                message TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ohlcv_daily_trade_date
            ON ohlcv_daily (trade_date)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_ohlcv_intraday_15m_trade_date
            ON ohlcv_intraday_15m (trade_date)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_quote_snapshots_15m_trade_date
            ON quote_snapshots_15m (trade_date)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_after_close_quotes_trade_date
            ON after_close_quotes (trade_date)
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_etf_dividends_ex_date
            ON etf_dividends (ex_dividend_date)
            """
        )


def _ensure_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    columns = {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    if column not in columns:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


def _retention_daily_cutoff(today: date) -> date:
    try:
        return today.replace(year=today.year - 5) - timedelta(days=30)
    except ValueError:
        return today.replace(year=today.year - 5, day=28) - timedelta(days=30)


def _is_legacy_file(path: Path) -> bool:
    return path.suffix.lower() in {".sqlite", ".db"}
