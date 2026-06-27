from __future__ import annotations

import json
import hashlib
import shutil
import sqlite3
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable

from utils import now_iso, pct, safe_subtract, yahoo_symbol


SEGMENT_FILES = {
    "etf": "etf.sqlite",
    "twse": "twse.sqlite",
    "tpex": "tpex.sqlite",
}

MARKET_SEGMENTS = {
    "ETF": "etf",
    "TWSE": "twse",
    "TPEX": "tpex",
}

SEGMENT_MARKETS = {value: key for key, value in MARKET_SEGMENTS.items()}

HEALTH_STATUSES = {
    "ok",
    "recent_ok_partial_history",
    "new_listing",
    "partial_old_missing",
    "recent_missing",
    "broken",
    "symbol_problem",
    "delisted_candidate",
    "delisted",
    "manual_review",
}

_ENSURED_CENTRAL_DB_PATHS: set[str] = set()


def ensure_central_db(path: Path) -> None:
    cache_key = str(path.resolve())
    if cache_key in _ENSURED_CENTRAL_DB_PATHS:
        return

    if _is_legacy_file(path):
        migrate_market_database_file(path, backup=False)
        _ensure_database_file(path)
        _ENSURED_CENTRAL_DB_PATHS.add(cache_key)
        return

    path.mkdir(parents=True, exist_ok=True)
    for db_path in segment_db_paths(path).values():
        migrate_market_database_file(db_path, backup=True)
        _ensure_database_file(db_path)
    repair_marker = path / ".empty_duplicate_repair_v1"
    if not repair_marker.exists():
        repaired = repair_empty_duplicate_instruments(path)
        repair_marker.write_text(json.dumps(repaired, ensure_ascii=False, indent=2), encoding="utf-8")
    _ENSURED_CENTRAL_DB_PATHS.add(cache_key)


def segment_db_paths(path: Path) -> dict[str, Path]:
    if _is_legacy_file(path):
        return {"legacy": path}
    return {segment: path / filename for segment, filename in SEGMENT_FILES.items()}


def instrument_market(asset_type: str, exchange_suffix: str, source_market: str | None = None) -> str:
    source = str(source_market or "").strip().upper()
    if source in {"TWSE", "TPEX", "ETF"}:
        return source
    if str(asset_type or "").strip().upper() == "ETF":
        return "ETF"
    if str(exchange_suffix or "").strip().upper() == ".TWO":
        return "TPEX"
    return "TWSE"


def exchange_suffix_for_market(market: str) -> str:
    return ".TWO" if str(market or "").strip().upper() == "TPEX" else ".TW"


def segment_for_market(market: str) -> str:
    return MARKET_SEGMENTS.get(str(market or "").strip().upper(), "twse")


def instrument_id_for(ticker: str, market: str) -> str:
    return f"{str(market or '').strip().upper()}:{str(ticker or '').strip().upper()}"


def row_instrument_id(row: dict[str, Any]) -> str:
    ticker = str(row.get("ticker") or "").strip().upper()
    market = str(row.get("market") or "").strip().upper()
    if not market:
        market = instrument_market(row.get("type", ""), row.get("exchange_suffix", ""), row.get("source_market"))
    return str(row.get("instrument_id") or instrument_id_for(ticker, market))


def migrate_market_database_file(db_path: Path, backup: bool = True) -> dict[str, Any]:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not db_path.exists():
        return {"database": str(db_path), "needed": False, "backup": ""}

    with sqlite3.connect(db_path) as conn:
        needed = (
            _table_exists(conn, "instruments") and "instrument_id" not in _table_columns(conn, "instruments")
        ) or (
            _table_exists(conn, "ohlcv_daily") and "instrument_id" not in _table_columns(conn, "ohlcv_daily")
        ) or (
            _table_exists(conn, "quotes") and "instrument_id" not in _table_columns(conn, "quotes")
        )
        if not needed:
            _create_market_schema(conn)
            return {"database": str(db_path), "needed": False, "backup": ""}

    backup_path = ""
    if backup:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = db_path.with_name(f"{db_path.name}.bak_{stamp}")
        shutil.copy2(db_path, backup_file)
        backup_path = str(backup_file)

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        summary = _migrate_market_database_connection(conn)
    summary["database"] = str(db_path)
    summary["backup"] = backup_path
    summary["needed"] = True
    return summary


def migrate_market_databases(path: Path, backup: bool = True) -> list[dict[str, Any]]:
    path.mkdir(parents=True, exist_ok=True)
    results = [
        migrate_market_database_file(db_path, backup=backup)
        for db_path in segment_db_paths(path).values()
    ]
    repaired = repair_empty_duplicate_instruments(path)
    repair_marker = path / ".empty_duplicate_repair_v1"
    repair_marker.write_text(json.dumps(repaired, ensure_ascii=False, indent=2), encoding="utf-8")
    if repaired:
        results.append({"database": str(path), "needed": False, "backup": "", "repaired": repaired})
    return results


def repair_empty_duplicate_instruments(path: Path) -> list[dict[str, Any]]:
    if _is_legacy_file(path):
        return []
    paths = segment_db_paths(path)
    records: list[dict[str, Any]] = []
    for segment, db_path in paths.items():
        if not db_path.exists():
            continue
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            if not _table_exists(conn, "instruments"):
                continue
            for row in conn.execute("SELECT * FROM instruments").fetchall():
                daily_rows = 0
                if _table_exists(conn, "ohlcv_daily") and "instrument_id" in _table_columns(conn, "ohlcv_daily"):
                    daily_rows = int(
                        conn.execute(
                            "SELECT COUNT(*) FROM ohlcv_daily WHERE instrument_id = ?",
                            (row["instrument_id"],),
                        ).fetchone()[0]
                        or 0
                    )
                records.append({**dict(row), "segment": segment, "db_path": db_path, "daily_rows": daily_rows})

    repaired: list[dict[str, Any]] = []
    by_ticker: dict[str, list[dict[str, Any]]] = {}
    for row in records:
        by_ticker.setdefault(str(row.get("ticker") or "").upper(), []).append(row)

    for ticker, group in by_ticker.items():
        if len(group) <= 1:
            continue
        max_rows = max(int(row.get("daily_rows") or 0) for row in group)
        if max_rows <= 0:
            continue
        for row in group:
            if int(row.get("daily_rows") or 0) > 0:
                continue
            db_path = row["db_path"]
            instrument_id = row["instrument_id"]
            with sqlite3.connect(db_path) as conn:
                _delete_instrument_data(conn, instrument_id)
            repaired.append(
                {
                    "ticker": ticker,
                    "instrument_id": instrument_id,
                    "segment": row["segment"],
                    "reason": "empty duplicate instrument removed",
                }
            )
    return repaired


def add_split_action(
    path: Path,
    ticker: str,
    effective_date: str,
    ratio_from: float,
    ratio_to: float,
    note: str = "",
    source: str = "manual",
) -> dict[str, Any]:
    ensure_central_db(path)
    ticker = str(ticker or "").strip().upper()
    effective_date = str(effective_date or "").strip()[:10]
    if not ticker:
        raise ValueError("ticker is required")
    if not effective_date:
        raise ValueError("effective_date is required")
    if ratio_from <= 0 or ratio_to <= 0:
        raise ValueError("split ratio must be greater than 0")
    instrument = get_instrument(path, ticker)
    if not instrument:
        raise ValueError(f"instrument not found: {ticker}")
    db_path = segment_db_paths(path)[instrument["segment"]]
    created_at = now_iso()
    with sqlite3.connect(db_path) as conn:
        _create_market_schema(conn)
        conn.execute(
            """
            INSERT INTO instrument_corporate_actions (
                instrument_id, action_type, effective_date, ratio_from, ratio_to,
                source, note, created_at, updated_at
            )
            VALUES (?, 'split', ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(instrument_id, action_type, effective_date) DO UPDATE SET
                ratio_from = excluded.ratio_from,
                ratio_to = excluded.ratio_to,
                source = excluded.source,
                note = excluded.note,
                updated_at = excluded.updated_at
            """,
            (
                instrument["instrument_id"],
                effective_date,
                float(ratio_from),
                float(ratio_to),
                source,
                note,
                created_at,
                created_at,
            ),
        )
    return {
        "ticker": ticker,
        "instrument_id": instrument["instrument_id"],
        "action_type": "split",
        "effective_date": effective_date,
        "ratio_from": float(ratio_from),
        "ratio_to": float(ratio_to),
        "ratio": float(ratio_to) / float(ratio_from),
        "note": note,
        "source": source,
    }


def list_corporate_actions(path: Path, ticker: str = "") -> list[dict[str, Any]]:
    ensure_central_db(path)
    normalized_ticker = str(ticker or "").strip().upper()
    rows: list[dict[str, Any]] = []
    for segment, db_path in segment_db_paths(path).items():
        if not db_path.exists():
            continue
        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                _create_market_schema(conn)
                clauses = []
                params: list[Any] = []
                if normalized_ticker:
                    clauses.append("i.ticker = ?")
                    params.append(normalized_ticker)
                where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
                records = conn.execute(
                    f"""
                    SELECT
                        a.*,
                        i.ticker,
                        i.name,
                        i.market,
                        i.type,
                        i.yahoo_symbol
                    FROM instrument_corporate_actions a
                    JOIN instruments i ON i.instrument_id = a.instrument_id
                    {where}
                    ORDER BY a.effective_date, i.ticker
                    """,
                    params,
                ).fetchall()
        except sqlite3.DatabaseError:
            continue
        for record in records:
            row = dict(record)
            row["segment"] = segment
            row["ratio"] = (
                float(row["ratio_to"]) / float(row["ratio_from"])
                if row.get("ratio_from") and row.get("ratio_to")
                else None
            )
            rows.append(row)
    return rows


def _delete_instrument_data(conn: sqlite3.Connection, instrument_id: str) -> None:
    for table in (
        "ohlcv_daily",
        "ohlcv_intraday_15m",
        "quote_snapshots_15m",
        "after_close_quotes",
        "quotes",
        "instrument_health_summary",
        "market_data_issues",
        "instrument_aliases",
        "instrument_name_history",
    ):
        if _table_exists(conn, table) and "instrument_id" in _table_columns(conn, table):
            conn.execute(f"DELETE FROM {table} WHERE instrument_id = ?", (instrument_id,))
    conn.execute("DELETE FROM instruments WHERE instrument_id = ?", (instrument_id,))


def _migrate_market_database_connection(conn: sqlite3.Connection) -> dict[str, Any]:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    old_tables: dict[str, str] = {}
    for table in (
        "instruments",
        "quotes",
        "ohlcv_daily",
        "ohlcv_intraday_15m",
        "quote_snapshots_15m",
        "after_close_quotes",
    ):
        if not _table_exists(conn, table):
            continue
        columns = _table_columns(conn, table)
        should_migrate = "instrument_id" not in columns
        if should_migrate:
            legacy_name = f"{table}_legacy_{stamp}"
            conn.execute(f"ALTER TABLE {table} RENAME TO {legacy_name}")
            old_tables[table] = legacy_name

    _create_market_schema(conn)
    instruments = _load_legacy_instruments(conn, old_tables.get("instruments"))
    for table in ("ohlcv_daily", "ohlcv_intraday_15m", "quote_snapshots_15m", "after_close_quotes"):
        if old_tables.get(table):
            _seed_instruments_from_legacy_rows(conn, old_tables[table], instruments)
    inserted_instruments = _insert_migrated_instruments(conn, instruments)
    copied = {
        "instruments": inserted_instruments,
        "ohlcv_daily": _copy_legacy_ohlcv_daily(conn, old_tables.get("ohlcv_daily"), instruments),
        "ohlcv_intraday_15m": _copy_legacy_intraday(conn, old_tables.get("ohlcv_intraday_15m"), instruments),
        "quote_snapshots_15m": _copy_legacy_snapshots(conn, old_tables.get("quote_snapshots_15m"), instruments),
        "after_close_quotes": _copy_legacy_after_close(conn, old_tables.get("after_close_quotes"), instruments),
        "quotes": _copy_legacy_quotes(conn, old_tables.get("quotes"), instruments),
    }
    return {"legacy_tables": old_tables, "copied": copied}


