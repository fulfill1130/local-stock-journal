from __future__ import annotations

import sys
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from analyzer import build_dashboard_state
from central_store import apply_daily_quote_fallbacks
from market import attach_quotes_to_items


class DailyQuoteFallbackTests(unittest.TestCase):
    def test_same_day_official_close_replaces_stale_yfinance_quote_for_holding_analysis(self) -> None:
        quotes = {
            "00900.TW": {
                "symbol": "00900.TW",
                "close": 19.77,
                "prev_close": 19.69,
                "price_time": "2026-06-25",
                "source": "yfinance",
            }
        }
        with _mock_daily_fallback(latest_close=19.80, previous_close=19.69, latest_date="2026-06-25"):
            patched = apply_daily_quote_fallbacks(db_root, quotes, ["00900"], force_tickers=["00900"])
        holdings = attach_quotes_to_items(
            [{"ticker": "00900", "exchange_suffix": ".TW", "shares": 353, "avg_cost": 15}],
            patched,
        )
        dashboard = build_dashboard_state({"settings": {}}, holdings, [], [])

        holding = dashboard["holdings"][0]
        self.assertEqual(holding["close"], 19.80)
        self.assertEqual(holding["quote"]["source"], "official_daily_fallback")
        self.assertAlmostEqual(holding["change_pct"], ((19.80 - 19.69) / 19.69) * 100)

    def test_older_official_close_does_not_override_newer_quote_data(self) -> None:
        quotes = {
            "00900.TW": {
                "symbol": "00900.TW",
                "close": 20.10,
                "prev_close": 19.80,
                "price_time": "2026-06-26",
                "source": "yfinance",
            }
        }
        with _mock_daily_fallback(latest_close=19.80, previous_close=19.69, latest_date="2026-06-25"):
            patched = apply_daily_quote_fallbacks(db_root, quotes, ["00900"], force_tickers=["00900"])

        self.assertEqual(patched["00900.TW"]["close"], 20.10)
        self.assertEqual(patched["00900.TW"]["source"], "yfinance")

    def test_after_close_quote_remains_separate_from_main_official_close(self) -> None:
        quotes = {
            "00900.TW": {
                "symbol": "00900.TW",
                "close": 19.77,
                "prev_close": 19.69,
                "price_time": "2026-06-25",
                "source": "yfinance",
            }
        }
        with _mock_daily_fallback(latest_close=19.80, previous_close=19.69, latest_date="2026-06-25"):
            patched = apply_daily_quote_fallbacks(db_root, quotes, ["00900"], force_tickers=["00900"])
        holdings = attach_quotes_to_items(
            [
                {
                    "ticker": "00900",
                    "exchange_suffix": ".TW",
                    "shares": 353,
                    "avg_cost": 15,
                    "after_close_quote": {
                        "trade_date": "2026-06-25",
                        "close": 19.83,
                        "source": "yfinance",
                    },
                }
            ],
            patched,
        )
        dashboard = build_dashboard_state({"settings": {}}, holdings, [], [])
        holding = dashboard["holdings"][0]

        self.assertEqual(holding["close"], 19.80)
        self.assertEqual(holding["after_close_quote"]["close"], 19.83)
        self.assertEqual(holding["after_close_quote"]["source"], "yfinance")


db_root = Path("unused")


@contextmanager
def _mock_daily_fallback(*, latest_close: float, previous_close: float, latest_date: str):
    instrument = {
        "ticker": "00900",
        "symbol": "00900.TW",
        "market": "ETF",
    }
    fallback = {
        "symbol": "00900.TW",
        "close": latest_close,
        "prev_close": previous_close,
        "change": latest_close - previous_close,
        "change_pct": ((latest_close - previous_close) / previous_close) * 100,
        "price_time": latest_date,
        "fetched_at": latest_date,
        "source": "official_daily_fallback",
        "daily_source": "TWSE_STOCK_DAY",
        "status": "historical-fallback",
    }
    with (
        patch("central_store.get_instrument", return_value=instrument),
        patch("central_store.latest_daily_quote", return_value=fallback),
    ):
        yield


if __name__ == "__main__":
    unittest.main()
