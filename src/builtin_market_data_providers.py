from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from local_csv_market_data_provider import LocalCsvMarketDataProvider
from market_data_providers import ProviderRegistry
from yfinance_quote_provider import YFinanceQuoteProvider


def create_builtin_provider_registry(
    *,
    local_quote_path: Path | None = None,
    local_history_path: Path | None = None,
    symbol_for_instrument: Callable[[str], str] | None = None,
) -> ProviderRegistry:
    registry = ProviderRegistry()
    local_csv_provider = LocalCsvMarketDataProvider(
        quote_path=local_quote_path,
        history_path=local_history_path,
    )

    registry.register_quote_provider(YFinanceQuoteProvider(symbol_for_instrument=symbol_for_instrument))
    registry.register_quote_provider(local_csv_provider)
    registry.register_history_provider(local_csv_provider)
    return registry
