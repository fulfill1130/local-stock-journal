from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from builtin_market_data_providers import create_builtin_provider_registry
from local_csv_market_data_provider import LocalCsvMarketDataProvider
from yfinance_quote_provider import YFinanceQuoteProvider


class BuiltinMarketDataProviderTests(unittest.TestCase):
    def test_constructs_registry_with_builtin_providers(self) -> None:
        registry = create_builtin_provider_registry()

        self.assertEqual(registry.providers_for("quotes"), ["yfinance", "local_csv"])
        self.assertEqual(registry.providers_for("history"), ["local_csv"])
        self.assertIsInstance(registry.quote_provider("yfinance"), YFinanceQuoteProvider)
        self.assertIsInstance(registry.quote_provider("local_csv"), LocalCsvMarketDataProvider)
        self.assertIsInstance(registry.history_provider("local_csv"), LocalCsvMarketDataProvider)

    def test_lookup_returns_supported_builtin_providers_without_fetching(self) -> None:
        registry = create_builtin_provider_registry()

        self.assertEqual(
            [provider.provider_id for provider in registry.quote_providers_for_instrument("TWSE:2330")],
            ["yfinance", "local_csv"],
        )
        self.assertEqual(
            [provider.provider_id for provider in registry.history_providers_for_instrument("TWSE:2330", "1d")],
            ["local_csv"],
        )
        self.assertEqual(registry.history_providers_for_instrument("TWSE:2330", "1m"), [])

    def test_passes_local_csv_paths_to_provider(self) -> None:
        quote_path = ROOT / "sample_data" / "market" / "quotes.csv"
        history_path = ROOT / "sample_data" / "market" / "ohlcv_daily.csv"

        registry = create_builtin_provider_registry(
            local_quote_path=quote_path,
            local_history_path=history_path,
        )
        provider = registry.quote_provider("local_csv")

        self.assertIsInstance(provider, LocalCsvMarketDataProvider)
        self.assertEqual(provider.quote_path, quote_path)
        self.assertEqual(provider.history_path, history_path)


if __name__ == "__main__":
    unittest.main()
