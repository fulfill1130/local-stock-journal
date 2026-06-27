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

## ETF Holdings Providers

ETF holdings providers load, parse, normalize, and validate holdings snapshots only. They do not write SQLite directly; callers must persist accepted snapshots through the existing ETF holdings storage helper.

`LocalCsvEtfHoldingsProvider` reads the synthetic `sample_data/market/etf_holdings.csv` format for offline tests and demos.

Manual ETF holdings CSV import is the first real input path for ETF component snapshots. It supports preview before confirmation and writes only market/research data through the ETF holdings storage helper. Imported ETF holdings are not account ledger data and must not create transactions, lots, or final account records.

`ConfiguredHttpEtfHoldingsProvider` is a manual-trigger live provider foundation for optional local use. It is not wired into page-open loading, dashboard refresh, or any scheduler. The manual trigger endpoint previews provider output before confirmation and writes only accepted ETF holdings snapshots through the ETF holdings storage helper.

Source discovery found that Yahoo Finance is not a reliable Taiwan ETF holdings source for this app: the JSON holdings endpoint requires Yahoo crumb/cookie state, and the Taiwan Yahoo holdings page is HTML-only, partial, and stale-prone. TWSE public/OpenAPI endpoints are useful for trading, quote, iNAV, and basic market data, but they do not appear to provide actual ETF component holdings with weights.

`YuantaEtfHoldingsProvider` is the first issuer-specific provider candidate for Yuanta ETFs such as 0050 and 0056. It parses the public Yuanta ETF ratio page's stock-weight table into the existing ETF holdings snapshot shape. No stable CSV/export endpoint has been wired yet; the parser is therefore conservative HTML parsing and should be treated as fragile issuer-page integration.

`FubonEtfHoldingsProvider` is an issuer-specific manual-trigger provider for Fubon ETF fund assets pages, initially tested with 00900. It parses the stock holdings table into ETF components and ignores non-stock asset rows such as futures, cash, margin, and payable items as components. Those non-stock rows may be summarized in notes only. The source is an official issuer fund assets page, but the parser is still HTML-based and should be reviewed before confirmation.

Private live provider settings belong only in ignored local configuration:

```text
config/providers.local.json
```

Start from the committed safe template if you want the stock detail page to show a provider-source dropdown:

```powershell
copy config\providers.local.example.json config\providers.local.json
```

Then edit only the ignored local copy. The example file uses fake placeholder URLs and must not contain real keys, tokens, cookies, private URLs, or raw provider responses.

The stock detail provider update panel calls `GET /api/database/etf-holdings/providers?ticker=<ticker>` to list configured sources. That endpoint returns only safe metadata such as `provider_id`, `display_name`, `type`, `issuer`, ticker support, status, and a short message. It does not return URLs, headers, API keys, cookies, tokens, local file paths, cache paths, raw responses, account/profile data, transactions, lots, or holdings.

Safe local config shape:

```json
{
  "etf_holdings": {
    "providers": [
      {
        "provider_id": "example_etf_holdings",
        "type": "http",
        "url_env": "ETF_HOLDINGS_URL",
        "format": "csv",
        "tickers": ["DEMOA"],
        "source": "example_provider",
        "public_source_url": "https://example.invalid/holdings",
        "api_key_env": "ETF_HOLDINGS_API_KEY"
      }
    ]
  }
}
```

Yuanta manual-trigger example:

```json
{
  "etf_holdings": {
    "providers": [
      {
        "provider_id": "yuanta_etf_holdings",
        "type": "yuanta",
        "tickers": ["0050", "0056"]
      }
    ]
  }
}
```

Fubon manual-trigger example:

```json
{
  "etf_holdings": {
    "providers": [
      {
        "provider_id": "fubon_00900",
        "display_name": "Fubon 00900 ETF holdings",
        "issuer": "Fubon",
        "type": "fubon",
        "tickers": ["00900"]
      }
    ]
  }
}
```

The dropdown only selects a configured provider. It does not fetch provider holdings on page open or when changing tickers. Provider data is fetched only when the user presses Preview, and SQLite is written only after a successful preview and explicit confirmation. Manual CSV import remains visible as the fallback when no provider is configured, a ticker is unsupported, or an issuer source changes.

Do not commit API keys, authenticated URLs, cookies, private provider URLs, or raw provider responses. If raw response caching is explicitly enabled for local troubleshooting, cache files must stay under the ignored runtime path:

```text
data/provider_cache/etf_holdings/
```

Scheduler refresh, page-open provider fetching, and broader live-provider automation remain future work until provider health, error handling, and source quality are stable.

Manual CSV import remains the fallback path when issuer pages change, fields are missing, or provider terms/stability are unclear.

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