def _load_legacy_instruments(conn: sqlite3.Connection, table: str | None) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    if not table:
        return rows
    for raw in conn.execute(f"SELECT * FROM {table}").fetchall():
        item = dict(raw)
        ticker = str(item.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        asset_type = str(item.get("type") or infer_asset_type(ticker)).strip().upper()
        suffix = str(item.get("exchange_suffix") or ".TW").strip().upper()
        market = instrument_market(asset_type, suffix)
        instrument_id = instrument_id_for(ticker, market)
        updated_at = timestamp_to_iso(item.get("updated_at_ts")) or now_iso()
        rows[instrument_id] = {
            "instrument_id": instrument_id,
            "ticker": ticker,
            "market": market,
            "type": asset_type,
            "name": clean_name(item.get("name", ""), ticker),
            "yahoo_symbol": item.get("symbol") or yahoo_symbol(ticker, suffix),
            "listing_date": item.get("listing_date") or "",
            "delisting_date": "",
            "status": legacy_instrument_status(item.get("history_status")),
            "source": item.get("source") or "profile",
            "created_at": updated_at,
            "updated_at": updated_at,
        }
    return rows


def _seed_instruments_from_legacy_rows(
    conn: sqlite3.Connection,
    table: str,
    instruments: dict[str, dict[str, Any]],
) -> None:
    columns = _table_columns(conn, table)
    if "ticker" not in columns:
        return
    source_column = "source_market" if "source_market" in columns else "source"
    for raw in conn.execute(f"SELECT DISTINCT ticker, {source_column} AS source_market FROM {table}").fetchall():
        ticker = str(raw["ticker"] or "").strip().upper()
        if not ticker:
            continue
        source_market = str(raw["source_market"] or "").strip().upper()
        asset_type = infer_asset_type(ticker)
        market = instrument_market(asset_type, ".TWO" if source_market == "TPEX" else ".TW", source_market)
        if asset_type == "ETF":
            market = "ETF"
        instrument_id = instrument_id_for(ticker, market)
        instruments.setdefault(
            instrument_id,
            {
                "instrument_id": instrument_id,
                "ticker": ticker,
                "market": market,
                "type": asset_type,
                "name": ticker,
                "yahoo_symbol": yahoo_symbol(ticker, exchange_suffix_for_market(market)),
                "listing_date": "",
                "delisting_date": "",
                "status": "active",
                "source": "migration",
                "created_at": now_iso(),
                "updated_at": now_iso(),
            },
        )


def _insert_migrated_instruments(conn: sqlite3.Connection, instruments: dict[str, dict[str, Any]]) -> int:
    before = conn.total_changes
    conn.executemany(
        """
        INSERT INTO instruments (
            instrument_id, ticker, market, type, name, yahoo_symbol, listing_date,
            delisting_date, status, source, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(instrument_id) DO UPDATE SET
            ticker = excluded.ticker,
            market = excluded.market,
            type = excluded.type,
            name = excluded.name,
            yahoo_symbol = excluded.yahoo_symbol,
            listing_date = COALESCE(NULLIF(excluded.listing_date, ''), instruments.listing_date),
            delisting_date = COALESCE(NULLIF(excluded.delisting_date, ''), instruments.delisting_date),
            status = excluded.status,
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
                row["yahoo_symbol"],
                row.get("listing_date") or None,
                row.get("delisting_date") or None,
                row.get("status") or "active",
                row.get("source") or "migration",
                row.get("created_at") or now_iso(),
                row.get("updated_at") or now_iso(),
            )
            for row in instruments.values()
        ],
    )
    return conn.total_changes - before


def _copy_legacy_ohlcv_daily(
    conn: sqlite3.Connection,
    table: str | None,
    instruments: dict[str, dict[str, Any]],
) -> int:
    if not table:
        return 0
    before = conn.total_changes
    rows = []
    for raw in conn.execute(f"SELECT * FROM {table}").fetchall():
        item = dict(raw)
        instrument = _legacy_instrument_for_row(item, instruments)
        if not instrument:
            continue
        trade_date = item.get("trade_date")
        if not trade_date:
            continue
        fetched_at = timestamp_to_iso(item.get("fetched_at_ts")) or now_iso()
        rows.append(
            (
                instrument["instrument_id"],
                trade_date,
                item.get("open"),
                item.get("high"),
                item.get("low"),
                item.get("close"),
                item.get("volume"),
                item.get("turnover"),
                item.get("source") or source_for_market(instrument["market"]),
                0,
                fetched_at,
                fetched_at,
            )
        )
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
        rows,
    )
    return conn.total_changes - before


def _copy_legacy_intraday(
    conn: sqlite3.Connection,
    table: str | None,
    instruments: dict[str, dict[str, Any]],
) -> int:
    if not table:
        return 0
    before = conn.total_changes
    rows = []
    for raw in conn.execute(f"SELECT * FROM {table}").fetchall():
        item = dict(raw)
        instrument = _legacy_instrument_for_row(item, instruments)
        if not instrument:
            continue
        bar_time = item.get("bar_time")
        if not bar_time:
            continue
        fetched_at = timestamp_to_iso(item.get("fetched_at_ts")) or now_iso()
        rows.append(
            (
                instrument["instrument_id"],
                bar_time,
                item.get("open"),
                item.get("high"),
                item.get("low"),
                item.get("close"),
                item.get("volume"),
                item.get("source") or "YAHOO",
                fetched_at,
            )
        )
    conn.executemany(
        """
        INSERT INTO ohlcv_intraday_15m (
            instrument_id, datetime, open, high, low, close, volume, source, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(instrument_id, datetime) DO UPDATE SET
            open = excluded.open,
            high = excluded.high,
            low = excluded.low,
            close = excluded.close,
            volume = excluded.volume,
            source = excluded.source
        """,
        rows,
    )
    return conn.total_changes - before


def _copy_legacy_snapshots(
    conn: sqlite3.Connection,
    table: str | None,
    instruments: dict[str, dict[str, Any]],
) -> int:
    if not table:
        return 0
    before = conn.total_changes
    rows = []
    for raw in conn.execute(f"SELECT * FROM {table}").fetchall():
        item = dict(raw)
        instrument = _legacy_instrument_for_row(item, instruments)
        if not instrument:
            continue
        captured_at = item.get("captured_at")
        if not captured_at:
            continue
        fetched_at = timestamp_to_iso(item.get("fetched_at_ts")) or now_iso()
        rows.append(
            (
                instrument["instrument_id"],
                captured_at,
                item.get("close"),
                item.get("change"),
                item.get("change_pct"),
                item.get("source") or "YAHOO",
                fetched_at,
            )
        )
    conn.executemany(
        """
        INSERT INTO quote_snapshots_15m (
            instrument_id, snapshot_time, price, change, change_pct, source, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(instrument_id, snapshot_time) DO UPDATE SET
            price = excluded.price,
            change = excluded.change,
            change_pct = excluded.change_pct,
            source = excluded.source
        """,
        rows,
    )
    return conn.total_changes - before


def _copy_legacy_after_close(
    conn: sqlite3.Connection,
    table: str | None,
    instruments: dict[str, dict[str, Any]],
) -> int:
    if not table:
        return 0
    before = conn.total_changes
    rows = []
    for raw in conn.execute(f"SELECT * FROM {table}").fetchall():
        item = dict(raw)
        instrument = _legacy_instrument_for_row(item, instruments)
        if not instrument:
            continue
        trade_date = item.get("trade_date")
        if not trade_date:
            continue
        fetched_at = timestamp_to_iso(item.get("fetched_at_ts")) or now_iso()
        rows.append(
            (
                instrument["instrument_id"],
                trade_date,
                item.get("close"),
                item.get("change"),
                item.get("change_pct"),
                item.get("source") or "YAHOO",
                fetched_at,
            )
        )
    conn.executemany(
        """
        INSERT INTO after_close_quotes (
            instrument_id, quote_date, price, change, change_pct, source, created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(instrument_id, quote_date) DO UPDATE SET
            price = excluded.price,
            change = excluded.change,
            change_pct = excluded.change_pct,
            source = excluded.source
        """,
        rows,
    )
    return conn.total_changes - before


def _copy_legacy_quotes(
    conn: sqlite3.Connection,
    table: str | None,
    instruments: dict[str, dict[str, Any]],
) -> int:
    if not table:
        return 0
    before = conn.total_changes
    symbol_to_instrument = {
        str(row["yahoo_symbol"]).upper(): row["instrument_id"]
        for row in instruments.values()
        if row.get("yahoo_symbol")
    }
    rows = []
    for raw in conn.execute(f"SELECT * FROM {table}").fetchall():
        item = dict(raw)
        symbol = str(item.get("symbol") or "").strip().upper()
        instrument_id = symbol_to_instrument.get(symbol)
        if not instrument_id:
            continue
        try:
            quote = json.loads(item.get("quote_json") or "{}")
        except json.JSONDecodeError:
            continue
        updated_at = timestamp_to_iso(item.get("updated_at_ts")) or now_iso()
        rows.append(
            (
                instrument_id,
                quote.get("close"),
                quote.get("change"),
                quote.get("change_pct"),
                str(quote.get("price_time") or quote.get("fetched_at") or "")[:10],
                str(quote.get("price_time") or quote.get("fetched_at") or ""),
                quote.get("source") or "YAHOO",
                updated_at,
            )
        )
    conn.executemany(
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
        rows,
    )
    return conn.total_changes - before


def _legacy_instrument_for_row(
    row: dict[str, Any],
    instruments: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    ticker = str(row.get("ticker") or "").strip().upper()
    if not ticker:
        return None
    source_market = str(row.get("source_market") or "").strip().upper()
    asset_type = infer_asset_type(ticker)
    market = "ETF" if asset_type == "ETF" else instrument_market(asset_type, ".TW", source_market)
    instrument_id = instrument_id_for(ticker, market)
    return instruments.get(instrument_id)


def legacy_instrument_status(value: object) -> str:
    text = str(value or "").strip()
    if text == "delisted":
        return "delisted"
    if text == "suspect_delisted":
        return "delisted_candidate"
    if text == "fetch_error":
        return "manual_review"
    return "active"


def source_for_market(market: str) -> str:
    market = str(market or "").strip().upper()
    if market == "TPEX":
        return "TPEX"
    if market in {"TWSE", "ETF"}:
        return "TWSE"
    return market or "UNKNOWN"


def timestamp_to_iso(value: object) -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return ""
    if number <= 0:
        return ""
    return datetime.fromtimestamp(number).astimezone().isoformat(timespec="seconds")


def iso_to_timestamp(value: object) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text).timestamp()
    except ValueError:
        return 0.0


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    return row is not None


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}



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
    success_delta = int(normalized_status == "success")
    fail_delta = int(normalized_status == "failed")
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
    record_operation_log(
        path,
        job_name=job_name,
        source=source,
        event_type="update_status",
        status=normalized_status,
        started_at=started_at,
        finished_at=finished_at,
        summary=message,
        details=message,
    )


def record_operation_log(
    path: Path,
    job_name: str,
    source: str,
    event_type: str,
    status: str,
    started_at: str = "",
    finished_at: str = "",
    summary: str = "",
    details: str = "",
) -> None:
    ensure_central_db(path)
    db_path = _operation_log_db_path(path)
    normalized_status = "success" if status == "success" else "failed"
    started = str(started_at or "")
    finished = str(finished_at or now_iso())
    duration_ms = _duration_ms(started, finished)
    summary_text = _compact_log_text(summary or details, 180)
    details_text = _compact_log_text(details or summary, 4000)
    with sqlite3.connect(db_path) as conn:
        _create_market_schema(conn)
        conn.execute(
            """
            INSERT INTO operation_logs (
                job_name,
                source,
                event_type,
                status,
                started_at,
                finished_at,
                duration_ms,
                summary,
                details,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(job_name or "").strip() or "unknown",
                str(source or "").strip(),
                str(event_type or "").strip() or "operation",
                normalized_status,
                started,
                finished,
                duration_ms,
                summary_text,
                details_text,
                now_iso(),
            ),
        )
        conn.execute(
            """
            DELETE FROM operation_logs
            WHERE id NOT IN (
                SELECT id
                FROM operation_logs
                ORDER BY finished_at DESC, id DESC
                LIMIT 100
            )
            """
        )


def list_operation_logs(
    path: Path,
    limit: int = 100,
    offset: int = 0,
    status: str = "",
    job_name: str = "",
) -> dict[str, Any]:
    ensure_central_db(path)
    db_path = _operation_log_db_path(path)
    normalized_limit = max(min(int(limit or 100), 300), 1)
    normalized_offset = max(int(offset or 0), 0)
    clauses: list[str] = []
    params: list[Any] = []
    if status:
        clauses.append("status = ?")
        params.append(status)
    if job_name:
        clauses.append("job_name = ?")
        params.append(job_name)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        _create_market_schema(conn)
        total = conn.execute(f"SELECT COUNT(*) AS count FROM operation_logs {where}", params).fetchone()["count"]
        rows = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM operation_logs
                {where}
                ORDER BY finished_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, normalized_limit, normalized_offset],
            ).fetchall()
        ]
    return {
        "logs": rows,
        "pagination": {
            "limit": normalized_limit,
            "offset": normalized_offset,
            "returned": len(rows),
            "total": int(total or 0),
            "has_more": normalized_offset + len(rows) < int(total or 0),
        },
    }


def record_uploaded_document(
    path: Path,
    *,
    profile_slug: str,
    original_filename: str,
    stored_path: str,
    mime_type: str,
    file_size: int,
    sha256: str,
    source: str = "manual_upload",
    status: str = "stored",
    note: str = "",
) -> dict[str, Any]:
    ensure_central_db(path)
    db_path = _operation_log_db_path(path)
    created_at = now_iso()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        _create_market_schema(conn)
        existing = conn.execute(
            "SELECT * FROM uploaded_documents WHERE sha256 = ? AND profile_slug = ?",
            (sha256, profile_slug),
        ).fetchone()
        if existing:
            row = dict(existing)
            conn.execute(
                """
                UPDATE uploaded_documents
                SET last_seen_at = ?, note = COALESCE(NULLIF(?, ''), note)
                WHERE id = ?
                """,
                (created_at, note, row["id"]),
            )
            row["duplicate"] = True
            row["last_seen_at"] = created_at
            return row
        cursor = conn.execute(
            """
            INSERT INTO uploaded_documents (
                profile_slug, original_filename, stored_path, mime_type,
                file_size, sha256, source, status, note, created_at, updated_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                profile_slug,
                original_filename,
                stored_path,
                mime_type,
                int(file_size or 0),
                sha256,
                source,
                status,
                note,
                created_at,
                created_at,
                created_at,
            ),
        )
        row = conn.execute("SELECT * FROM uploaded_documents WHERE id = ?", (cursor.lastrowid,)).fetchone()
    result = dict(row)
    result["duplicate"] = False
    return result


def list_uploaded_documents(
    path: Path,
    limit: int = 80,
    offset: int = 0,
    profile_slug: str = "",
    status: str = "",
) -> dict[str, Any]:
    ensure_central_db(path)
    db_path = _operation_log_db_path(path)
    normalized_limit = max(min(int(limit or 80), 300), 1)
    normalized_offset = max(int(offset or 0), 0)
    clauses: list[str] = []
    params: list[Any] = []
    if profile_slug:
        clauses.append("profile_slug = ?")
        params.append(profile_slug)
    if status:
        clauses.append("status = ?")
        params.append(status)
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        _create_market_schema(conn)
        total = conn.execute(f"SELECT COUNT(*) AS count FROM uploaded_documents {where}", params).fetchone()["count"]
        rows = [
            dict(row)
            for row in conn.execute(
                f"""
                SELECT *
                FROM uploaded_documents
                {where}
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                [*params, normalized_limit, normalized_offset],
            ).fetchall()
        ]
    return {
        "uploads": rows,
        "pagination": {
            "limit": normalized_limit,
            "offset": normalized_offset,
            "returned": len(rows),
            "total": int(total or 0),
            "has_more": normalized_offset + len(rows) < int(total or 0),
        },
    }


