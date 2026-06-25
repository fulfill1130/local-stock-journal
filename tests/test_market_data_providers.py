from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from market_data_providers import ProviderRegistry
from market_data_types import OhlcvBar, ProviderResult, Quote


class FakeQuoteProvider:
    provider_id = "fake_quotes"

    def supports(self, instrument_id: str) -> bool:
        return instrument_id.startswith("TWSE:")

    def get_quotes(self, instrument_ids: list[str]) -> ProviderResult[Quote]:
        return ProviderResult(
            provider_id=self.provider_id,
            items=tuple(
                Quote(instrument_id=instrument_id, provider_id=self.provider_id, price=100)
                for instrument_id in instrument_ids
            ),
        )


class FakeHistoryProvider:
    provider_id = "fake_history"

    def supports(self, instrument_id: str, interval: str = "1d") -> bool:
        return instrument_id.startswith("TWSE:") and interval == "1d"

    def get_daily_bars(self, instrument_id: str, start: date, end: date) -> ProviderResult[OhlcvBar]:
        return ProviderResult(
            provider_id=self.provider_id,
            items=(
                OhlcvBar(
                    instrument_id=instrument_id,
                    provider_id=self.provider_id,
                    date=start,
                    close=100,
                ),
            ),
        )


class ProviderRegistryTests(unittest.TestCase):
    def test_registers_providers_by_capability(self) -> None:
        registry = ProviderRegistry()
        quote_provider = FakeQuoteProvider()
        history_provider = FakeHistoryProvider()

        registry.register_quote_provider(quote_provider)
        registry.register_history_provider(history_provider)

        self.assertEqual(registry.providers_for("quotes"), ["fake_quotes"])
        self.assertEqual(registry.providers_for("history"), ["fake_history"])
        self.assertIs(registry.quote_provider("fake_quotes"), quote_provider)
        self.assertIs(registry.history_provider("fake_history"), history_provider)

    def test_finds_providers_that_support_an_instrument(self) -> None:
        registry = ProviderRegistry()
        registry.register_quote_provider(FakeQuoteProvider())
        registry.register_history_provider(FakeHistoryProvider())

        self.assertEqual(
            [provider.provider_id for provider in registry.quote_providers_for_instrument("TWSE:2330")],
            ["fake_quotes"],
        )
        self.assertEqual(
            [provider.provider_id for provider in registry.quote_providers_for_instrument("NASDAQ:NVDA")],
            [],
        )
        self.assertEqual(
            [provider.provider_id for provider in registry.history_providers_for_instrument("TWSE:2330", "1d")],
            ["fake_history"],
        )
        self.assertEqual(
            [provider.provider_id for provider in registry.history_providers_for_instrument("TWSE:2330", "1m")],
            [],
        )

    def test_rejects_blank_provider_ids(self) -> None:
        class BlankQuoteProvider(FakeQuoteProvider):
            provider_id = ""

        registry = ProviderRegistry()

        with self.assertRaises(ValueError):
            registry.register_quote_provider(BlankQuoteProvider())


if __name__ == "__main__":
    unittest.main()
