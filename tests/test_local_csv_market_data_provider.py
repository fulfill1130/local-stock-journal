from __future__ import annotations

import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from local_csv_market_data_provider import LocalCsvMarketDataProvider


class LocalCsvMarketDataProviderTests(unittest.TestCase):
    def test_loads_local_quotes_from_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            quote_path = Path(temp_dir) / "quotes.csv"
            quote_path.write_text(
                "\n".join(
                    [
                        "instrument_id,price,previous_close,change,change_pct,source_timestamp,freshness,source,currency",
                        "TWSE:2330,100,95,5,5.263157,2026-06-24T10:00:00+08:00,manual,local_sample,TWD",
                    ]
                ),
                encoding="utf-8",
            )

            provider = LocalCsvMarketDataProvider(quote_path=quote_path)
            result = provider.get_quotes(["TWSE:2330"])

        self.assertTrue(result.ok)
        self.assertEqual(len(result.items), 1)
        quote = result.items[0]
        self.assertEqual(quote.instrument_id, "TWSE:2330")
        self.assertEqual(quote.provider_id, "local_csv")
        self.assertEqual(quote.price, 100)
        self.assertEqual(quote.previous_close, 95)
        self.assertEqual(quote.change, 5)
        self.assertEqual(quote.change_pct, 5.263157)
        self.assertEqual(quote.source_timestamp.isoformat(), "2026-06-24T10:00:00+08:00")
        self.assertEqual(quote.freshness, "manual")
        self.assertEqual(quote.source, "local_sample")
        self.assertEqual(quote.currency, "TWD")

    def test_loads_local_history_from_csv(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            history_path = Path(temp_dir) / "history.csv"
            history_path.write_text(
                "\n".join(
                    [
                        "instrument_id,date,open,high,low,close,volume,value,source_timestamp,freshness,source,adjusted",
                        "TWSE:2330,2026-06-24,100,110,99,108,12345,1234500,2026-06-24T14:00:00+08:00,end_of_day,local_sample,false",
                        "TWSE:2330,2026-06-25,108,112,107,111,23456,2345600,2026-06-25T14:00:00+08:00,end_of_day,local_sample,true",
                        "TWSE:9999,2026-06-24,1,1,1,1,1,1,2026-06-24T14:00:00+08:00,end_of_day,local_sample,false",
                    ]
                ),
                encoding="utf-8",
            )

            provider = LocalCsvMarketDataProvider(history_path=history_path)
            result = provider.get_daily_bars("TWSE:2330", date(2026, 6, 24), date(2026, 6, 25))

        self.assertTrue(result.ok)
        self.assertEqual([bar.date.isoformat() for bar in result.items], ["2026-06-24", "2026-06-25"])
        first = result.items[0]
        second = result.items[1]
        self.assertEqual(first.provider_id, "local_csv")
        self.assertEqual(first.close, 108)
        self.assertEqual(first.volume, 12345)
        self.assertEqual(first.source, "local_sample")
        self.assertFalse(first.adjusted)
        self.assertTrue(second.adjusted)

    def test_missing_quote_and_history_return_structured_issues(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            quote_path = Path(temp_dir) / "quotes.csv"
            history_path = Path(temp_dir) / "history.csv"
            quote_path.write_text("instrument_id,price\nTWSE:2330,100\n", encoding="utf-8")
            history_path.write_text("instrument_id,date,close\nTWSE:2330,2026-06-24,100\n", encoding="utf-8")

            provider = LocalCsvMarketDataProvider(quote_path=quote_path, history_path=history_path)
            quote_result = provider.get_quotes(["TWSE:9999"])
            history_result = provider.get_daily_bars("TWSE:9999", date(2026, 6, 24), date(2026, 6, 25))

        self.assertFalse(quote_result.ok)
        self.assertEqual(quote_result.items, ())
        self.assertEqual(quote_result.issues[0].code, "quote_not_found")
        self.assertEqual(quote_result.issues[0].instrument_id, "TWSE:9999")
        self.assertFalse(history_result.ok)
        self.assertEqual(history_result.items, ())
        self.assertEqual(history_result.issues[0].code, "history_not_found")
        self.assertEqual(history_result.issues[0].instrument_id, "TWSE:9999")


if __name__ == "__main__":
    unittest.main()
