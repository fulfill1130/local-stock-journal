# Runtime Config Inventory

This inventory captures hardcoded runtime assumptions that should later move behind a settings loader or plugin/adapter configuration. This pass is documentation only: no runtime behavior, profile names, paths, or code structure were changed.

## Inspected Files

- `src/server.py`
- `src/cli.py`
- `src/market.py`
- `src/central_store.py`
- `src/gmail_reader.py`
- `src/utils.py`
- `src/static/app.js`
- `src/static/uploads.js`
- `src/templates/database.html`
- `src/templates/dividends.html`
- `src/templates/logs.html`
- `src/templates/uploads.html`
- `scripts/start_dashboard.ps1`
- `scripts/start_dashboard_tailscale.ps1`
- `scripts/allow_tailscale_firewall.ps1`
- `run_dashboard_server.cmd`

## Hardcoded Profiles

| Assumption | Current locations | Future settings bucket |
| --- | --- | --- |
| Profile IDs are `son` and `mom`. | `src/server.py` `PROFILES`; `src/templates/*`; `src/static/uploads.js` | `profiles` |
| Default profile is `son`. | `src/server.py` `DEFAULT_PROFILE`; `src/cli.py`; `src/static/app.js`; `src/static/uploads.js` | `profiles.default` |
| Profile labels are embedded UI text. | `src/server.py`; `src/templates/*`; `src/static/app.js` | `profiles[].label` or localization |
| Profile state path is `data/profiles/<profile>/state.json`. | `src/server.py` `profile_state_path` | `paths.profile_state` |
| Profile routes are `/<profile>` and `/<profile>/api/...`. | `src/server.py`; `src/static/app.js` | Web route config, later |

Do not rename or remove existing profiles until a settings loader exists and profile migration is tested.

## Hardcoded Paths

| Path or pattern | Current locations | Notes |
| --- | --- | --- |
| `data/market_data` | `src/server.py`; `src/cli.py` | Segmented market SQLite root. |
| `data/central.sqlite` | `src/server.py` | Legacy migration source. |
| `data/quotes_cache.json` | `src/server.py` | Local quote cache. |
| `data/refresh_log.json` | `src/server.py` | Scheduler/refresh log. |
| `data/cleanup_market_data.log` | `src/cli.py` | Cleanup command output. |
| `data/uploads/<profile>/<year>/<month>` | `src/server.py`; `src/gmail_reader.py` | Upload library and Gmail attachment storage. |
| `config/gmail_credentials.json` | `src/cli.py`; `src/server.py` | Gmail OAuth client secret path. |
| `config/gmail_token.json` | `src/cli.py`; `src/server.py` | Gmail OAuth token path. |
| Flask templates/static under `src/templates` and `src/static` | `src/server.py` | App factory assumes project layout. |
| Script logs under `data/*startup*.log` | `scripts/*.ps1` | Windows helper scripts assume local data directory. |
| `C:\Python314\python.exe` and private host IP | `run_dashboard_server.cmd`; `scripts/start_dashboard_tailscale.ps1` | Local machine assumptions, not framework defaults. |

Future settings bucket: `paths`, with separate runtime, config, upload, cache, log, and legacy paths.

## Hardcoded Markets and Symbols

| Assumption | Current locations | Future settings bucket |
| --- | --- | --- |
| Taiwan markets are represented by `TWSE`, `TPEX`, and `ETF`. | `src/central_store.py`; `src/official_market.py`; `src/official_sync.py`; `src/server.py`; `src/cli.py` | `markets` and market plugins |
| Market DB segment files are `twse.sqlite`, `tpex.sqlite`, and `etf.sqlite`. | `src/central_store.py` `SEGMENT_FILES` | Storage adapter config |
| Default exchange suffix is `.TW`; TPEx suffix is `.TWO`. | `src/utils.py`; `src/store.py`; `src/server.py`; `src/cli.py`; `src/market.py`; `src/static/database.js` | `markets[].symbol_aliases` |
| Tickers starting with `00` are inferred as ETF in some flows. | `src/server.py`; `src/central_store.py` | Instrument classifier plugin |
| Built-in dashboard context symbols include Nasdaq, S&P 500, SOX, NVDA, AMD, TSM, US10Y, and DXY. | `src/market.py` `US_MARKETS` | `dashboard.market_context` |
| Taiwan vs US market is inferred from suffix or known dashboard symbols. | `src/market.py` | Market calendar/provider registry |
| Currency defaults to `TWD`. | `src/server.py` profile state defaults | `profiles[].currency` or `markets[].currency` |

