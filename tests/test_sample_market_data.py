from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from local_csv_market_data_provider import LocalCsvMarketDataProvider


class SampleMarketDataTests(unittest.TestCase):
    def test_synthetic_sample_csv_files_load_through_local_provider(self) -> None:
        provider = LocalCsvMarketDataProvider(
            quote_path=ROOT / "sample_data" / "market" / "quotes.csv",
            history_path=ROOT / "sample_data" / "market" / "ohlcv_daily.csv",
        )

        quote_result = provider.get_quotes(["SAMPLE:AAA", "SAMPLE:BBB"])
        history_result = provider.get_daily_bars("SAMPLE:AAA", date(2026, 1, 13), date(2026, 1, 15))

        self.assertTrue(quote_result.ok)
        self.assertEqual([quote.instrument_id for quote in quote_result.items], ["SAMPLE:AAA", "SAMPLE:BBB"])
        self.assertEqual(quote_result.items[0].source, "synthetic_sample")
        self.assertEqual(quote_result.items[0].currency, "USD")
        self.assertTrue(history_result.ok)
        self.assertEqual(len(history_result.items), 3)
        self.assertEqual(history_result.items[-1].close, 42.5)
        self.assertEqual(history_result.items[-1].source, "synthetic_sample")


if __name__ == "__main__":
    unittest.main()
