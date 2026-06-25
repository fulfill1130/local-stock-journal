from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from yfinance_quote_provider import YFinanceQuoteProvider


class YFinanceQuoteProviderTests(unittest.TestCase):
    def test_successful_quote_conversion_uses_existing_bundle_shape(self) -> None:
        provider = YFinanceQuoteProvider()
        raw_quote = {
            "symbol": "2330.TW",
            "close": 100,
            "prev_close": 95,
            "change": 5,
            "change_pct": 5.263157,
            "price_time": "2026-06-24T10:00:00+08:00",
            "fetched_at": "2026-06-24T10:01:00+08:00",
            "source": "yfinance",
            "status": "ok",
            "error": "",
        }

        with patch("yfinance_quote_provider.market.fetch_symbol_bundle", return_value=(raw_quote, [])) as fetch:
            result = provider.get_quotes(["2330.TW"])

        fetch.assert_called_once_with("2330.TW")
        self.assertTrue(result.ok)
        self.assertEqual(result.provider_id, "yfinance")
        self.assertEqual(result.source, "yfinance")
        self.assertEqual(len(result.items), 1)
        quote = result.items[0]
        self.assertEqual(quote.instrument_id, "2330.TW")
        self.assertEqual(quote.provider_id, "yfinance")
        self.assertEqual(quote.price, 100)
        self.assertEqual(quote.previous_close, 95)
        self.assertEqual(quote.change, 5)
        self.assertEqual(quote.change_pct, 5.263157)
        self.assertEqual(quote.source_timestamp.isoformat(), "2026-06-24T10:00:00+08:00")
        self.assertEqual(quote.fetched_at.isoformat(), "2026-06-24T10:01:00+08:00")
        self.assertEqual(quote.freshness, "realtime")
        self.assertEqual(quote.issues, ())

    def test_provider_failure_becomes_structured_issue(self) -> None:
        provider = YFinanceQuoteProvider()

        with patch(
            "yfinance_quote_provider.market.fetch_symbol_bundle",
            side_effect=RuntimeError("network unavailable"),
        ) as fetch:
            result = provider.get_quotes(["2330.TW"])

        fetch.assert_called_once_with("2330.TW")
        self.assertFalse(result.ok)
        self.assertEqual(result.items, ())
        self.assertEqual(len(result.issues), 1)
        issue = result.issues[0]
        self.assertEqual(issue.provider_id, "yfinance")
        self.assertEqual(issue.code, "fetch_failed")
        self.assertEqual(issue.message, "network unavailable")
        self.assertTrue(issue.retryable)
        self.assertEqual(issue.instrument_id, "2330.TW")
        self.assertEqual(issue.details["symbol"], "2330.TW")
        self.assertEqual(issue.details["exception_type"], "RuntimeError")

    def test_optional_symbol_resolver_keeps_instrument_id_stable(self) -> None:
        provider = YFinanceQuoteProvider(symbol_for_instrument=lambda instrument_id: "2330.TW")
        raw_quote = {
            "close": 100,
            "prev_close": 90,
            "source": "yfinance",
            "status": "ok",
        }

        with patch("yfinance_quote_provider.market.fetch_symbol_bundle", return_value=(raw_quote, [])) as fetch:
            result = provider.get_quotes(["TWSE:2330"])

        fetch.assert_called_once_with("2330.TW")
        self.assertEqual(result.items[0].instrument_id, "TWSE:2330")


if __name__ == "__main__":
    unittest.main()