## Hardcoded Providers

| Provider assumption | Current locations | Future settings bucket |
| --- | --- | --- |
| yfinance is the quote provider and source label is `yfinance`. | `src/market.py`; `src/server.py`; `src/official_market.py` | `providers.quotes` |
| TWSE official daily data URL is built into code. | `src/official_market.py` | `providers.history.twse_official` |
| TPEx official daily data URL is built into code. | `src/official_market.py` | `providers.history.tpex_official` |
| TWSE listed company profile endpoint is built into code. | `src/official_market.py` | `providers.instrument_profiles.twse` |
| TWSE ETF dividend page is built into code. | `src/dividend_fetcher.py` | `providers.dividends.twse_etfortune` |
| Yahoo Taiwan dividend page and labels are built into code/UI. | `src/dividend_fetcher.py`; `src/server.py`; `src/static/dividends.js` | `providers.dividends.yahoo_tw` |
| Manual price overrides use source `manual`. | `src/market.py`; `src/store.py` | `providers.manual_overrides` |
| Source precedence is implicit: official data is preferred, Yahoo/yfinance is fallback or auxiliary. | `src/server.py`; `src/central_store.py`; docs | `market_data.source_precedence` |

Provider settings should eventually declare capabilities, rate limits, source quality, fallback order, and whether the provider is allowed for quotes, daily bars, dividends, or instrument lookup.

## Hardcoded Schedules

| Schedule | Current locations | Future settings bucket |
| --- | --- | --- |
| Central quote refresh every 15 minutes with 1 minute offset. | `src/server.py` scheduler setup | `schedules.quote_refresh` |
| Taiwan quote refresh window `09:01-13:01`. | `src/market.py`; `src/server.py` defaults | `markets.TWSE.hours` / `markets.TPEX.hours` |
| US quote refresh window `21:30-05:00`. | `src/market.py`; `src/server.py` defaults | `markets.US.hours` |
| After-close refresh at `13:31`. | `src/server.py`; `default_next_run_at` | `schedules.after_close` |
| Official daily refresh at `14:00`; startup skips before 14:00. | `src/server.py`; `default_next_run_at` | `schedules.official_daily` |
| Gmail statement scan at `23:30`. | `src/server.py`; `default_next_run_at` | `schedules.imports.gmail_statements` |
| Official history backfill every 30 minutes with 7 minute offset. | `src/server.py` | `schedules.history_backfill` |
| CLI history sync defaults to current year start through today. | `src/cli.py` | CLI command defaults |
| CLI request pauses: 1.0s monthly, 3.0s per ticker, 0.5s official daily. | `src/cli.py` | Provider throttle defaults |

## Gmail Assumptions

| Assumption | Current locations | Future settings bucket |
| --- | --- | --- |
| Gmail readonly scope is fixed. | `src/gmail_reader.py` | `imports.gmail.scopes` |
| Credentials path is `config/gmail_credentials.json`. | `src/cli.py`; `src/server.py` | `imports.gmail.credentials_path` |
| Token path is `config/gmail_token.json`. | `src/cli.py`; `src/server.py` | `imports.gmail.token_path` |
| Search query assumes sender `service@billu.tssco.com.tw`. | `src/cli.py`; `src/server.py` | Broker import adapter config |
| Search query assumes PDF attachments. | `src/cli.py`; `src/gmail_reader.py` | Broker import adapter config |
| Scheduled scan writes only to profile `son`. | `src/server.py` | `imports.gmail.target_profile` |
| Subject pattern is broker-specific and encoded in a regex/string. | `src/gmail_reader.py`; `src/cli.py`; `src/server.py` | Broker import adapter config |
| Statement date is inferred from filename or subject with YYYYMMDD / YYYY-MM-DD / YYYY.MM.DD patterns. | `src/gmail_reader.py` | Document parser config |
| Gmail integration downloads attachments but does not parse directly into transactions. | `src/gmail_reader.py`; `src/server.py` | Keep as safety rule |

## Broker and Accounting Assumptions

