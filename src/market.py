from __future__ import annotations

import json
import os
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd
import yfinance as yf

from central_store import load_quote_cache, save_quote_cache
from utils import safe_subtract, yahoo_symbol, pct


US_MARKETS = [
    {"key": "nasdaq", "label": "Nasdaq", "symbol": "^IXIC"},
    {"key": "sp500", "label": "S&P 500", "symbol": "^GSPC"},
    {"key": "sox", "label": "費半", "symbol": "^SOX"},
    {"key": "nvda", "label": "NVDA", "symbol": "NVDA"},
    {"key": "amd", "label": "AMD", "symbol": "AMD"},
    {"key": "tsm", "label": "TSM ADR", "symbol": "TSM"},
    {"key": "us10y", "label": "美債10年", "symbol": "^TNX"},
    {"key": "dxy", "label": "美元指數", "symbol": "DX-Y.NYB"},
]

US_SYMBOLS = {item["symbol"].upper() for item in US_MARKETS}
TW_MARKET_WINDOW = ("09:01", "13:01")
US_MARKET_WINDOW = ("21:30", "05:00")


class QuoteService:
    def __init__(self, cache_path: Path, refresh_seconds: int = 60):
        self.cache_path = cache_path
        self.refresh_seconds = max(15, int(refresh_seconds))
        self.cache = self._load_cache()
        self.refresh_summary: dict[str, Any] = {
            "requested_symbols": [],
            "skipped_symbols": [],
            "forced_symbols": [],
        }
        self.intraday_15m_rows: list[dict[str, Any]] = []

    def get_quotes(
        self,
        symbols: list[str],
        force: bool = False,
        force_symbols: list[str] | set[str] | None = None,
        respect_market_hours: bool = True,
    ) -> dict[str, dict[str, Any]]:
        quotes = {}
        unique_symbols = [symbol for symbol in dict.fromkeys(symbols) if symbol]
        now = datetime.now().astimezone()
        force_set = {str(symbol).upper() for symbol in (force_symbols or [])}
        self.refresh_summary = {
            "now": now.isoformat(timespec="seconds"),
            "refresh_seconds": self.refresh_seconds,
            "tw_window": f"{TW_MARKET_WINDOW[0]}-{TW_MARKET_WINDOW[1]}",
            "us_window": f"{US_MARKET_WINDOW[0]}-{US_MARKET_WINDOW[1]}",
            "requested_symbols": [],
            "skipped_symbols": [],
            "forced_symbols": sorted(force_set),
        }
        self.intraday_15m_rows = []

        for symbol in unique_symbols:
            symbol_key = symbol.upper()
            forced_symbol = symbol_key in force_set
            allowed_now = refresh_allowed_for_symbol(symbol, now) if respect_market_hours else True
            allow_fetch = allowed_now or forced_symbol
            force_this_symbol = forced_symbol or (force and allowed_now)

            cached = self.cache.get(symbol)
            will_request = allow_fetch and (force_this_symbol or not cached or self._is_stale(cached))
            if will_request:
                self.refresh_summary["requested_symbols"].append(symbol)
            elif not allow_fetch:
                self.refresh_summary["skipped_symbols"].append(symbol)

            quotes[symbol] = self.get_quote(
                symbol,
                force=force_this_symbol,
                allow_fetch=allow_fetch,
                skip_reason=closed_market_message(symbol),
            )
        self._save_cache()
        return quotes

    def get_quote(
        self,
        symbol: str,
        force: bool = False,
        allow_fetch: bool = True,
        skip_reason: str = "",
    ) -> dict[str, Any]:
        cached = self.cache.get(symbol)
        if not allow_fetch:
            if cached:
                return {
                    **cached,
                    "source": "cache",
                    "status": "market-closed",
                    "error": skip_reason,
                }
            return _empty_quote(symbol, skip_reason)

        if not force and cached and not self._is_stale(cached):
            return {**cached, "source": "cache"}

        try:
            quote, intraday_rows = _fetch_quote(symbol)
            quote["source"] = "yfinance"
            quote["status"] = "ok"
            quote["error"] = ""
            self.cache[symbol] = quote
            self.intraday_15m_rows.extend(intraday_rows)
            return quote
        except Exception as exc:
            if cached:
                return {
                    **cached,
                    "source": "cache",
                    "status": "stale",
                    "error": f"yfinance 抓取失敗，使用快取：{exc}",
                }
            return _empty_quote(symbol, str(exc))

    def _is_stale(self, quote: dict[str, Any]) -> bool:
        return time.time() - float(quote.get("fetched_at_ts", 0)) > self.refresh_seconds

    def _load_cache(self) -> dict[str, dict[str, Any]]:
        if self.cache_path.suffix.lower() in {".sqlite", ".db"}:
            return load_quote_cache(self.cache_path)
        if not self.cache_path.exists():
            return {}
        try:
            return json.loads(self.cache_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}

    def _save_cache(self) -> None:
        if self.cache_path.suffix.lower() in {".sqlite", ".db"}:
            save_quote_cache(self.cache_path, self.cache)
            return
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            delete=False,
            dir=str(self.cache_path.parent),
            suffix=".tmp",
        ) as tmp:
            json.dump(self.cache, tmp, ensure_ascii=False, indent=2)
            tmp.write("\n")
            tmp_path = Path(tmp.name)
        os.replace(tmp_path, self.cache_path)


