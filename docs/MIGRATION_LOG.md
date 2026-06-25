# Migration Log

This handoff summarizes the framework migration foundation completed so far. Do not treat this as permission to refactor broadly.

## Completed Tasks

- Task 1: Open-source hygiene.
  - Updated `.gitignore`.
  - Updated `docs/SECURITY_AND_PRIVACY.md`.
  - Updated `docs/DISCLAIMER.md`.

- Task 2: Runtime/config inventory.
  - Created `docs/RUNTIME_CONFIG_INVENTORY.md`.

- Task 3: Accounting regression tests.
  - Added `tests/test_accounting_regressions.py`.
  - Covered FIFO lot consumption, realized P&L, manual dividend income separation, total earned, split adjustment, and duplicate transaction detection.

- Task 4: Settings loader.
  - Added `src/settings.py`.
  - Added `tests/test_settings_defaults.py`.
  - Settings are not wired into runtime yet.

- Task 5A: Market data result types.
  - Added `src/market_data_types.py`.
  - Added `tests/test_market_data_types.py`.

- Task 5B: Provider interfaces and registry.
  - Added `src/market_data_providers.py`.
  - Added `tests/test_market_data_providers.py`.

- Task 5C: yfinance quote provider adapter.
  - Added `src/yfinance_quote_provider.py`.
  - Added `tests/test_yfinance_quote_provider.py`.
  - Adapter is standalone and not wired into dashboard flows.

- Task 5D: Local CSV market data provider.
  - Added `src/local_csv_market_data_provider.py`.
  - Added `tests/test_local_csv_market_data_provider.py`.
  - Provider uses local files only and makes no network calls.

- Task 5E: Market data provider docs and sample data.
  - Added `docs/MARKET_DATA_PROVIDERS.md`.
  - Added synthetic sample files under `sample_data/market/`.
  - Added `tests/test_sample_market_data.py`.

## Current Test Status

- Command: `python -m unittest discover -s tests -v`
- Status: 19/19 tests passed.

## Important Files

- Planning and handoff:
  - `docs/FRAMEWORK_MIGRATION_PLAN.md`
  - `docs/RUNTIME_CONFIG_INVENTORY.md`
  - `docs/MIGRATION_LOG.md`

- Safety and public-readiness docs:
  - `.gitignore`
  - `docs/SECURITY_AND_PRIVACY.md`
  - `docs/DISCLAIMER.md`
  - `docs/MARKET_DATA_PROVIDERS.md`

- New framework foundation modules:
  - `src/settings.py`
  - `src/market_data_types.py`
  - `src/market_data_providers.py`
  - `src/yfinance_quote_provider.py`
  - `src/local_csv_market_data_provider.py`

- Tests:
  - `tests/test_accounting_regressions.py`
  - `tests/test_settings_defaults.py`
  - `tests/test_market_data_types.py`
  - `tests/test_market_data_providers.py`
  - `tests/test_yfinance_quote_provider.py`
  - `tests/test_local_csv_market_data_provider.py`
  - `tests/test_sample_market_data.py`

- Synthetic sample data:
  - `sample_data/market/quotes.csv`
  - `sample_data/market/ohlcv_daily.csv`

## Do Not Change Yet

- Do not refactor the whole project.
- Do not wire provider adapters into `server.py`, scheduler jobs, CLI commands, or dashboard flows yet.
- Do not change runtime behavior.
- Do not rename `son` or `mom` profiles yet.
- Do not move private runtime data.
- Do not change existing `market.py`, `official_market.py`, `central_store.py`, or `server.py` unless a later task explicitly requires it.

## Recommended Next Task

Commit the current Task 5E handoff/docs/sample-data changes, then start a small provider registry composition task:

- Create a built-in provider factory/registration helper that registers `YFinanceQuoteProvider` and `LocalCsvMarketDataProvider`.
- Keep it standalone.
- Do not wire it into runtime dashboard flows.
- Add tests for registry construction only.