def get_uploaded_document(path: Path, upload_id: int) -> dict[str, Any] | None:
    ensure_central_db(path)
    db_path = _operation_log_db_path(path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        _create_market_schema(conn)
        row = conn.execute("SELECT * FROM uploaded_documents WHERE id = ?", (int(upload_id),)).fetchone()
    return dict(row) if row else None


def get_gmail_attachment_receipt(
    path: Path,
    *,
    profile_slug: str,
    message_id: str,
    original_filename: str,
) -> dict[str, Any] | None:
    ensure_central_db(path)
    db_path = _operation_log_db_path(path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        _create_market_schema(conn)
        row = conn.execute(
            """
            SELECT *
            FROM gmail_attachment_receipts
            WHERE profile_slug = ? AND message_id = ? AND original_filename = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (profile_slug, message_id, original_filename),
        ).fetchone()
    return dict(row) if row else None


def get_gmail_statement_receipt(
    path: Path,
    *,
    profile_slug: str,
    statement_date: str,
) -> dict[str, Any] | None:
    ensure_central_db(path)
    db_path = _operation_log_db_path(path)
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        _create_market_schema(conn)
        row = conn.execute(
            """
            SELECT *
            FROM gmail_attachment_receipts
            WHERE profile_slug = ? AND statement_date = ? AND status IN ('stored', 'duplicate_hash')
            ORDER BY downloaded_at DESC, id DESC
            LIMIT 1
            """,
            (profile_slug, statement_date),
        ).fetchone()
    return dict(row) if row else None


def record_gmail_attachment_receipt(
    path: Path,
    *,
    profile_slug: str,
    message_id: str,
    attachment_id: str,
    original_filename: str,
    statement_date: str,
    sha256: str,
    upload_id: int | None,
    status: str,
    note: str = "",
) -> dict[str, Any]:
    ensure_central_db(path)
    db_path = _operation_log_db_path(path)
    timestamp = now_iso()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        _create_market_schema(conn)
        conn.execute(
            """
            INSERT INTO gmail_attachment_receipts (
                profile_slug, message_id, attachment_id, original_filename,
                statement_date, sha256, upload_id, status, note,
                downloaded_at, last_seen_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(profile_slug, message_id, attachment_id) DO UPDATE SET
                original_filename = excluded.original_filename,
                statement_date = excluded.statement_date,
                sha256 = excluded.sha256,
                upload_id = COALESCE(excluded.upload_id, gmail_attachment_receipts.upload_id),
                status = excluded.status,
                note = excluded.note,
                last_seen_at = excluded.last_seen_at
            """,
            (
                profile_slug,
                message_id,
                attachment_id,
                original_filename,
                statement_date,
                sha256,
                upload_id,
                status,
                note,
                timestamp,
                timestamp,
            ),
        )
        row = conn.execute(
            """
            SELECT * FROM gmail_attachment_receipts
            WHERE profile_slug = ? AND message_id = ? AND attachment_id = ?
            """,
            (profile_slug, message_id, attachment_id),
        ).fetchone()
    return dict(row)


def update_uploaded_document_status(
    path: Path,
    upload_id: int,
    *,
    status: str,
    note: str = "",
) -> dict[str, Any]:
    ensure_central_db(path)
    db_path = _operation_log_db_path(path)
    normalized = str(status or "").strip() or "stored"
    updated_at = now_iso()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        _create_market_schema(conn)
        conn.execute(
            """
            UPDATE uploaded_documents
            SET status = ?, note = COALESCE(NULLIF(?, ''), note), updated_at = ?
            WHERE id = ?
            """,
            (normalized, note, updated_at, int(upload_id)),
        )
        row = conn.execute("SELECT * FROM uploaded_documents WHERE id = ?", (int(upload_id),)).fetchone()
    if not row:
        raise ValueError("uploaded document not found")
    return dict(row)


def _operation_log_db_path(path: Path) -> Path:
    if _is_legacy_file(path):
        return path
    return segment_db_paths(path)["etf"]


def _compact_log_text(value: object, max_length: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 1] + "…"


def _duration_ms(started_at: str, finished_at: str) -> int | None:
    try:
        started = datetime.fromisoformat(started_at)
        finished = datetime.fromisoformat(finished_at)
    except ValueError:
        return None
    return max(int((finished - started).total_seconds() * 1000), 0)


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
                ("ohlcv_daily", "date", daily_cutoff.isoformat()),
                ("quote_snapshots_15m", "snapshot_time", intraday_cutoff.isoformat()),
                ("ohlcv_intraday_15m", "datetime", intraday_cutoff.isoformat()),
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
    asset_type = str(asset_type or inferred_type).strip().upper()
    market = instrument_market(asset_type, exchange_suffix)
    incoming = {
        "instrument_id": instrument_id_for(ticker, market),
        "ticker": ticker,
        "market": market,
        "yahoo_symbol": yahoo_symbol(ticker, exchange_suffix),
        "name": clean_name(name, ticker),
        "type": asset_type,
        "source": source,
        "listing_date": "",
        "delisting_date": "",
        "status": "active",
        "created_at": now_iso(),
        "updated_at": now_iso(),
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
            row = normalize_instrument_output(row)
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
            return normalize_instrument_output(dict(row))
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
    market = instrument_market(asset_type, exchange_suffix)

    row = {
        "instrument_id": instrument_id_for(ticker, market),
        "ticker": ticker,
        "market": market,
        "yahoo_symbol": yahoo_symbol(ticker, exchange_suffix),
        "name": clean_name(name, ticker),
        "type": asset_type,
        "source": source,
        "listing_date": str(listing_date or "").strip(),
        "delisting_date": "",
        "status": "active",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    return _upsert_instrument(path, row)


def list_instruments(
    path: Path,
    quote_cache: dict[str, dict[str, Any]] | None = None,
    limit: int | None = None,
    offset: int = 0,
    q: str = "",
    asset_type: str = "",
    market: str = "",
    exchange_suffix: str = "",
    history_status: str = "",
) -> list[dict[str, Any]]:
    ensure_central_db(path)
    quote_cache = quote_cache or {}
    rows: list[dict[str, Any]] = []
    for segment, db_path in segment_db_paths(path).items():
        try:
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                clauses = []
                params: list[Any] = []
                if q:
                    clauses.append("(i.ticker LIKE ? OR i.name LIKE ? OR i.yahoo_symbol LIKE ?)")
                    keyword = f"%{q}%"
                    params.extend([keyword, keyword, keyword])
                if asset_type:
                    clauses.append("i.type = ?")
                    params.append(asset_type)
                if market:
                    clauses.append("i.market = ?")
                    params.append(market)
                if exchange_suffix:
                    if exchange_suffix not in {".TW", ".TWO"}:
                        clauses.append("1 = 0")
                    else:
                        clauses.append("i.yahoo_symbol LIKE ?")
                        params.append(f"%{exchange_suffix}")
                if history_status:
                    clauses.append("h.history_status = ?")
                    params.append(history_status)
                where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
                records = conn.execute(
                    f"""
                    SELECT
                        i.instrument_id,
                        i.ticker,
                        i.market,
                        i.yahoo_symbol,
                        i.name,
                        i.type,
                        i.source,
                        i.listing_date,
                        i.delisting_date,
                        i.status,
                        i.created_at,
                        i.updated_at,
                        h.daily_rows,
                        h.first_daily_date,
                        h.last_daily_date,
                        h.expected_start_date,
                        h.expected_end_date,
                        h.history_status,
                        h.recent_data_ok,
                        h.missing_month_count,
                        h.first_missing_month,
                        h.missing_months_json,
                        h.last_checked_at,
                        h.last_success_at,
                        h.last_error,
                        h.retry_count,
                        h.next_retry_at,
                        h.manual_review_required,
                        q.price,
                        q.change,
                        q.change_pct,
                        q.quote_date,
                        q.quote_time,
                        q.source AS quote_source,
                        q.updated_at AS quote_updated_at,
                        issue.issue_count,
                        issue.latest_issue,
                        action.corporate_action_count,
                        action.latest_corporate_action_date,
                        action.latest_corporate_action_type
                    FROM instruments i
                    LEFT JOIN instrument_health_summary h ON h.instrument_id = i.instrument_id
                    LEFT JOIN quotes q ON q.instrument_id = i.instrument_id
                    LEFT JOIN (
                        SELECT instrument_id, COUNT(*) AS issue_count, MAX(message) AS latest_issue
                        FROM market_data_issues
                        WHERE resolved_at IS NULL
                        GROUP BY instrument_id
                    ) issue ON issue.instrument_id = i.instrument_id
                    LEFT JOIN (
                        SELECT
                            instrument_id,
                            COUNT(*) AS corporate_action_count,
                            MAX(effective_date) AS latest_corporate_action_date,
                            MAX(action_type) AS latest_corporate_action_type
                        FROM instrument_corporate_actions
                        GROUP BY instrument_id
                    ) action ON action.instrument_id = i.instrument_id
                    {where}
                    ORDER BY i.ticker
                    """,
                    params,
                ).fetchall()
        except sqlite3.DatabaseError:
            continue

        for record in records:
            row = normalize_instrument_output(dict(record))
            cached_quote = quote_cache.get(row["symbol"], {})
            row["close"] = row.get("price") if row.get("price") is not None else cached_quote.get("close")
            row["price_time"] = row.get("quote_time") or row.get("quote_date") or cached_quote.get("price_time", "")
            row["quote_status"] = ""
            row["quote_error"] = row.get("last_error") or ""
            row["daily_bar_count"] = row.get("daily_rows") or 0
            row["daily_first_date"] = row.get("first_daily_date")
            row["daily_last_date"] = row.get("last_daily_date")
            rows.append(row)
    rows = sorted(rows, key=lambda row: str(row["ticker"]))
    if limit is not None:
        start = max(int(offset or 0), 0)
        end = start + max(int(limit), 0)
        return rows[start:end]
    return rows


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
        fallback = latest_daily_quote(path, ticker)
        if not fallback:
            continue
        if current.get("close") is None:
            patched[symbol] = fallback
            continue
        if ticker not in forced:
            continue
        current_date = quote_record_date(current)
        fallback_date = quote_record_date(fallback)
        same_day_official = (
            current_date
            and fallback_date
            and fallback_date == current_date
            and is_official_tw_daily_quote(fallback, instrument)
        )
        if current_date and fallback_date and fallback_date < current_date:
            continue
        if current_date and fallback_date and fallback_date == current_date and not same_day_official:
            continue
        patched[symbol] = fallback
    return patched


def is_official_tw_daily_quote(quote: dict[str, Any], instrument: dict[str, Any]) -> bool:
    market = str(instrument.get("market") or "").strip().upper()
    daily_source = str(quote.get("daily_source") or "").strip().upper()
    return (
        market in {"TWSE", "TPEX", "ETF"}
        and quote.get("source") == "official_daily_fallback"
        and daily_source in {"TWSE_STOCK_DAY", "TPEX_TRADING_STOCK"}
    )


def quote_record_date(quote: dict[str, Any]) -> str:
    for key in ("price_time", "fetched_at", "quote_date"):
        value = str(quote.get(key) or "").strip()
        if len(value) >= 10 and value[4:5] == "-" and value[7:8] == "-":
            return value[:10]
    return ""


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
        "daily_source": latest.get("source", ""),
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
            rows = conn.execute(
                """
                SELECT i.yahoo_symbol, q.*
                FROM quotes q
                JOIN instruments i ON i.instrument_id = q.instrument_id
                """
            ).fetchall()
        cache: dict[str, dict[str, Any]] = {}
        for row in rows:
            symbol = row["yahoo_symbol"]
            if not symbol:
                continue
            cache[symbol] = {
                "close": row["price"],
                "change": row["change"],
                "change_pct": row["change_pct"],
                "price_time": row["quote_time"] or row["quote_date"],
                "source": row["source"],
                "fetched_at": row["updated_at"],
            }
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
        updated_at = now_iso()
        with sqlite3.connect(path) as conn:
            for symbol, quote in cache.items():
                instrument = conn.execute(
                    "SELECT instrument_id FROM instruments WHERE yahoo_symbol = ?",
                    (symbol,),
                ).fetchone()
                if not instrument:
                    continue
                quote_time = str(quote.get("price_time") or quote.get("fetched_at") or "")
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
                        instrument[0],
                        quote.get("close"),
                        quote.get("change"),
                        quote.get("change_pct"),
                        quote_time[:10],
                        quote_time,
                        quote.get("source") or "YAHOO",
                        updated_at,
                    ),
                )
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def upsert_ohlcv_daily(path: Path, rows: list[dict[str, Any]]) -> int:
    ensure_central_db(path)
    if not rows:
        return 0
    current = now_iso()
    rows_by_path: dict[Path, list[dict[str, Any]]] = {}
    for row in rows:
        instrument = ensure_instrument_for_market_row(path, row)
        db_path = _db_path_for_ticker(path, instrument["ticker"], row.get("source_market"))
        rows_by_path.setdefault(db_path, []).append({**row, "_instrument": instrument})

    for db_path, batch in rows_by_path.items():
        with sqlite3.connect(db_path) as conn:
            conn.executemany(
                """
                INSERT INTO ohlcv_daily (
                    instrument_id,
                    date,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    value,
                    source,
                    adjusted,
                    created_at,
                    updated_at
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
                        row["_instrument"]["instrument_id"],
                        row.get("date") or row["trade_date"],
                        row.get("open"),
                        row.get("high"),
                        row.get("low"),
                        row.get("close"),
                        row.get("volume"),
                        row.get("value", row.get("turnover")),
                        row.get("source", ""),
                        int(row.get("adjusted", 0) or 0),
                        timestamp_to_iso(row.get("fetched_at_ts")) or current,
                        current,
                    )
                    for row in batch
                ],
            )
            latest_by_instrument: dict[str, dict[str, Any]] = {}
            for row in batch:
                key = row["_instrument"]["instrument_id"]
                if key not in latest_by_instrument or str(row.get("trade_date", "")) > str(latest_by_instrument[key].get("trade_date", "")):
                    latest_by_instrument[key] = row
            conn.executemany(
                """
                INSERT INTO quotes (
                    instrument_id, price, change, change_pct, quote_date, quote_time, source, updated_at
                )
                VALUES (?, ?, NULL, NULL, ?, ?, ?, ?)
                ON CONFLICT(instrument_id) DO UPDATE SET
                    price = excluded.price,
                    quote_date = excluded.quote_date,
                    quote_time = excluded.quote_time,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                [
                    (
                        row["_instrument"]["instrument_id"],
                        row.get("close"),
                        row.get("date") or row.get("trade_date"),
                        row.get("date") or row.get("trade_date"),
                        source_for_market(row["_instrument"]["market"]),
                        current,
                    )
                    for row in latest_by_instrument.values()
                    if row.get("close") is not None
                ],
            )
    return len(rows)


def upsert_ohlcv_intraday_15m(path: Path, rows: list[dict[str, Any]]) -> int:
    ensure_central_db(path)
    if not rows:
        return 0
    current = now_iso()
    rows_by_path: dict[Path, list[dict[str, Any]]] = {}
    for row in rows:
        instrument = ensure_instrument_for_market_row(path, row)
        db_path = _db_path_for_ticker(path, instrument["ticker"], row.get("source_market"))
        rows_by_path.setdefault(db_path, []).append({**row, "_instrument": instrument})

    for db_path, batch in rows_by_path.items():
        with sqlite3.connect(db_path) as conn:
            conn.executemany(
                """
                INSERT INTO ohlcv_intraday_15m (
                    instrument_id,
                    datetime,
                    open,
                    high,
                    low,
                    close,
                    volume,
                    source,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(instrument_id, datetime) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    source = excluded.source
                """,
                [
                    (
                        row["_instrument"]["instrument_id"],
                        row["bar_time"],
                        row.get("open"),
                        row.get("high"),
                        row.get("low"),
                        row.get("close"),
                        row.get("volume"),
                        row.get("source", ""),
                        timestamp_to_iso(row.get("fetched_at_ts")) or current,
                    )
                    for row in batch
                ],
            )
    return len(rows)


def upsert_quote_snapshots_15m(path: Path, rows: list[dict[str, Any]]) -> int:
    ensure_central_db(path)
    if not rows:
        return 0
    current = now_iso()
    rows_by_path: dict[Path, list[dict[str, Any]]] = {}
    for row in rows:
        instrument = ensure_instrument_for_market_row(path, row)
        db_path = _db_path_for_ticker(path, instrument["ticker"], row.get("source_market"))
        rows_by_path.setdefault(db_path, []).append({**row, "_instrument": instrument})

    for db_path, batch in rows_by_path.items():
        with sqlite3.connect(db_path) as conn:
            conn.executemany(
                """
                INSERT INTO quote_snapshots_15m (
                    instrument_id,
                    snapshot_time,
                    price,
                    change,
                    change_pct,
                    source,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(instrument_id, snapshot_time) DO UPDATE SET
                    price = excluded.price,
                    change = excluded.change,
                    change_pct = excluded.change_pct,
                    source = excluded.source
                """,
                [
                    (
                        row["_instrument"]["instrument_id"],
                        row["captured_at"],
                        row.get("close"),
                        row.get("change"),
                        row.get("change_pct"),
                        row.get("source", ""),
                        timestamp_to_iso(row.get("fetched_at_ts")) or current,
                    )
                    for row in batch
                ],
            )
            latest_by_instrument: dict[str, dict[str, Any]] = {}
            for row in batch:
                key = row["_instrument"]["instrument_id"]
                if key not in latest_by_instrument or str(row.get("captured_at", "")) > str(latest_by_instrument[key].get("captured_at", "")):
                    latest_by_instrument[key] = row
            conn.executemany(
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
                [
                    (
                        row["_instrument"]["instrument_id"],
                        row.get("close"),
                        row.get("change"),
                        row.get("change_pct"),
                        str(row.get("trade_date") or row.get("captured_at") or "")[:10],
                        row.get("captured_at"),
                        row.get("source", "YAHOO"),
                        current,
                    )
                    for row in latest_by_instrument.values()
                    if row.get("close") is not None
                ],
            )
    return len(rows)


def upsert_after_close_quotes(path: Path, rows: list[dict[str, Any]]) -> int:
    ensure_central_db(path)
    if not rows:
        return 0
    current = now_iso()
    rows_by_path: dict[Path, list[dict[str, Any]]] = {}
    for row in rows:
        instrument = ensure_instrument_for_market_row(path, row)
        db_path = _db_path_for_ticker(path, instrument["ticker"], row.get("source_market"))
        rows_by_path.setdefault(db_path, []).append({**row, "_instrument": instrument})

    for db_path, batch in rows_by_path.items():
        with sqlite3.connect(db_path) as conn:
            conn.executemany(
                """
                INSERT INTO after_close_quotes (
                    instrument_id,
                    quote_date,
                    price,
                    change,
                    change_pct,
                    source,
                    created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(instrument_id, quote_date) DO UPDATE SET
                    price = excluded.price,
                    change = excluded.change,
                    change_pct = excluded.change_pct,
                    source = excluded.source
                """,
                [
                    (
                        row["_instrument"]["instrument_id"],
                        row["trade_date"],
                        row.get("close"),
                        row.get("change"),
                        row.get("change_pct"),
                        row.get("source", ""),
                        timestamp_to_iso(row.get("fetched_at_ts")) or current,
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


def ensure_etf_holdings_schema(path: Path) -> None:
    ensure_central_db(path)
    db_path = segment_db_paths(path)["etf"]
    conn = sqlite3.connect(db_path)
    try:
        _create_etf_holdings_schema(conn)
        _create_etf_holdings_indexes(conn)
        conn.commit()
    finally:
        conn.close()


def upsert_etf_holding_snapshot(
    path: Path,
    *,
    etf_ticker: str,
    as_of_date: str,
    source: str,
    rows: list[dict[str, Any]],
    source_url: str = "",
    status: str = "ok",
    notes: str = "",
) -> dict[str, Any]:
    ensure_etf_holdings_schema(path)
    ticker = str(etf_ticker or "").strip().upper()
    as_of = str(as_of_date or "").strip()[:10]
    normalized_source = str(source or "manual").strip() or "manual"
    if not ticker:
        raise ValueError("etf_ticker is required")
    if not as_of:
        raise ValueError("as_of_date is required")

    components = [_normalize_etf_component_row(ticker, as_of, normalized_source, row, index) for index, row in enumerate(rows, 1)]
    current = now_iso()
    db_path = segment_db_paths(path)["etf"]
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        existing = conn.execute(
            """
            SELECT id, created_at
            FROM etf_holding_snapshots
            WHERE etf_ticker = ? AND as_of_date = ? AND source = ?
            """,
            (ticker, as_of, normalized_source),
        ).fetchone()
        created_at = existing["created_at"] if existing else current
        conn.execute(
            """
            INSERT INTO etf_holding_snapshots (
                etf_ticker, as_of_date, source, source_url, status,
                row_count, created_at, updated_at, notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(etf_ticker, as_of_date, source) DO UPDATE SET
                source_url = excluded.source_url,
                status = excluded.status,
                row_count = excluded.row_count,
                updated_at = excluded.updated_at,
                notes = excluded.notes
            """,
            (
                ticker,
                as_of,
                normalized_source,
                str(source_url or ""),
                str(status or "ok"),
                len(components),
                created_at,
                current,
                str(notes or ""),
            ),
        )
        snapshot = conn.execute(
            """
            SELECT *
            FROM etf_holding_snapshots
            WHERE etf_ticker = ? AND as_of_date = ? AND source = ?
            """,
            (ticker, as_of, normalized_source),
        ).fetchone()
        snapshot_id = int(snapshot["id"])
        conn.execute("DELETE FROM etf_holding_components WHERE snapshot_id = ?", (snapshot_id,))
        conn.executemany(
            """
            INSERT INTO etf_holding_components (
                snapshot_id, etf_ticker, as_of_date, source,
                constituent_ticker, constituent_name, weight, shares,
                market_value, industry, sort_order, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    snapshot_id,
                    row["etf_ticker"],
                    row["as_of_date"],
                    row["source"],
                    row["constituent_ticker"],
                    row["constituent_name"],
                    row["weight"],
                    row["shares"],
                    row["market_value"],
                    row["industry"],
                    row["sort_order"],
                    current,
                )
                for row in components
            ],
        )
        conn.commit()
    finally:
        conn.close()
    result = get_etf_holding_snapshot(path, ticker, as_of)
    return result or {"snapshot": None, "components": []}


def get_etf_holding_snapshot(path: Path, ticker: str, as_of_date: str | None = None) -> dict[str, Any] | None:
    ensure_etf_holdings_schema(path)
    normalized = str(ticker or "").strip().upper()
    if not normalized:
        return None
    db_path = segment_db_paths(path)["etf"]
    params: list[Any] = [normalized]
    where = "etf_ticker = ?"
    if as_of_date and str(as_of_date).strip().lower() != "latest":
        where += " AND as_of_date = ?"
        params.append(str(as_of_date).strip()[:10])
    conn = sqlite3.connect(db_path)
    try:
        conn.row_factory = sqlite3.Row
        snapshot = conn.execute(
            f"""
            SELECT *
            FROM etf_holding_snapshots
            WHERE {where}
            ORDER BY as_of_date DESC, updated_at DESC, id DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
        if snapshot is None:
            return None
        components = conn.execute(
            """
            SELECT
                etf_ticker,
                as_of_date,
                source,
                constituent_ticker,
                constituent_name,
                weight,
                shares,
                market_value,
                industry,
                sort_order,
                created_at
            FROM etf_holding_components
            WHERE snapshot_id = ?
            ORDER BY sort_order, weight DESC, constituent_ticker
            """,
            (snapshot["id"],),
        ).fetchall()
    finally:
        conn.close()
    return {
        "snapshot": dict(snapshot),
        "components": [dict(row) for row in components],
    }


def _normalize_etf_component_row(
    etf_ticker: str,
    as_of_date: str,
    source: str,
    row: dict[str, Any],
    default_sort_order: int,
) -> dict[str, Any]:
    return {
        "etf_ticker": etf_ticker,
        "as_of_date": as_of_date,
        "source": source,
        "constituent_ticker": str(row.get("constituent_ticker") or "").strip().upper(),
        "constituent_name": str(row.get("constituent_name") or "").strip(),
        "weight": _optional_float(row.get("weight")),
        "shares": _optional_float(row.get("shares")),
        "market_value": _optional_float(row.get("market_value")),
        "industry": str(row.get("industry") or "").strip(),
        "sort_order": _optional_int(row.get("sort_order")) or default_sort_order,
    }


def _optional_float(value: Any) -> float | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return None


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
    normalized_status = "success" if status == "success" else "failed"
    record_operation_log(
        path,
        job_name=f"dividend_refresh:{ticker}",
        source=source,
        event_type="dividend_refresh",
        status=normalized_status,
        started_at=started_at,
        finished_at=finished_at,
        summary=f"{ticker} fetched={int(fetched_count or 0)} written={int(written_count or 0)}",
        details=message,
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
    instrument = get_instrument(path, ticker)
    if not instrument:
        return []
    db_path = segment_db_paths(path)[instrument["segment"]]
    clauses = ["instrument_id = ?"]
    params: list[Any] = [instrument["instrument_id"]]
    if start_date:
        clauses.append("date >= ?")
        params.append(start_date)
    if end_date:
        clauses.append("date <= ?")
        params.append(end_date)
    sql = f"""
        SELECT
            instrument_id,
            date AS trade_date,
            date,
            open,
            high,
            low,
            close,
            volume,
            value AS turnover,
            source,
            created_at,
            updated_at
        FROM ohlcv_daily
        WHERE {' AND '.join(clauses)}
        ORDER BY date DESC
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
    instrument = get_instrument(path, ticker)
    if not instrument:
        return []
    db_path = segment_db_paths(path)[instrument["segment"]]
    clauses = ["instrument_id = ?"]
    params: list[Any] = [instrument["instrument_id"]]
    if start_time:
        clauses.append("datetime >= ?")
        params.append(start_time)
    if end_time:
        clauses.append("datetime <= ?")
        params.append(end_time)
    sql = f"""
        SELECT
            instrument_id,
            datetime AS bar_time,
            substr(datetime, 1, 10) AS trade_date,
            open, high, low, close, volume, source, created_at
        FROM ohlcv_intraday_15m
        WHERE {' AND '.join(clauses)}
        ORDER BY datetime DESC
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
    instrument = get_instrument(path, ticker)
    if not instrument:
        return []
    db_path = segment_db_paths(path)[instrument["segment"]]
    clauses = ["instrument_id = ?"]
    params: list[Any] = [instrument["instrument_id"]]
    if start_time:
        clauses.append("snapshot_time >= ?")
        params.append(start_time)
    if end_time:
        clauses.append("snapshot_time <= ?")
        params.append(end_time)
    sql = f"""
        SELECT
            instrument_id,
            snapshot_time AS captured_at,
            substr(snapshot_time, 1, 10) AS trade_date,
            price AS close,
            change,
            change_pct,
            source,
            created_at
        FROM quote_snapshots_15m
        WHERE {' AND '.join(clauses)}
        ORDER BY snapshot_time DESC
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
    instrument = get_instrument(path, ticker)
    if not instrument:
        return None
    db_path = segment_db_paths(path)[instrument["segment"]]
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT
                instrument_id,
                quote_date AS trade_date,
                quote_date AS captured_at,
                price AS close,
                change,
                change_pct,
                source,
                created_at
            FROM after_close_quotes
            WHERE instrument_id = ?
            ORDER BY quote_date DESC
            LIMIT 1
            """,
            (instrument["instrument_id"],),
        ).fetchone()
    return dict(row) if row else None


def ohlcv_daily_stats(path: Path, ticker: str) -> dict[str, Any]:
    ensure_central_db(path)
    instrument = get_instrument(path, ticker)
    if not instrument:
        return {"bar_count": 0, "first_date": None, "last_date": None}
    db_path = segment_db_paths(path)[instrument["segment"]]
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS bar_count,
                MIN(date) AS first_date,
                MAX(date) AS last_date
            FROM ohlcv_daily
            WHERE instrument_id = ?
            """,
            (instrument["instrument_id"],),
        ).fetchone()
    return dict(row) if row else {"bar_count": 0, "first_date": None, "last_date": None}


def ohlcv_daily_months(path: Path, ticker: str) -> set[str]:
    ensure_central_db(path)
    instrument = get_instrument(path, ticker)
    if not instrument:
        return set()
    db_path = segment_db_paths(path)[instrument["segment"]]
    with sqlite3.connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT DISTINCT substr(date, 1, 7) AS trade_month
            FROM ohlcv_daily
            WHERE instrument_id = ? AND date IS NOT NULL AND date != ''
            """,
            (instrument["instrument_id"],),
        ).fetchall()
    return {str(row[0]) for row in rows if row[0]}


def rebuild_health_summary(path: Path, today: date | None = None) -> list[dict[str, Any]]:
    ensure_central_db(path)
    today = today or date.today()
    results: list[dict[str, Any]] = []
    for segment, db_path in segment_db_paths(path).items():
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            instruments = [dict(row) for row in conn.execute("SELECT * FROM instruments ORDER BY ticker").fetchall()]
            for instrument in instruments:
                seed_quote_from_latest_daily(conn, instrument)
                summary = calculate_health_summary(conn, instrument, today)
                upsert_health_summary(conn, summary)
                sync_health_issues(conn, summary)
                results.append({**summary, "segment": segment})
    return results


def seed_quote_from_latest_daily(conn: sqlite3.Connection, instrument: dict[str, Any]) -> None:
    existing = conn.execute(
        "SELECT price FROM quotes WHERE instrument_id = ?",
        (instrument["instrument_id"],),
    ).fetchone()
    if existing and existing["price"] is not None:
        return
    rows = conn.execute(
        """
        SELECT date, close, source
        FROM ohlcv_daily
        WHERE instrument_id = ? AND close IS NOT NULL
        ORDER BY date DESC
        LIMIT 2
        """,
        (instrument["instrument_id"],),
    ).fetchall()
    if not rows:
        return
    latest = rows[0]
    previous = rows[1] if len(rows) > 1 else None
    change = safe_subtract(latest["close"], previous["close"] if previous else None)
    current = now_iso()
    conn.execute(
        """
        INSERT INTO quotes (
            instrument_id, price, change, change_pct, quote_date, quote_time, source, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(instrument_id) DO UPDATE SET
            price = COALESCE(quotes.price, excluded.price),
            change = COALESCE(quotes.change, excluded.change),
            change_pct = COALESCE(quotes.change_pct, excluded.change_pct),
            quote_date = COALESCE(quotes.quote_date, excluded.quote_date),
            quote_time = COALESCE(quotes.quote_time, excluded.quote_time),
            source = COALESCE(quotes.source, excluded.source),
            updated_at = COALESCE(quotes.updated_at, excluded.updated_at)
        """,
        (
            instrument["instrument_id"],
            latest["close"],
            change,
            pct(change, previous["close"] if previous else None),
            latest["date"],
            latest["date"],
            latest["source"] or source_for_market(instrument.get("market", "")),
            current,
        ),
    )


def check_market_db(path: Path) -> list[dict[str, Any]]:
    ensure_central_db(path)
    required_tables = {
        "instruments",
        "instrument_name_history",
        "instrument_aliases",
        "ohlcv_daily",
        "quotes",
        "ohlcv_intraday_15m",
        "quote_snapshots_15m",
        "after_close_quotes",
        "instrument_health_summary",
        "market_data_issues",
        "update_status",
        "operation_logs",
    }
    results: list[dict[str, Any]] = []
    for segment, db_path in segment_db_paths(path).items():
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            tables = {
                row["name"]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).fetchall()
            }
            for table in sorted(required_tables - tables):
                results.append(
                    {
                        "level": "error",
                        "segment": segment,
                        "database": str(db_path),
                        "check": "missing_table",
                        "message": f"missing table: {table}",
                    }
                )
            if "instruments" in tables and "instrument_id" not in _table_columns(conn, "instruments"):
                results.append(
                    {
                        "level": "error",
                        "segment": segment,
                        "database": str(db_path),
                        "check": "schema",
                        "message": "instruments missing instrument_id",
                    }
                )
            for table in (
                "ohlcv_daily",
                "quotes",
                "ohlcv_intraday_15m",
                "quote_snapshots_15m",
                "after_close_quotes",
                "instrument_health_summary",
            ):
                if table not in tables:
                    continue
                columns = _table_columns(conn, table)
                if "instrument_id" not in columns:
                    results.append(
                        {
                            "level": "error",
                            "segment": segment,
                            "database": str(db_path),
                            "check": "schema",
                            "message": f"{table} missing instrument_id",
                        }
                    )
                    continue
                orphan_count = conn.execute(
                    f"""
                    SELECT COUNT(*) AS count
                    FROM {table} t
                    LEFT JOIN instruments i ON i.instrument_id = t.instrument_id
                    WHERE t.instrument_id IS NULL
                       OR t.instrument_id = ''
                       OR i.instrument_id IS NULL
                    """
                ).fetchone()["count"]
                if orphan_count:
                    results.append(
                        {
                            "level": "error",
                            "segment": segment,
                            "database": str(db_path),
                            "check": "orphan_rows",
                            "message": f"{table} orphan or blank instrument_id rows: {orphan_count}",
                        }
                    )
            if "ohlcv_daily" in tables:
                duplicate_count = conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM (
                        SELECT instrument_id, date, COUNT(*) AS row_count
                        FROM ohlcv_daily
                        GROUP BY instrument_id, date
                        HAVING row_count > 1
                    )
                    """
                ).fetchone()["count"]
                if duplicate_count:
                    results.append(
                        {
                            "level": "error",
                            "segment": segment,
                            "database": str(db_path),
                            "check": "duplicate_daily",
                            "message": f"duplicate ohlcv_daily instrument/date groups: {duplicate_count}",
                        }
                    )
            if "instruments" in tables:
                manual_count = conn.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM instruments
                    WHERE ticker IS NULL OR ticker = '' OR market IS NULL OR market = ''
                    """
                ).fetchone()["count"]
                if manual_count:
                    results.append(
                        {
                            "level": "warning",
                            "segment": segment,
                            "database": str(db_path),
                            "check": "manual_review",
                            "message": f"instruments needing manual review fields: {manual_count}",
                        }
                    )
    if not results:
        results.append(
            {
                "level": "ok",
                "segment": "all",
                "database": str(path),
                "check": "market_db",
                "message": "market database checks passed",
            }
        )
    return results


def calculate_health_summary(
    conn: sqlite3.Connection,
    instrument: dict[str, Any],
    today: date,
) -> dict[str, Any]:
    instrument_id = instrument["instrument_id"]
    row = conn.execute(
        """
        SELECT COUNT(*) AS daily_rows, MIN(date) AS first_daily_date, MAX(date) AS last_daily_date
        FROM ohlcv_daily
        WHERE instrument_id = ?
        """,
        (instrument_id,),
    ).fetchone()
    daily_rows = int(row["daily_rows"] or 0)
    first_daily_date = row["first_daily_date"] if row else None
    last_daily_date = row["last_daily_date"] if row else None
    first_date = parse_date_text(first_daily_date)
    last_date = parse_date_text(last_daily_date)
    listing_date = parse_date_text(instrument.get("listing_date"))
    expected_start = expected_history_start(today, listing_date, first_date, last_date)
    expected_end = today
    existing_months = {
        str(month[0])
        for month in conn.execute(
            """
            SELECT DISTINCT substr(date, 1, 7)
            FROM ohlcv_daily
            WHERE instrument_id = ?
            """,
            (instrument_id,),
        ).fetchall()
        if month[0]
    }
    missing = [
        month.strftime("%Y-%m")
        for month in month_starts_local(expected_start, expected_end)
        if month.strftime("%Y-%m") not in existing_months
    ]
    recent_data_ok = bool(last_date and last_date >= today - timedelta(days=7))
    prior = conn.execute(
        "SELECT retry_count, last_error, manual_review_required FROM instrument_health_summary WHERE instrument_id = ?",
        (instrument_id,),
    ).fetchone()
    retry_count = int(prior["retry_count"] or 0) if prior else 0
    manual_review_required = int(prior["manual_review_required"] or 0) if prior else 0
    history_status = classify_history_status(
        instrument=instrument,
        today=today,
        first_date=first_date,
        last_date=last_date,
        expected_start=expected_start,
        recent_data_ok=recent_data_ok,
        missing_month_count=len(missing),
        retry_count=retry_count,
        manual_review_required=manual_review_required,
    )
    checked_at = now_iso()
    return {
        "instrument_id": instrument_id,
        "daily_rows": daily_rows,
        "first_daily_date": first_daily_date,
        "last_daily_date": last_daily_date,
        "expected_start_date": expected_start.isoformat(),
        "expected_end_date": expected_end.isoformat(),
        "history_status": history_status,
        "recent_data_ok": 1 if recent_data_ok else 0,
        "missing_month_count": len(missing),
        "first_missing_month": missing[0] if missing else "",
        "missing_months_json": json.dumps(missing, ensure_ascii=False),
        "last_checked_at": checked_at,
        "last_success_at": checked_at if recent_data_ok else "",
        "last_error": "" if recent_data_ok else (prior["last_error"] if prior else ""),
        "retry_count": retry_count,
        "next_retry_at": "",
        "manual_review_required": manual_review_required,
        "updated_at": checked_at,
    }


def expected_history_start(today: date, listing_date: date | None, first_date: date | None, last_date: date | None) -> date:
    retention_start = _retention_daily_cutoff(today)
    if listing_date and listing_date > retention_start:
        return listing_date
    if first_date and last_date and first_date > today - timedelta(days=120) and last_date >= today - timedelta(days=7):
        return first_date
    return retention_start


def classify_history_status(
    instrument: dict[str, Any],
    today: date,
    first_date: date | None,
    last_date: date | None,
    expected_start: date,
    recent_data_ok: bool,
    missing_month_count: int,
    retry_count: int,
    manual_review_required: int,
) -> str:
    instrument_status = str(instrument.get("status") or "active")
    if instrument_status == "delisted":
        return "delisted"
    if instrument_status in {"manual_review", "symbol_problem", "delisted_candidate"}:
        return instrument_status
    if manual_review_required:
        return "manual_review"
    if retry_count >= 3 and not recent_data_ok:
        return "delisted_candidate"
    if not first_date or not last_date:
        return "recent_missing"
    if first_date > today - timedelta(days=120) and recent_data_ok:
        return "new_listing"
    if not recent_data_ok:
        return "recent_missing"
    if missing_month_count == 0:
        return "ok"
    first_missing_is_old = expected_start < today - timedelta(days=365)
    return "recent_ok_partial_history" if first_missing_is_old else "partial_old_missing"


def upsert_health_summary(conn: sqlite3.Connection, summary: dict[str, Any]) -> None:
    conn.execute(
        """
        INSERT INTO instrument_health_summary (
            instrument_id, daily_rows, first_daily_date, last_daily_date,
            expected_start_date, expected_end_date, history_status, recent_data_ok,
            missing_month_count, first_missing_month, missing_months_json,
            last_checked_at, last_success_at, last_error, retry_count, next_retry_at,
            manual_review_required, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(instrument_id) DO UPDATE SET
            daily_rows = excluded.daily_rows,
            first_daily_date = excluded.first_daily_date,
            last_daily_date = excluded.last_daily_date,
            expected_start_date = excluded.expected_start_date,
            expected_end_date = excluded.expected_end_date,
            history_status = excluded.history_status,
            recent_data_ok = excluded.recent_data_ok,
            missing_month_count = excluded.missing_month_count,
            first_missing_month = excluded.first_missing_month,
            missing_months_json = excluded.missing_months_json,
            last_checked_at = excluded.last_checked_at,
            last_success_at = COALESCE(NULLIF(excluded.last_success_at, ''), instrument_health_summary.last_success_at),
            last_error = excluded.last_error,
            retry_count = excluded.retry_count,
            next_retry_at = excluded.next_retry_at,
            manual_review_required = excluded.manual_review_required,
            updated_at = excluded.updated_at
        """,
        (
            summary["instrument_id"],
            summary["daily_rows"],
            summary["first_daily_date"],
            summary["last_daily_date"],
            summary["expected_start_date"],
            summary["expected_end_date"],
            summary["history_status"],
            summary["recent_data_ok"],
            summary["missing_month_count"],
            summary["first_missing_month"],
            summary["missing_months_json"],
            summary["last_checked_at"],
            summary["last_success_at"],
            summary["last_error"],
            summary["retry_count"],
            summary["next_retry_at"],
            summary["manual_review_required"],
            summary["updated_at"],
        ),
    )


def sync_health_issues(conn: sqlite3.Connection, summary: dict[str, Any]) -> None:
    instrument_id = summary["instrument_id"]
    if int(summary.get("missing_month_count") or 0) > 0:
        upsert_market_data_issue(
            conn,
            instrument_id,
            "missing_month",
            "low" if summary["recent_data_ok"] else "medium",
            f"missing_month_count={summary['missing_month_count']}; first_missing={summary['first_missing_month']}",
        )
    else:
        resolve_market_data_issue(conn, instrument_id, "missing_month", "month coverage complete")
    if summary["history_status"] == "recent_missing":
        upsert_market_data_issue(conn, instrument_id, "recent_missing", "high", "recent official daily data missing")
    else:
        resolve_market_data_issue(conn, instrument_id, "recent_missing", "recent data ok")
    status_issue = {
        "broken": ("official_no_data", "high", "official data fetch repeatedly failed"),
        "symbol_problem": ("symbol_problem", "high", "market or source symbol looks incorrect"),
        "delisted_candidate": ("delisted_candidate", "medium", "official source returned no data multiple times"),
        "manual_review": ("manual_review", "medium", "manual review required"),
    }.get(str(summary.get("history_status") or ""))
    if status_issue:
        upsert_market_data_issue(conn, instrument_id, *status_issue)
    else:
        for issue_type in ("official_no_data", "parse_error", "symbol_problem", "delisted_candidate", "manual_review"):
            resolve_market_data_issue(conn, instrument_id, issue_type, "health status cleared")


def record_market_data_problem(
    path: Path,
    ticker: str,
    history_status: str,
    issue_type: str,
    severity: str,
    message: str,
    next_retry_at: str = "",
    manual_review_required: int = 0,
) -> None:
    ensure_central_db(path)
    instrument = get_instrument(path, ticker)
    if not instrument:
        return
    db_path = segment_db_paths(path)[instrument["segment"]]
    current = now_iso()
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        prior = conn.execute(
            "SELECT retry_count FROM instrument_health_summary WHERE instrument_id = ?",
            (instrument["instrument_id"],),
        ).fetchone()
        retry_count = int(prior["retry_count"] or 0) + 1 if prior else 1
        instrument_status = str(history_status or "")
        if instrument_status in {"delisted", "delisted_candidate", "symbol_problem", "manual_review"}:
            conn.execute(
                """
                UPDATE instruments
                SET status = ?, updated_at = ?
                WHERE instrument_id = ?
                """,
                (instrument_status, current, instrument["instrument_id"]),
            )
        conn.execute(
            """
            INSERT INTO instrument_health_summary (
                instrument_id, history_status, recent_data_ok, last_checked_at,
                last_error, retry_count, next_retry_at, manual_review_required, updated_at
            )
            VALUES (?, ?, 0, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(instrument_id) DO UPDATE SET
                history_status = excluded.history_status,
                recent_data_ok = excluded.recent_data_ok,
                last_checked_at = excluded.last_checked_at,
                last_error = excluded.last_error,
                retry_count = excluded.retry_count,
                next_retry_at = excluded.next_retry_at,
                manual_review_required = excluded.manual_review_required,
                updated_at = excluded.updated_at
            """,
            (
                instrument["instrument_id"],
                history_status,
                current,
                str(message or "")[:500],
                retry_count,
                next_retry_at,
                int(manual_review_required or 0),
                current,
            ),
        )
        upsert_market_data_issue(
            conn,
            instrument["instrument_id"],
            issue_type,
            severity,
            str(message or "")[:500],
        )


def upsert_market_data_issue(
    conn: sqlite3.Connection,
    instrument_id: str,
    issue_type: str,
    severity: str,
    message: str,
) -> None:
    current = now_iso()
    existing = conn.execute(
        """
        SELECT id, retry_count
        FROM market_data_issues
        WHERE instrument_id = ? AND issue_type = ? AND resolved_at IS NULL
        ORDER BY id DESC
        LIMIT 1
        """,
        (instrument_id, issue_type),
    ).fetchone()
    if existing:
        issue_id = existing["id"] if isinstance(existing, sqlite3.Row) else existing[0]
        conn.execute(
            """
            UPDATE market_data_issues
            SET severity = ?, message = ?, last_seen_at = ?, retry_count = retry_count + 1
            WHERE id = ?
            """,
            (severity, message, current, issue_id),
        )
        return
    conn.execute(
        """
        INSERT INTO market_data_issues (
            instrument_id, issue_type, severity, message, first_seen_at, last_seen_at, retry_count
        )
        VALUES (?, ?, ?, ?, ?, ?, 1)
        """,
        (instrument_id, issue_type, severity, message, current, current),
    )


def resolve_market_data_issue(conn: sqlite3.Connection, instrument_id: str, issue_type: str, note: str) -> None:
    conn.execute(
        """
        UPDATE market_data_issues
        SET resolved_at = COALESCE(resolved_at, ?), resolution_note = ?
        WHERE instrument_id = ? AND issue_type = ? AND resolved_at IS NULL
        """,
        (now_iso(), note, instrument_id, issue_type),
    )


def month_starts_local(start_date: date, end_date: date) -> list[date]:
    current = start_date.replace(day=1)
    months: list[date] = []
    while current <= end_date:
        months.append(current)
        if current.month == 12:
            current = current.replace(year=current.year + 1, month=1)
        else:
            current = current.replace(month=current.month + 1)
    return months


def parse_date_text(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


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
            updated_at = ?
            WHERE instrument_id = ?
            """,
            (listing_date, listing_date, now_iso(), instrument["instrument_id"]),
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
        if listing_date:
            conn.execute(
                """
                UPDATE instruments
                SET listing_date = CASE
                    WHEN listing_date = '' OR listing_date IS NULL OR listing_date > ? THEN ?
                    ELSE listing_date
                END,
                updated_at = ?
                WHERE instrument_id = ?
                """,
                (listing_date, listing_date, now_iso(), instrument["instrument_id"]),
            )
        if status in {"delisted", "delisted_candidate", "symbol_problem", "manual_review"}:
            conn.execute(
                """
                UPDATE instruments
                SET status = ?, updated_at = ?
                WHERE instrument_id = ?
                """,
                (status, now_iso(), instrument["instrument_id"]),
            )
        conn.execute(
            """
            INSERT INTO instrument_health_summary (
                instrument_id, history_status, last_checked_at, updated_at
            )
            VALUES (?, ?, ?, ?)
            ON CONFLICT(instrument_id) DO UPDATE SET
                history_status = excluded.history_status,
                last_checked_at = excluded.last_checked_at,
                updated_at = excluded.updated_at
            """,
            (
                instrument["instrument_id"],
                str(status or "").strip(),
                checked_at,
                now_iso(),
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


def normalize_instrument_output(row: dict[str, Any]) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "").strip().upper()
    market = str(row.get("market") or "").strip().upper()
    asset_type = str(row.get("type") or infer_asset_type(ticker)).strip().upper()
    if not market:
        market = instrument_market(asset_type, row.get("exchange_suffix", ""), row.get("source_market"))
    suffix = exchange_suffix_for_market(market)
    symbol = row.get("yahoo_symbol") or row.get("symbol") or yahoo_symbol(ticker, suffix)
    updated_at = row.get("updated_at") or timestamp_to_iso(row.get("updated_at_ts")) or ""
    return {
        **row,
        "instrument_id": row.get("instrument_id") or instrument_id_for(ticker, market),
        "ticker": ticker,
        "market": market,
        "type": asset_type,
        "exchange_suffix": suffix,
        "symbol": symbol,
        "yahoo_symbol": symbol,
        "segment": segment_for_market(market),
        "updated_at": updated_at,
        "updated_at_ts": iso_to_timestamp(updated_at),
    }


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
        "instrument_id": incoming.get("instrument_id") or existing.get("instrument_id") or row_instrument_id(incoming),
        "ticker": ticker,
        "market": incoming.get("market") or existing.get("market") or instrument_market(incoming.get("type", ""), incoming.get("exchange_suffix", "")),
        "yahoo_symbol": incoming.get("yahoo_symbol") or existing.get("yahoo_symbol") or existing.get("symbol"),
        "name": name,
        "type": incoming.get("type") or existing.get("type") or infer_asset_type(ticker),
        "source": incoming.get("source") or existing.get("source") or "profile",
        "listing_date": incoming.get("listing_date") or existing.get("listing_date") or "",
        "delisting_date": incoming.get("delisting_date") or existing.get("delisting_date") or "",
        "status": incoming.get("status") or existing.get("status") or "active",
        "created_at": existing.get("created_at") or incoming.get("created_at") or now_iso(),
        "updated_at": now_iso(),
    }


def clean_name(value: object, ticker: object) -> str:
    text = str(value or "").strip()
    ticker_text = str(ticker or "").strip().upper()
    return text or ticker_text


def is_specific_name(name: str | None, ticker: str) -> bool:
    return bool(name) and str(name).strip().upper() != str(ticker).strip().upper()


def infer_asset_type(ticker: str) -> str:
    return "ETF" if str(ticker).startswith("00") else "STOCK"


def ensure_instrument_for_market_row(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    ticker = str(row.get("ticker") or "").strip().upper()
    if not ticker:
        raise ValueError("market row missing ticker")
    existing = get_instrument(path, ticker)
    if existing:
        return existing
    source_market = str(row.get("source_market") or "").strip().upper()
    asset_type = infer_asset_type(ticker)
    suffix = ".TWO" if source_market == "TPEX" else ".TW"
    if asset_type == "ETF":
        suffix = ".TW"
    return register_instrument(
        path,
        ticker=ticker,
        name=str(row.get("name") or ticker),
        asset_type=asset_type,
        exchange_suffix=suffix,
        source="market_data",
    )


def _upsert_instrument(path: Path, row: dict[str, Any]) -> dict[str, Any]:
    ensure_central_db(path)
    market = row.get("market") or instrument_market(row["type"], row.get("exchange_suffix", ""))
    row["market"] = market
    row["instrument_id"] = row.get("instrument_id") or instrument_id_for(row["ticker"], market)
    row["yahoo_symbol"] = row.get("yahoo_symbol") or yahoo_symbol(row["ticker"], exchange_suffix_for_market(market))
    segment = segment_for_market(market)
    db_path = segment_db_paths(path)[segment if not _is_legacy_file(path) else "legacy"]
    with sqlite3.connect(db_path) as conn:
        existing = conn.execute(
            "SELECT name FROM instruments WHERE instrument_id = ?",
            (row["instrument_id"],),
        ).fetchone()
        if existing and is_specific_name(existing[0], row["ticker"]) and existing[0] != row["name"]:
            conn.execute(
                """
                INSERT INTO instrument_name_history (
                    instrument_id, old_name, new_name, effective_date, detected_at, source, note
                )
                VALUES (?, ?, ?, '', ?, ?, ?)
                """,
                (
                    row["instrument_id"],
                    existing[0],
                    row["name"],
                    now_iso(),
                    row.get("source") or "unknown",
                    "detected by instrument upsert",
                ),
            )
            conn.execute(
                """
                INSERT INTO instrument_aliases (
                    instrument_id, alias_type, alias_value, source, is_active, created_at, note
                )
                VALUES (?, 'old_name', ?, ?, 0, ?, 'name changed')
                """,
                (row["instrument_id"], existing[0], row.get("source") or "unknown", now_iso()),
            )
        conn.execute(
            """
            INSERT INTO instruments (
                instrument_id,
                ticker,
                market,
                type,
                name,
                yahoo_symbol,
                listing_date,
                delisting_date,
                status,
                source,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(instrument_id) DO UPDATE SET
                name = excluded.name,
                type = excluded.type,
                yahoo_symbol = excluded.yahoo_symbol,
                source = excluded.source,
                listing_date = COALESCE(NULLIF(excluded.listing_date, ''), instruments.listing_date),
                delisting_date = COALESCE(NULLIF(excluded.delisting_date, ''), instruments.delisting_date),
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                row["instrument_id"],
                row["ticker"],
                row["market"],
                row["type"],
                row["name"],
                row["yahoo_symbol"],
                row.get("listing_date") or None,
                row.get("delisting_date") or None,
                row.get("status") or "active",
                row["source"],
                row.get("created_at") or now_iso(),
                row.get("updated_at") or now_iso(),
            ),
        )
    _delete_ticker_from_other_segments(path, row["ticker"], keep_path=db_path)
    return normalize_instrument_output({**row, "segment": segment})


def _delete_ticker_from_other_segments(path: Path, ticker: str, keep_path: Path) -> None:
    if _is_legacy_file(path):
        return
    for db_path in segment_db_paths(path).values():
        if db_path == keep_path:
            continue
        try:
            with sqlite3.connect(db_path) as conn:
                ids = [
                    row[0]
                    for row in conn.execute("SELECT instrument_id FROM instruments WHERE ticker = ?", (ticker,)).fetchall()
                ]
                conn.execute("DELETE FROM instruments WHERE ticker = ?", (ticker,))
                for instrument_id in ids:
                    conn.execute("DELETE FROM ohlcv_daily WHERE instrument_id = ?", (instrument_id,))
                    conn.execute("DELETE FROM ohlcv_intraday_15m WHERE instrument_id = ?", (instrument_id,))
                    conn.execute("DELETE FROM quote_snapshots_15m WHERE instrument_id = ?", (instrument_id,))
                    conn.execute("DELETE FROM after_close_quotes WHERE instrument_id = ?", (instrument_id,))
                    conn.execute("DELETE FROM quotes WHERE instrument_id = ?", (instrument_id,))
                    conn.execute("DELETE FROM instrument_health_summary WHERE instrument_id = ?", (instrument_id,))
                conn.execute("DELETE FROM etf_dividends WHERE ticker = ?", (ticker,))
        except sqlite3.DatabaseError:
            continue


def _db_path_for_ticker(path: Path, ticker: str, source_market: str | None) -> Path:
    if _is_legacy_file(path):
        return path
    instrument = get_instrument(path, ticker)
    if instrument:
        return segment_db_paths(path)[instrument["segment"]]
    if str(ticker).startswith("00"):
        return segment_db_paths(path)["etf"]
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
        _create_market_schema(conn)


def _create_market_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS instruments (
            instrument_id TEXT PRIMARY KEY,
            ticker TEXT NOT NULL,
            market TEXT NOT NULL,
            type TEXT NOT NULL,
            name TEXT,
            yahoo_symbol TEXT,
            listing_date TEXT,
            delisting_date TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            source TEXT,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(ticker, market)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS instrument_name_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument_id TEXT NOT NULL,
            old_name TEXT,
            new_name TEXT,
            effective_date TEXT,
            detected_at TEXT NOT NULL,
            source TEXT,
            note TEXT,
            FOREIGN KEY(instrument_id) REFERENCES instruments(instrument_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS instrument_aliases (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument_id TEXT NOT NULL,
            alias_type TEXT NOT NULL,
            alias_value TEXT NOT NULL,
            source TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT,
            note TEXT,
            FOREIGN KEY(instrument_id) REFERENCES instruments(instrument_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS instrument_corporate_actions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument_id TEXT NOT NULL,
            action_type TEXT NOT NULL,
            effective_date TEXT NOT NULL,
            ratio_from REAL,
            ratio_to REAL,
            source TEXT,
            note TEXT,
            created_at TEXT,
            updated_at TEXT,
            UNIQUE(instrument_id, action_type, effective_date),
            FOREIGN KEY(instrument_id) REFERENCES instruments(instrument_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ohlcv_daily (
            instrument_id TEXT NOT NULL,
            date TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            value REAL,
            source TEXT NOT NULL,
            adjusted INTEGER DEFAULT 0,
            created_at TEXT,
            updated_at TEXT,
            PRIMARY KEY (instrument_id, date),
            FOREIGN KEY(instrument_id) REFERENCES instruments(instrument_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quotes (
            instrument_id TEXT PRIMARY KEY,
            price REAL,
            change REAL,
            change_pct REAL,
            quote_date TEXT,
            quote_time TEXT,
            source TEXT,
            updated_at TEXT,
            FOREIGN KEY(instrument_id) REFERENCES instruments(instrument_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ohlcv_intraday_15m (
            instrument_id TEXT NOT NULL,
            datetime TEXT NOT NULL,
            open REAL,
            high REAL,
            low REAL,
            close REAL,
            volume INTEGER,
            source TEXT NOT NULL,
            created_at TEXT,
            PRIMARY KEY (instrument_id, datetime),
            FOREIGN KEY(instrument_id) REFERENCES instruments(instrument_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS quote_snapshots_15m (
            instrument_id TEXT NOT NULL,
            snapshot_time TEXT NOT NULL,
            price REAL,
            change REAL,
            change_pct REAL,
            source TEXT,
            created_at TEXT,
            PRIMARY KEY (instrument_id, snapshot_time),
            FOREIGN KEY(instrument_id) REFERENCES instruments(instrument_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS after_close_quotes (
            instrument_id TEXT NOT NULL,
            quote_date TEXT NOT NULL,
            price REAL,
            change REAL,
            change_pct REAL,
            source TEXT,
            created_at TEXT,
            PRIMARY KEY (instrument_id, quote_date),
            FOREIGN KEY(instrument_id) REFERENCES instruments(instrument_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS instrument_health_summary (
            instrument_id TEXT PRIMARY KEY,
            daily_rows INTEGER DEFAULT 0,
            first_daily_date TEXT,
            last_daily_date TEXT,
            expected_start_date TEXT,
            expected_end_date TEXT,
            history_status TEXT,
            recent_data_ok INTEGER DEFAULT 0,
            missing_month_count INTEGER DEFAULT 0,
            first_missing_month TEXT,
            missing_months_json TEXT,
            last_checked_at TEXT,
            last_success_at TEXT,
            last_error TEXT,
            retry_count INTEGER DEFAULT 0,
            next_retry_at TEXT,
            manual_review_required INTEGER DEFAULT 0,
            updated_at TEXT,
            FOREIGN KEY(instrument_id) REFERENCES instruments(instrument_id)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS market_data_issues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            instrument_id TEXT,
            issue_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            message TEXT,
            first_seen_at TEXT,
            last_seen_at TEXT,
            retry_count INTEGER DEFAULT 0,
            resolved_at TEXT,
            resolution_note TEXT,
            FOREIGN KEY(instrument_id) REFERENCES instruments(instrument_id)
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
        CREATE TABLE IF NOT EXISTS operation_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name TEXT NOT NULL,
            source TEXT,
            event_type TEXT NOT NULL,
            status TEXT NOT NULL,
            started_at TEXT,
            finished_at TEXT,
            duration_ms INTEGER,
            summary TEXT,
            details TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS uploaded_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_slug TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            stored_path TEXT NOT NULL,
            mime_type TEXT,
            file_size INTEGER NOT NULL,
            sha256 TEXT NOT NULL,
            source TEXT NOT NULL,
            status TEXT NOT NULL,
            note TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            last_seen_at TEXT,
            parsed_at TEXT,
            parse_status TEXT,
            parse_summary TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS gmail_attachment_receipts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            profile_slug TEXT NOT NULL,
            message_id TEXT NOT NULL,
            attachment_id TEXT NOT NULL,
            original_filename TEXT NOT NULL,
            statement_date TEXT,
            sha256 TEXT,
            upload_id INTEGER,
            status TEXT NOT NULL,
            note TEXT,
            downloaded_at TEXT NOT NULL,
            last_seen_at TEXT NOT NULL,
            UNIQUE(profile_slug, message_id, attachment_id),
            FOREIGN KEY(upload_id) REFERENCES uploaded_documents(id)
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
    _create_etf_holdings_schema(conn)
    _create_market_indexes(conn)


def _create_etf_holdings_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS etf_holding_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            etf_ticker TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            source TEXT NOT NULL,
            source_url TEXT,
            status TEXT NOT NULL,
            row_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            notes TEXT,
            UNIQUE(etf_ticker, as_of_date, source)
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS etf_holding_components (
            snapshot_id INTEGER NOT NULL,
            etf_ticker TEXT NOT NULL,
            as_of_date TEXT NOT NULL,
            source TEXT NOT NULL,
            constituent_ticker TEXT,
            constituent_name TEXT,
            weight REAL,
            shares REAL,
            market_value REAL,
            industry TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            FOREIGN KEY(snapshot_id) REFERENCES etf_holding_snapshots(id)
        )
        """
    )


def _create_market_indexes(conn: sqlite3.Connection) -> None:
    conn.execute("CREATE INDEX IF NOT EXISTS idx_instruments_ticker_market ON instruments(ticker, market)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_instruments_status ON instruments(status)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_corporate_actions_instrument_date "
        "ON instrument_corporate_actions(instrument_id, effective_date)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ohlcv_daily_instrument_date ON ohlcv_daily(instrument_id, date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_quotes_updated ON quotes(updated_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_health_status ON instrument_health_summary(history_status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_health_retry ON instrument_health_summary(next_retry_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_issues_instrument ON market_data_issues(instrument_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_issues_unresolved ON market_data_issues(resolved_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_operation_logs_finished ON operation_logs(finished_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_operation_logs_status ON operation_logs(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_operation_logs_job ON operation_logs(job_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_uploaded_documents_created ON uploaded_documents(created_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_uploaded_documents_profile ON uploaded_documents(profile_slug)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_uploaded_documents_status ON uploaded_documents(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_uploaded_documents_sha ON uploaded_documents(sha256)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_gmail_receipts_statement "
        "ON gmail_attachment_receipts(profile_slug, statement_date)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_gmail_receipts_sha "
        "ON gmail_attachment_receipts(profile_slug, sha256)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_etf_dividends_ex_date ON etf_dividends(ex_dividend_date)")
    _create_etf_holdings_indexes(conn)


def _create_etf_holdings_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_etf_holding_snapshots_ticker_date "
        "ON etf_holding_snapshots(etf_ticker, as_of_date)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_etf_holding_components_snapshot "
        "ON etf_holding_components(snapshot_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_etf_holding_components_ticker "
        "ON etf_holding_components(constituent_ticker)"
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