| Assumption | Current locations | Future settings bucket |
| --- | --- | --- |
| Broker fee default is `0.001425`. | `src/server.py` profile defaults and transaction handling | `broker_defaults.fee_rate` |
| Transaction tax default is `0.003`. | `src/server.py` profile defaults and transaction handling | `broker_defaults.transaction_tax_rate` |
| CLI transaction fee/tax defaults are `0.0`. | `src/cli.py` | CLI command defaults |
| Only `BUY` and `SELL` are first-class trade actions in the core ledger flow. | `src/store.py`; `src/server.py`; docs | Journal transaction schema |
| FIFO is the cost basis model. | `src/store.py`; docs | `accounting.cost_basis` |
| Uploaded documents are stored as private broker/account records. | `src/server.py`; `src/gmail_reader.py`; docs | Import adapter config |
| PDF text extraction is local and password-aware, but OCR/AI parsing is not wired as core behavior. | `src/server.py`; docs | Parser adapter config |
| Import output should remain staged/reviewed before final transaction writes. | docs and current upload flow | Safety rule |

## Local Server and Access Assumptions

| Assumption | Current locations | Future settings bucket |
| --- | --- | --- |
| Default host is `127.0.0.1`; default port is `8787`. | `src/cli.py`; `scripts/start_dashboard.ps1` | `server.host`, `server.port` |
| Optional share token is passed through query string or `X-Share-Token`. | `src/server.py`; frontend token helpers | `auth.local_share_token` |
| Tailscale script discovers a Tailscale IP and opens profile path. | `scripts/start_dashboard_tailscale.ps1` | Local deployment helper config |
| Firewall helper opens port `8787` for Tailscale. | `scripts/allow_tailscale_firewall.ps1` | Local deployment helper config |
| `run_dashboard_server.cmd` hardcodes a Windows Python path and private host IP. | `run_dashboard_server.cmd` | Local-only script, not framework default |

## UI and Localization Assumptions

| Assumption | Current locations | Future settings bucket |
| --- | --- | --- |
| Browser locale formatting uses `zh-TW`. | `src/static/app.js`; `src/static/uploads.js`; other static JS | `ui.locale` |
| Data status labels, source labels, assistant signals, and profile labels are embedded in code/templates. | `src/server.py`; `src/analyzer.py`; `src/static/*.js`; templates | Localization files |
| Database/upload pages hardcode top links to `son` and `mom`. | `src/templates/database.html`; `src/templates/dividends.html`; `src/templates/logs.html`; `src/templates/uploads.html` | Dynamic profile nav from settings |
| Upload page hardcodes profile select options. | `src/templates/uploads.html` | Dynamic profiles from settings |

Some UI/backend strings appear encoding-damaged in the current files. Treat that as a separate cleanup/localization task, not part of this settings pass.

## Suggested Settings Buckets

The eventual settings loader can start with a single local config object shaped around these buckets:

```yaml
server:
  host: 127.0.0.1
  port: 8787
  share_token: ""

paths:
  runtime_dir: data
  config_dir: config
  market_data_dir: data/market_data
  profiles_dir: data/profiles
  uploads_dir: data/uploads
  quote_cache: data/quotes_cache.json
  refresh_log: data/refresh_log.json

profiles:
  default: son
  items:
    - slug: son
      label: Son
      currency: TWD
    - slug: mom
      label: Mom
      currency: TWD

markets:
  TWSE:
    timezone: Asia/Taipei
    currency: TWD
    suffixes: [.TW]
  TPEX:
    timezone: Asia/Taipei
    currency: TWD
    suffixes: [.TWO]

providers:
  quotes: [yfinance]
  daily_history: [twse_official, tpex_official]
  dividends: [twse_etfortune, yahoo_tw]

schedules:
  quote_refresh_minutes: 15
  after_close: "13:31"
  official_daily: "14:00"
  gmail_statements: "23:30"
  history_backfill_minutes: 30

imports:
  gmail:
    enabled: false
    credentials_path: config/gmail_credentials.json
    token_path: config/gmail_token.json
    target_profile: son
  broker_statement:
    attachment_types: [pdf]
    require_review: true

broker_defaults:
  fee_rate: 0.001425
  transaction_tax_rate: 0.003

ui:
  locale: zh-TW
  dashboard_market_context: []
```

This is an inventory shape only. Introducing the loader should happen in a separate, tested change.

