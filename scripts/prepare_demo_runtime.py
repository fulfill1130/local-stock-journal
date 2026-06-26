from __future__ import annotations

import argparse
import csv
import gc
import json
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from central_store import (  # noqa: E402
    SEGMENT_FILES,
    _create_market_schema,
    instrument_id_for,
    instrument_market,
    segment_for_market,
)
from store import load_state, save_state  # noqa: E402
from utils import yahoo_symbol  # noqa: E402


SENTINEL_NAME = ".demo_runtime"
SOURCE = "synthetic_demo"


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare an isolated synthetic demo runtime directory.")
    parser.add_argument(
        "--target",
        type=Path,
        default=ROOT / "demo_runtime",
        help="Target runtime directory. Defaults to ./demo_runtime.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete and recreate the target, only when it contains a demo sentinel.",
    )
    args = parser.parse_args()

    summary = prepare_demo_runtime(ROOT, args.target, reset=args.reset)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def prepare_demo_runtime(root: Path, target: Path | None = None, *, reset: bool = False) -> dict[str, Any]:
    root = Path(root).resolve()
    target = Path(target or root / "demo_runtime").resolve()
    sample_root = root / "sample_data"
    _validate_target(root, target)
    _prepare_target(target, reset=reset)

    profile_source = sample_root / "profiles" / "demo" / "state.json"
    quotes_source = sample_root / "market" / "quotes.csv"
    ohlcv_source = sample_root / "market" / "ohlcv_daily.csv"
    _require_file(profile_source)
    _require_file(quotes_source)
    _require_file(ohlcv_source)

    _write_sentinel(target)
    profile_target = target / "profiles" / "demo" / "state.json"
    profile_target.parent.mkdir(parents=True, exist_ok=True)
    state = load_state(profile_source)
    save_state(profile_target, state)

    metadata = _instrument_metadata(state)
    central_db_path = target / "market_data"
    _ensure_demo_market_data(central_db_path)
    _seed_instruments(central_db_path, metadata)

    history_rows = _load_history_rows(ohlcv_source, metadata)
    history_written = _seed_ohlcv_daily(central_db_path, history_rows, metadata)

    quote_rows = list(_read_csv(quotes_source))
    quotes_written = _seed_quotes(central_db_path, quote_rows, metadata)
    _write_quote_cache(target / "quotes_cache.json", quote_rows, metadata)

    dividend_rows = _dividend_calendar_rows(state)
    dividends_written = _seed_dividends(central_db_path, dividend_rows, metadata)
    _seed_health_summary(central_db_path, metadata)
    gc.collect()

    return {
        "target": str(target),
        "profile": str(profile_target),
        "market_data": str(central_db_path),
        "history_rows": history_written,
        "quote_rows": quotes_written,
        "dividend_rows": dividends_written,
        "tickers": sorted(metadata),
    }


def _validate_target(root: Path, target: Path) -> None:
    forbidden = {
        (root / "data").resolve(),
        (root / "sample_data").resolve(),
        root.resolve(),
    }
    if target in forbidden or target.name.lower() in {"data", "sample_data"}:
        raise ValueError(f"Refusing unsafe demo runtime target: {target}")


def _prepare_target(target: Path, *, reset: bool) -> None:
    if reset and target.exists():
        sentinel = target / SENTINEL_NAME
        if not sentinel.exists():
            raise RuntimeError(f"Refusing to reset target without {SENTINEL_NAME}: {target}")
        gc.collect()
        shutil.rmtree(target)
    elif target.exists() and any(target.iterdir()):
        raise RuntimeError(f"Target already exists and is not empty; use --reset: {target}")
    target.mkdir(parents=True, exist_ok=True)


def _write_sentinel(target: Path) -> None:
    payload = {
        "generated": True,
        "kind": "stock_daily_helper_demo_runtime",
        "source": "sample_data",
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "safe_to_delete": True,
    }
    (target / SENTINEL_NAME).write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _require_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Required sample file missing: {path}")