def symbols_for_state(state: dict[str, Any]) -> list[str]:
    symbols = [item["symbol"] for item in US_MARKETS]
    for item in state.get("holdings", []) + state.get("watchlist", []):
        symbols.append(yahoo_symbol(item.get("ticker", ""), item.get("exchange_suffix", ".TW")))
    symbols.extend(state.get("price_overrides", {}).keys())
    return symbols


def fetch_symbol_bundle(symbol: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    quote, intraday_rows = _fetch_quote(symbol)
    quote["source"] = "yfinance"
    quote["status"] = "ok"
    quote["error"] = ""
    return quote, intraday_rows


def refresh_allowed_for_symbol(symbol: str, now: datetime | None = None) -> bool:
    now = now or datetime.now().astimezone()
    market = market_for_symbol(symbol)
    if market == "tw":
        if now.weekday() >= 5:
            return False
        return _is_time_in_window(now, *TW_MARKET_WINDOW, inclusive_end=True)
    return _is_time_in_window(now, *US_MARKET_WINDOW)


def market_for_symbol(symbol: str) -> str:
    normalized = str(symbol).strip().upper()
    if normalized.endswith(".TW") or normalized.endswith(".TWO"):
        return "tw"
    if normalized in US_SYMBOLS:
        return "us"
    return "us"


def closed_market_message(symbol: str) -> str:
    market = market_for_symbol(symbol)
    if market == "tw":
        return f"台股非更新時段（{TW_MARKET_WINDOW[0]}-{TW_MARKET_WINDOW[1]}），未請求 Yahoo。"
    return f"美股非更新時段（{US_MARKET_WINDOW[0]}-{US_MARKET_WINDOW[1]}），未請求 Yahoo。"


def _is_time_in_window(now: datetime, start: str, end: str, inclusive_end: bool = False) -> bool:
    current = now.hour * 60 + now.minute
    start_minute = _hhmm_to_minutes(start)
    end_minute = _hhmm_to_minutes(end)
    if start_minute <= end_minute:
        return start_minute <= current <= end_minute if inclusive_end else start_minute <= current < end_minute
    return current >= start_minute or current < end_minute


def _hhmm_to_minutes(value: str) -> int:
    hour_text, minute_text = value.split(":", 1)
    return int(hour_text) * 60 + int(minute_text)


def apply_price_overrides(
    quotes: dict[str, dict[str, Any]],
    overrides: dict[str, dict[str, Any]] | None,
) -> dict[str, dict[str, Any]]:
    if not overrides:
        return quotes

    for symbol, override in overrides.items():
        if not isinstance(override, dict):
            continue
        close = override.get("close")
        if close is None:
            continue

        base = quotes.get(symbol, _empty_quote(symbol, "manual override"))
        prev_close = override.get("prev_close", base.get("prev_close"))
        change = safe_subtract(close, prev_close)
        quotes[symbol] = {
            **base,
            "symbol": symbol,
            "close": close,
            "prev_close": prev_close,
            "change": change,
            "change_pct": pct(change, prev_close),
            "price_time": override.get("updated_at", base.get("price_time", "")),
            "source": "manual",
            "status": "manual",
            "error": override.get("note", ""),
        }
    return quotes


def attach_quotes_to_items(items: list[dict[str, Any]], quotes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    enriched = []
    for item in items:
        symbol = yahoo_symbol(item.get("ticker", ""), item.get("exchange_suffix", ".TW"))
        quote = quotes.get(symbol, _empty_quote(symbol, "沒有報價"))
        enriched.append({**item, "symbol": symbol, "quote": quote})
    return enriched


def market_snapshot(quotes: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for item in US_MARKETS:
        quote = quotes.get(item["symbol"], _empty_quote(item["symbol"], "沒有報價"))
        close = quote.get("close")
        if item["symbol"] == "^TNX" and close is not None and close > 20:
            close = close / 10
        rows.append({**item, "quote": {**quote, "display_close": close}})
    return rows


def _fetch_quote(symbol: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ticker = yf.Ticker(symbol)
    close, prev_close, price_time, intraday_history = _intraday_price(ticker)

    daily_close, daily_prev_close, daily_time = _daily_price(ticker)
    if daily_close is not None and close == daily_close:
        price_time = daily_time
    if close is None:
        close = daily_close
        price_time = daily_time
    if prev_close is None:
        prev_close = daily_prev_close

    change = safe_subtract(close, prev_close)
    quote = {
        "symbol": symbol,
        "close": close,
        "prev_close": prev_close,
        "change": change,
        "change_pct": pct(change, prev_close),
        "price_time": price_time,
        "fetched_at_ts": time.time(),
        "fetched_at": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return quote, _intraday_15m_rows(symbol, intraday_history, quote["fetched_at_ts"])


def _intraday_price(ticker: yf.Ticker) -> tuple[float | None, float | None, str, pd.DataFrame]:
    history = ticker.history(period="1d", interval="1m", auto_adjust=False, actions=False, timeout=15)
    if history.empty or "Close" not in history.columns:
        close = None
        price_time = ""
    else:
        closes = history["Close"].dropna()
        if closes.empty:
            close = None
            price_time = ""
        else:
            close = _float(closes.iloc[-1])
            price_time = str(closes.index[-1])

    fast_close = None
    prev_close = None
    try:
        fast_info = ticker.fast_info
        fast_close = _float(fast_info.get("last_price"))
        if fast_close is None:
            fast_close = _float(fast_info.get("lastPrice"))
        if fast_close is None:
            fast_close = _float(fast_info.get("regular_market_price"))
        if fast_close is None:
            fast_close = _float(fast_info.get("regularMarketPrice"))
        prev_close = _float(fast_info.get("previous_close"))
        if prev_close is None:
            prev_close = _float(fast_info.get("regularMarketPreviousClose"))
    except Exception:
        pass

    return fast_close if fast_close is not None else close, prev_close, price_time, history


def _intraday_15m_rows(symbol: str, history: pd.DataFrame, fetched_at_ts: float) -> list[dict[str, Any]]:
    if market_for_symbol(symbol) != "tw" or history.empty:
        return []
    required = {"Open", "High", "Low", "Close", "Volume"}
    if not required.issubset(history.columns):
        return []

    frame = history[list(required)].dropna(subset=["Open", "High", "Low", "Close"])
    if frame.empty:
        return []

    bars = frame.resample("15min", label="left", closed="left").agg(
        {
            "Open": "first",
            "High": "max",
            "Low": "min",
            "Close": "last",
            "Volume": "sum",
        }
    ).dropna(subset=["Open", "High", "Low", "Close"])

    now = datetime.now().astimezone()
    ticker = symbol.rsplit(".", 1)[0].upper()
    rows = []
    for index, row in bars.iterrows():
        bar_end = index + timedelta(minutes=15)
        if bar_end > now:
            continue
        rows.append(
            {
                "ticker": ticker,
                "bar_time": index.isoformat(),
                "trade_date": index.date().isoformat(),
                "open": _float(row["Open"]),
                "high": _float(row["High"]),
                "low": _float(row["Low"]),
                "close": _float(row["Close"]),
                "volume": int(row["Volume"]) if not pd.isna(row["Volume"]) else None,
                "source": "YFINANCE_1M_RESAMPLED_15M",
                "source_market": "YAHOO",
                "fetched_at_ts": fetched_at_ts,
            }
        )
    return rows


def _daily_price(ticker: yf.Ticker) -> tuple[float | None, float | None, str]:
    history = ticker.history(period="7d", interval="1d", auto_adjust=False, actions=False, timeout=15)
    if history.empty or "Close" not in history.columns:
        return None, None, ""
    closes = history["Close"].dropna()
    if closes.empty:
        return None, None, ""
    close = _float(closes.iloc[-1])
    prev_close = _float(closes.iloc[-2]) if len(closes) >= 2 else None
    return close, prev_close, str(closes.index[-1].date() if hasattr(closes.index[-1], "date") else closes.index[-1])


def _float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    return float(value)


def _empty_quote(symbol: str, error: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "close": None,
        "prev_close": None,
        "change": None,
        "change_pct": None,
        "price_time": "",
        "fetched_at_ts": 0,
        "fetched_at": "",
        "source": "N/A",
        "status": "error",
        "error": error,
    }
