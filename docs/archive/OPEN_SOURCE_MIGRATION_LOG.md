# Open Source Migration Log

This checkpoint records the current framework migration state. It is not permission to refactor broadly, wire new providers into runtime flows, or change application behavior.

## Completed Tasks

- Task 1: Open-source hygiene.
  - Updated ignore and public-readiness documentation.
  - Reinforced that credentials, tokens, broker documents, private ledgers, local databases, generated runtime files, and private network details must stay out of commits.

- Task 2: Runtime/config inventory.
  - Created the runtime/config inventory documenting hardcoded profile, path, market, provider, schedule, broker, and UI assumptions that need to become configurable.

- Task 3: Accounting regression tests.
  - Added tests for FIFO lot consumption, realized P&L, manual dividend income separation, total earned, split adjustment, and duplicate transaction detection.

- Task 4: Settings loader.
  - Added a settings module and default-settings tests.
  - Settings are not wired into runtime yet.

- Task 5A: Market data result types.
  - Added provider-neutral result objects for quotes, OHLCV bars, provider issues, and provider results.

- Task 5B: Provider interfaces and registry.
  - Added capability-based market data provider protocols and registry tests.

- Task 5C: yfinance quote provider adapter.
  - Added a standalone yfinance quote provider adapter and tests.
  - Adapter is not wired into dashboard, CLI, scheduler, or server flows.

- Task 5D: Local CSV market data provider.
  - Added a no-network local CSV provider and tests.

- Task 5E: Market data provider docs and sample data.
  - Added provider documentation.
  - Added synthetic sample market CSV files.
  - Added tests that load sample data through the local CSV provider.

## Fixes

- Fixed holding card price precedence for Taiwan stocks.
  - Same-day official daily close now overrides same-day stale yfinance/cache quote for the main holding price.
  - After-close quote remains separate.
  - Tests now pass 26/26.

## Files Created Or Changed

- `.gitignore`
- `AGENTS.md`
- `docs/DISCLAIMER.md`
- `docs/MARKET_DATA_PROVIDERS.md`
- `docs/MIGRATION_LOG.md`
- `docs/OPEN_SOURCE_MIGRATION_LOG.md`
- `docs/RUNTIME_CONFIG_INVENTORY.md`
- `docs/SECURITY_AND_PRIVACY.md`
- `sample_data/market/ohlcv_daily.csv`
- `sample_data/market/quotes.csv`
- `src/local_csv_market_data_provider.py`
- `src/market_data_providers.py`
- `src/market_data_types.py`
- `src/settings.py`
- `src/yfinance_quote_provider.py`
- `tests/test_accounting_regressions.py`
- `tests/test_local_csv_market_data_provider.py`
- `tests/test_market_data_providers.py`
- `tests/test_market_data_types.py`
- `tests/test_sample_market_data.py`
- `tests/test_settings_defaults.py`
- `tests/test_yfinance_quote_provider.py`

## Current Test Status

- Command: `python -m unittest discover -s tests -v`
- Status: 26/26 tests passing.

## Runtime Wiring Status

Provider foundation work is standalone only. `YFinanceQuoteProvider`, `LocalCsvMarketDataProvider`, provider result types, and the provider registry are not wired into runtime dashboard, server, CLI, scheduler, or market refresh flows yet.

## Recommended Next Task

Create a standalone built-in provider registration helper that registers `YFinanceQuoteProvider` and `LocalCsvMarketDataProvider`.

Constraints:

- Keep it standalone.
- Add registry-construction tests only.
- Do not wire it into runtime dashboard flows.
- Do not change runtime behavior.
- Do not refactor application modules.
