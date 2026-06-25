# Market Data Providers

Market data providers are adapters that translate an external or local data source into provider-neutral result objects:

- `Quote` for latest or known quote data.
- `OhlcvBar` for daily OHLCV history.
- `ProviderIssue` for structured warnings and errors.
- `ProviderResult` for successful rows plus non-fatal issues.

The current dashboard is not wired to these provider adapters yet. Existing runtime behavior stays in the current modules until a later migration step.

## Provider Roles

Providers are capability-based:

- `QuoteProvider` returns quotes for one or more instrument IDs.
- `HistoryProvider` returns daily OHLCV bars for one instrument over a date range.
- `ProviderRegistry` can register providers by capability and find providers that support an instrument.

Provider adapters should not place trades, mutate ledgers, or write directly into final account records. They should return data plus structured issues so callers can decide how to cache, display, or reject the data.

## Local CSV Provider

`LocalCsvMarketDataProvider` is a no-network provider intended for development, tests, demos, and offline examples.

Quote CSV columns:

```text
instrument_id,price,previous_close,change,change_pct,source_timestamp,freshness,source,currency
```

Daily OHLCV CSV columns:

```text
instrument_id,date,open,high,low,close,volume,value,source_timestamp,freshness,source,adjusted
```

Example usage:

```python
from datetime import date
from pathlib import Path

from local_csv_market_data_provider import LocalCsvMarketDataProvider

provider = LocalCsvMarketDataProvider(
    quote_path=Path("sample_data/market/quotes.csv"),
    history_path=Path("sample_data/market/ohlcv_daily.csv"),
)

quotes = provider.get_quotes(["SAMPLE:AAA"])
bars = provider.get_daily_bars("SAMPLE:AAA", date(2026, 1, 1), date(2026, 1, 31))
```

The sample CSV files are synthetic. They are not broker records, account records, official exchange data, or redistributable market data.

## yfinance Adapter Status

`YFinanceQuoteProvider` is a thin adapter around the existing yfinance quote behavior in `market.py`.

Current status:

- It implements `QuoteProvider`.
- It converts the existing quote dictionary shape into `Quote`.
- It converts provider failures into `ProviderIssue`.
- It is not wired into the Flask app, CLI, scheduler, or dashboard.
- Tests mock the existing fetch function and do not make network calls.

## Why API Providers Are Optional

The framework should be useful without API keys, network access, or paid data subscriptions. Local CSV and synthetic sample providers support:

- Offline development.
- Deterministic tests.
- Safe demos with no private account data.
- Provider interface validation before integrating live sources.

Live API providers can be added as optional adapters later. They must respect provider terms, rate limits, source quality, and market data redistribution restrictions.