def _instrument_metadata(state: dict[str, Any]) -> dict[str, dict[str, str]]:
    metadata: dict[str, dict[str, str]] = {}
    for item in state.get("holdings", []) + state.get("watchlist", []):
        ticker = str(item.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        metadata[ticker] = {
            "ticker": ticker,
            "name": str(item.get("name") or ticker),
            "type": str(item.get("type") or "STOCK").strip().upper(),
            "exchange_suffix": str(item.get("exchange_suffix") or ".TW").strip().upper(),
        }
        metadata[ticker]["market"] = instrument_market(metadata[ticker]["type"], metadata[ticker]["exchange_suffix"])
        metadata[ticker]["segment"] = segment_for_market(metadata[ticker]["market"])
        metadata[ticker]["instrument_id"] = instrument_id_for(ticker, metadata[ticker]["market"])
    return metadata


def _ensure_demo_market_data(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    for filename in SEGMENT_FILES.values():
        conn = sqlite3.connect(path / filename)
        try:
            _create_market_schema(conn)
            conn.commit()
        finally:
            conn.close()


def _seed_instruments(path: Path, metadata: dict[str, dict[str, str]]) -> int:
    written = 0
    grouped: dict[str, list[dict[str, str]]] = {}
    for item in metadata.values():
        grouped.setdefault(item["segment"], []).append(item)
    current = datetime.now().astimezone().isoformat(timespec="seconds")
    for segment, rows in grouped.items():
        conn = sqlite3.connect(path / SEGMENT_FILES[segment])
        try:
            before = conn.total_changes
            conn.executemany(
                """
                INSERT INTO instruments (
                    instrument_id, ticker, market, type, name, yahoo_symbol,
                    listing_date, delisting_date, status, source, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, '', '', 'active', ?, ?, ?)
                ON CONFLICT(instrument_id) DO UPDATE SET
                    ticker = excluded.ticker,
                    market = excluded.market,
                    type = excluded.type,
                    name = excluded.name,
                    yahoo_symbol = excluded.yahoo_symbol,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                [
                    (
                        row["instrument_id"],
                        row["ticker"],
                        row["market"],
                        row["type"],
                        row["name"],
                        yahoo_symbol(row["ticker"], row["exchange_suffix"]),
                        SOURCE,
                        current,
                        current,
                    )
                    for row in rows
                ],
            )
            conn.commit()
            written += conn.total_changes - before
        finally:
            conn.close()
    return written


def _load_history_rows(path: Path, metadata: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in _read_csv(path):
        ticker = str(raw.get("instrument_id") or "").strip().upper()
        if not ticker:
            continue
        meta = metadata.get(ticker, {"ticker": ticker, "name": ticker, "type": "STOCK", "exchange_suffix": ".TW"})
        rows.append(
            {
                "ticker": ticker,
                "name": meta["name"],
                "type": meta["type"],
                "exchange_suffix": meta["exchange_suffix"],
                "date": raw.get("date", ""),
                "open": _float_or_none(raw.get("open")),
                "high": _float_or_none(raw.get("high")),
                "low": _float_or_none(raw.get("low")),
                "close": _float_or_none(raw.get("close")),
                "volume": _int_or_none(raw.get("volume")),
                "value": _float_or_none(raw.get("value")),
                "source": raw.get("source") or SOURCE,
                "adjusted": 1 if str(raw.get("adjusted") or "").strip().lower() in {"1", "true", "yes"} else 0,
            }
        )
    return rows


def _seed_ohlcv_daily(
    central_db_path: Path,
    rows: list[dict[str, Any]],
    metadata: dict[str, dict[str, str]],
) -> int:
    written = 0
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        meta = metadata.get(ticker)
        if not meta:
            continue
        grouped.setdefault(meta["segment"], []).append(row)
    current = datetime.now().astimezone().isoformat(timespec="seconds")
    for segment, batch in grouped.items():
        conn = sqlite3.connect(central_db_path / SEGMENT_FILES[segment])
        try:
            before = conn.total_changes
            conn.executemany(
                """
                INSERT INTO ohlcv_daily (
                    instrument_id, date, open, high, low, close, volume, value,
                    source, adjusted, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(instrument_id, date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    value = excluded.value,
                    source = excluded.source,
                    adjusted = excluded.adjusted,
                    updated_at = excluded.updated_at
                """,
                [
                    (
                        metadata[row["ticker"]]["instrument_id"],
                        row["date"],
                        row["open"],
                        row["high"],
                        row["low"],
                        row["close"],
                        row["volume"],
                        row["value"],
                        row["source"],
                        row["adjusted"],
                        current,
                        current,
                    )
                    for row in batch
                ],
            )
            conn.commit()
            written += conn.total_changes - before
        finally:
            conn.close()
    return written


def _seed_quotes(
    central_db_path: Path,
    rows: list[dict[str, str]],
    metadata: dict[str, dict[str, str]],
) -> int:
    written = 0
    for row in rows:
        ticker = str(row.get("instrument_id") or "").strip().upper()
        meta = metadata.get(ticker)
        if not ticker or not meta:
            continue
        db_path = central_db_path / SEGMENT_FILES[meta["segment"]]
        source_timestamp = str(row.get("source_timestamp") or "")
        conn = sqlite3.connect(db_path)
        try:
            before = conn.total_changes
            conn.execute(
                """
                INSERT INTO quotes (
                    instrument_id, price, change, change_pct, quote_date, quote_time, source, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(instrument_id) DO UPDATE SET
                    price = excluded.price,
                    change = excluded.change,
                    change_pct = excluded.change_pct,
                    quote_date = excluded.quote_date,
                    quote_time = excluded.quote_time,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (
                    meta["instrument_id"],
                    _float_or_none(row.get("price")),
                    _float_or_none(row.get("change")),
                    _float_or_none(row.get("change_pct")),
                    source_timestamp[:10],
                    source_timestamp,
                    row.get("source") or SOURCE,
                    source_timestamp or datetime.now().astimezone().isoformat(timespec="seconds"),
                ),
            )
            conn.commit()
            written += conn.total_changes - before
        finally:
            conn.close()
    return written


def _write_quote_cache(path: Path, rows: list[dict[str, str]], metadata: dict[str, dict[str, str]]) -> None:
    cache: dict[str, dict[str, Any]] = {}
    for row in rows:
        ticker = str(row.get("instrument_id") or "").strip().upper()
        if not ticker:
            continue
        suffix = metadata.get(ticker, {}).get("exchange_suffix", ".TW")
        symbol = yahoo_symbol(ticker, suffix)
        source_timestamp = str(row.get("source_timestamp") or "")
        cache[symbol] = {
            "close": _float_or_none(row.get("price")),
            "prev_close": _float_or_none(row.get("previous_close")),
            "change": _float_or_none(row.get("change")),
            "change_pct": _float_or_none(row.get("change_pct")),
            "price_time": source_timestamp,
            "source": row.get("source") or SOURCE,
            "fetched_at": source_timestamp,
            "fetched_at_ts": datetime.now().timestamp(),
            "status": "demo",
            "error": "",
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _dividend_calendar_rows(state: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in state.get("holdings", []) + state.get("watchlist", []):
        ticker = str(item.get("ticker") or "").strip().upper()
        ex_date = str(item.get("ex_dividend_date") or "").strip()
        payout_date = str(item.get("payout_date") or "").strip()
        dividend = _float_or_none(item.get("monthly_dividend_est"))
        if not ticker or not ex_date or dividend is None:
            continue
        rows.append(
            {
                "ticker": ticker,
                "name": str(item.get("name") or ticker),
                "ex_dividend_date": ex_date,
                "record_date": ex_date,
                "payout_date": payout_date,
                "dividend": dividend,
                "announcement_year": ex_date[:4],
                "source": SOURCE,
                "source_url": "",
                "composition_text": "Synthetic demo dividend calendar event.",
            }
        )
    return rows


def _seed_dividends(
    central_db_path: Path,
    rows: list[dict[str, Any]],
    metadata: dict[str, dict[str, str]],
) -> int:
    written = 0
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        meta = metadata.get(str(row.get("ticker") or "").strip().upper())
        if meta:
            grouped.setdefault(meta["segment"], []).append(row)
    for segment, batch in grouped.items():
        conn = sqlite3.connect(central_db_path / SEGMENT_FILES[segment])
        try:
            before = conn.total_changes
            conn.executemany(
                """
                INSERT INTO etf_dividends (
                    ticker, name, ex_dividend_date, record_date, payout_date,
                    dividend, announcement_year, source, source_url, composition_text, updated_at_ts
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
                        row["name"],
                        row["ex_dividend_date"],
                        row["record_date"],
                        row["payout_date"],
                        row["dividend"],
                        row["announcement_year"],
                        row["source"],
                        row["source_url"],
                        row["composition_text"],
                        datetime.now().timestamp(),
                    )
                    for row in batch
                ],
            )
            conn.commit()
            written += conn.total_changes - before
        finally:
            conn.close()
    return written


def _seed_health_summary(central_db_path: Path, metadata: dict[str, dict[str, str]]) -> None:
    current = datetime.now().astimezone().isoformat(timespec="seconds")
    for item in metadata.values():
        conn = sqlite3.connect(central_db_path / SEGMENT_FILES[item["segment"]])
        try:
            conn.row_factory = sqlite3.Row
            stats = conn.execute(
                """
                SELECT COUNT(*) AS daily_rows, MIN(date) AS first_daily_date, MAX(date) AS last_daily_date
                FROM ohlcv_daily
                WHERE instrument_id = ?
                """,
                (item["instrument_id"],),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO instrument_health_summary (
                    instrument_id, daily_rows, first_daily_date, last_daily_date,
                    history_status, recent_data_ok, last_checked_at, last_success_at,
                    manual_review_required, updated_at
                )
                VALUES (?, ?, ?, ?, 'ok', 1, ?, ?, 0, ?)
                ON CONFLICT(instrument_id) DO UPDATE SET
                    daily_rows = excluded.daily_rows,
                    first_daily_date = excluded.first_daily_date,
                    last_daily_date = excluded.last_daily_date,
                    history_status = excluded.history_status,
                    recent_data_ok = excluded.recent_data_ok,
                    last_checked_at = excluded.last_checked_at,
                    last_success_at = excluded.last_success_at,
                    manual_review_required = excluded.manual_review_required,
                    updated_at = excluded.updated_at
                """,
                (
                    item["instrument_id"],
                    int(stats["daily_rows"] or 0),
                    stats["first_daily_date"],
                    stats["last_daily_date"],
                    current,
                    current,
                    current,
                ),
            )
            conn.commit()
        finally:
            conn.close()


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as file:
        return list(csv.DictReader(file))


def _float_or_none(value: Any) -> float | None:
    text = str(value or "").strip()
    return float(text) if text else None


def _int_or_none(value: Any) -> int | None:
    text = str(value or "").strip()
    return int(float(text)) if text else None


def verify_demo_runtime(target: Path) -> dict[str, Any]:
    target = Path(target).resolve()
    central_db_path = target / "market_data"
    return {
        "profile_exists": (target / "profiles" / "demo" / "state.json").exists(),
        "demoa_rows": _count_rows(central_db_path / "etf.sqlite", "ohlcv_daily", "instrument_id = 'ETF:DEMOA'"),
        "demob_rows": _count_rows(central_db_path / "twse.sqlite", "ohlcv_daily", "instrument_id = 'TWSE:DEMOB'"),
        "demoa_dividends": _count_rows(central_db_path / "etf.sqlite", "etf_dividends", "ticker = 'DEMOA'"),
    }


def _count_rows(db_path: Path, table: str, where: str) -> int:
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE {where}").fetchone()
        return int(row[0] or 0)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
