# Framework Migration Plan

Goal: convert `stock_daily_helper` from a personal local dashboard into an open-source, framework-oriented local stock journal and assistant system.

This plan is intentionally incremental. The current app contains useful domain behavior, but much of it is embedded in route handlers, local profile assumptions, Taiwan market assumptions, and provider-specific functions. The migration should first create stable boundaries around that behavior before changing features.

## 1. Current Architecture Summary

The current application is a local-first Flask web app with a CLI entry point:

- `src/main.py` resolves the project root and delegates to `src/cli.py`.
- `src/cli.py` defines commands for serving the dashboard, manual transactions, market-data sync, database migration, dividend import, Gmail checks, and attachment download.
- `src/server.py` is the main composition layer. It creates the Flask app, initializes local data stores, defines routes and API endpoints, starts background refresh jobs, reads profile ledgers, enriches holdings with market data, handles uploads, extracts PDF text, and performs some market-history backfill logic.
- `src/store.py` manages profile JSON ledgers: buys, sells, cash, watchlist entries, transaction IDs, FIFO lot accounting, realized P&L, split application, and rebuilt holdings.
- `src/central_store.py` owns SQLite persistence for market and shared data. It creates segmented market databases, migrates legacy DBs, stores instruments, quotes, OHLCV rows, intraday snapshots, after-close quotes, dividend records, corporate actions, update status, operation logs, uploads, Gmail receipts, health summaries, and market-data issues.
- `src/market.py` wraps yfinance quote fetching, caching, intraday 15-minute row generation, market-hour gating, and manual price overrides.
- `src/official_market.py` fetches TWSE/TPEx official daily data, listed company profiles, and yfinance daily history fallback rows.
- `src/official_sync.py` catches up missing official daily bars for instruments.
- `src/dividend_fetcher.py` fetches and parses TWSE ETF dividend data plus Yahoo dividend pages.
- `src/gmail_reader.py` uses Gmail read-only OAuth to find broker-statement PDFs, deduplicate them, store files, and record receipts.
- `src/analyzer.py` converts raw profile state and enriched quotes into dashboard summaries, holding/watchlist analysis, signals, source badges, and recent transaction slices.
- `src/templates` and `src/static` implement the browser UI. The frontend is profile-aware but still assumes dashboard routes and Taiwan-oriented labels, markets, schedules, and display conventions.

Storage is split between:

- Profile JSON files under `data/profiles/<profile>/state.json`.
- Segmented SQLite market databases under `data/market_data`.
- Quote cache JSON under `data/quotes_cache.json`.
- Uploaded documents under `data/uploads/<profile>/...`.
- Local config files for external integrations.

The documented architectural intent already separates account data from central market data, avoids external API calls on normal page opens where possible, records health/issues, and keeps import staging separate from confirmed ledgers. The current implementation partially follows this, but several boundaries are still implicit rather than enforced by module contracts.

## 2. Private Assumptions That Must Be Removed

The open-source framework must remove or make configurable these assumptions:

- Fixed profiles: `son`, `mom`, `DEFAULT_PROFILE = "son"`, hardcoded profile labels, hardcoded profile navigation, and default upload profile values.
- Private runtime artifacts in the repository tree: real data, credentials, tokens, local databases, broker PDFs/screenshots, generated logs, generated reports, and backup archives must be excluded from source and moved into ignored local runtime locations.
- Broker-specific Gmail behavior: default sender, subject patterns, query strings, PDF-only assumptions, and statement date parsing should become adapter configuration.
- Taiwan-first market model: TWSE/TPEx/ETF segmentation, `.TW` and `.TWO` suffixes, Taiwan market hours, ROC date parsing, Taiwan-specific names/labels, TWD defaults, broker fee/tax defaults, and dividend source assumptions must be provider/market configuration.
- Yahoo/yfinance as built-in behavior: quote, daily history, dividend fallback, source labels, cache shape, and freshness policy should depend on a provider interface.
- Global US market watch symbols: index/stock symbols used as dashboard context should be configured by the journal owner or a market plugin.
- Direct filesystem paths: `data/...`, `config/gmail_credentials.json`, `config/gmail_token.json`, `output/...`, and upload paths should come from an app settings object.
- Share-token security model: query-string token propagation is acceptable for private local use but should be documented as a local-only option and isolated behind an auth/session interface.
- UI language and text: labels, signals, and messages are currently app-specific and should move toward configurable copy or localization files.
- Investment heuristics: dashboard signals such as profit/stop-loss/dividend-month logic should be optional assistant rules, not framework core.
- SQLite schema tied to one market universe: fields like `yahoo_symbol`, `exchange_suffix`, `etf_dividends`, and segmented DB names should be generalized or adapter-owned.
- Startup behavior: automatic migrations, profile seeding, health rebuilds, and optional refresh jobs should be controlled by explicit configuration.

## 3. Proposed Module Boundaries

Target package boundaries:

- `journal_core`
  - Domain models and pure rules: accounts, portfolios, instruments, transactions, lots, cash movements, dividends, notes, documents, import batches, assistant signals, and journal entries.
  - No Flask, no provider SDKs, no direct filesystem assumptions.

- `journal_storage`
  - Repository interfaces and local implementations.
  - SQLite repositories for instruments, market data, documents, operation logs, health summaries, and issues.
  - JSON or SQLite repository for account ledgers, with migration support from current profile JSON files.

- `journal_market`
  - Provider-neutral service layer for quotes, OHLCV, dividends, market calendars, symbol lookup, corporate actions, source quality, and safety checks.
  - Handles provider selection, cache policy, fallback policy, throttling, and source precedence.

- `journal_imports`
  - Document ingestion, upload library, email connectors, extractors, parsers, import staging, duplicate detection, and review workflow.
  - Parser outputs staging rows only; final ledger writes stay in `journal_core` services.

- `journal_assistant`
  - Optional assistant rules and report generation.
  - Consumes journal and market snapshots; does not mutate ledgers unless an explicit reviewed action is accepted.

- `journal_web`
  - Flask app factory, route registration, API serializers, templates, static assets, local auth/session hooks, and frontend settings bootstrap.
  - Depends on service interfaces, not concrete provider modules.

- `journal_cli`
  - Command registration and dependency wiring.
  - Commands should call services through interfaces rather than import storage/provider functions directly.

- `journal_plugins`
  - Built-in plugin loader, plugin manifests, adapter registration, and optional third-party plugin discovery.

The first migration should not physically move every file. It should introduce interfaces and facades in place, then gradually move code behind them.

## 4. Provider Interface Design

Provider interfaces should be small, typed, and capability-based. A provider may implement only the capabilities it supports.

Suggested data types:

```python
@dataclass(frozen=True)
class MarketRef:
    code: str                  # "TWSE", "TPEX", "NASDAQ", "NYSE"
    timezone: str              # IANA timezone
    currency: str

@dataclass(frozen=True)
class InstrumentRef:
    instrument_id: str
    ticker: str
    market: str
    type: str
    display_name: str = ""
    aliases: tuple[str, ...] = ()

@dataclass(frozen=True)
class Quote:
    instrument_id: str
    price: float | None
    previous_close: float | None
    quote_time: datetime | None
    source: str
    quality: str               # realtime, delayed, end_of_day, stale, manual, unavailable
    errors: tuple[str, ...] = ()

@dataclass(frozen=True)
class OhlcvBar:
    instrument_id: str
    date: date
    open: float | None
    high: float | None
    low: float | None
    close: float | None
    volume: int | None
    value: float | None
    source: str
    adjusted: bool = False
```

Suggested capability protocols:

```python
class InstrumentProvider(Protocol):
    provider_id: str
    def search(self, query: str, market: str | None = None) -> list[InstrumentRef]: ...
    def get_profile(self, instrument: InstrumentRef) -> InstrumentRef | None: ...

class QuoteProvider(Protocol):
    provider_id: str
    def supports(self, instrument: InstrumentRef) -> bool: ...
    def get_quotes(self, instruments: list[InstrumentRef]) -> list[Quote]: ...

class HistoryProvider(Protocol):
    provider_id: str
    def supports(self, instrument: InstrumentRef, interval: str) -> bool: ...
    def get_daily_bars(self, instrument: InstrumentRef, start: date, end: date) -> list[OhlcvBar]: ...

class DividendProvider(Protocol):
    provider_id: str
    def supports(self, instrument: InstrumentRef) -> bool: ...
    def get_dividends(self, instrument: InstrumentRef, start: date, end: date) -> list[DividendEvent]: ...

class MarketCalendarProvider(Protocol):
    provider_id: str
    def market_hours(self, market: str, day: date) -> MarketHours: ...
    def is_refresh_allowed(self, market: str, at: datetime, data_type: str) -> bool: ...
```

Provider results should include source, timestamp, freshness, and quality metadata. Provider exceptions should be normalized into structured errors so one failed provider does not break the whole dashboard.

Provider selection should be declarative:

```yaml
markets:
  TWSE:
    timezone: Asia/Taipei
    currency: TWD
    quotes: [yfinance]
    daily_history: [twse_official, yfinance]
    dividends: [twse_etfortune, yahoo_tw]
    source_precedence:
      daily_history: [twse_official, tpex_official, yfinance]
```

## 5. Plugin / Adapter Design

Plugins should package provider adapters, import adapters, assistant rules, UI extensions, or sample configurations without requiring framework code changes.

Plugin manifest:

```toml
[plugin]
id = "tw-markets"
name = "Taiwan Market Providers"
version = "0.1.0"

[capabilities]
markets = ["TWSE", "TPEX"]
providers = ["twse_official", "tpex_official", "yahoo_tw", "yfinance"]
imports = ["gmail_pdf_statement"]
assistant_rules = ["tw_dividend_etf_signals"]
```

Adapter registration:

```python
def register(registry: PluginRegistry) -> None:
    registry.market_provider(TwseOfficialHistoryProvider())
    registry.market_provider(TpexOfficialHistoryProvider())
    registry.quote_provider(YFinanceQuoteProvider())
    registry.dividend_provider(TwseEtfDividendProvider())
    registry.import_adapter(GmailStatementAdapter())
```

Adapter categories:

- Market adapters: quotes, daily OHLCV, intraday bars, dividends, corporate actions, instrument profiles, market calendars.
- Broker/import adapters: Gmail search, file naming, statement date detection, document parsers, duplicate-key strategies, staging row validators.
- Storage adapters: local JSON profile ledgers, SQLite, future Postgres or DuckDB, encrypted local storage.
- Assistant adapters: signal rules, report sections, explanation templates, optional AI parser/provider.
- UI adapters: labels, market filters, document type options, assistant rule settings, dashboard cards.

Plugin constraints:

- A plugin must declare which capabilities it owns.
- A plugin must not write confirmed ledger entries directly.
- A plugin must not bypass market data safety rules.
- A plugin must not require secrets at import time.
- A plugin should be testable with fake data and no network.

## 6. Market Data Safety Rules

Core safety rules:

- Dashboard rendering should prefer local cached data and precomputed summaries. Provider calls should happen only through explicit refresh jobs or user-triggered refreshes.
- Official or primary-source OHLCV must not be overwritten by auxiliary sources. Fallback data should be stored separately or clearly marked with source and quality.
- Every market data row must carry provider ID, fetched timestamp, source timestamp/date, adjustment status, and quality.
- Quote freshness must be visible. Stale, cached, manual, delayed, and unavailable data should be distinguishable in APIs and UI.
- Provider failures should be recorded as structured issues and operation logs. One failed ticker/provider must not fail the entire refresh.
- Refreshes must respect market calendars, market hours, provider rate limits, and backoff policies.
- Historical backfill should be idempotent, resumable, and bounded by configured retention or requested date ranges.
- Name, ticker, and alias changes must preserve stable instrument IDs.
- Delisted or unsupported instruments must remain resolvable for old journal entries.
- Corporate actions should be explicit records and should not silently rewrite transaction history.
- Dividend calendar estimates and actual received dividends must remain separate.
- Broker/import/AI parser output must go to staging rows until reviewed by the user.
- The framework must never place trades or connect to brokerage trading APIs by default.
- Financial advice language should be avoided in core. Assistant outputs should be framed as journal analysis or user-configured rules.

Open-source hygiene rules:

- No real credentials, tokens, broker documents, private ledgers, local databases, private IPs, or generated runtime files in commits.
- Sample data must be synthetic.
- Logs must avoid full document text, tokens, passwords, and account identifiers.

## 7. First 10 Small Implementation Tasks

1. Add a runtime/config inventory document listing every hardcoded profile, path, market, provider, schedule, and broker assumption.
2. Move `PROFILES`, `DEFAULT_PROFILE`, currency, fee/tax defaults, refresh windows, dashboard indexes, and Gmail query defaults into a single app settings loader while keeping current defaults.
3. Add tests around current FIFO accounting, split application, profile state normalization, duplicate transaction detection, and dashboard summary totals before refactoring behavior.
4. Introduce provider result dataclasses for quotes and daily bars, then adapt `market.py` and `official_market.py` internally without changing callers.
5. Create a market provider registry and register current yfinance, TWSE, TPEx, Yahoo dividend, and manual override behavior as built-in adapters.
6. Add a storage repository facade for profile ledgers and market data, initially delegating to `store.py` and `central_store.py`.
7. Extract Gmail-specific statement matching into a broker import adapter configuration and keep the current pattern as a private/local example, not a framework default.
8. Replace profile-specific routes and UI defaults with dynamic profile lists from settings.
9. Add a repository hygiene pass: update ignore rules, move private runtime files out of tracked paths, and add synthetic sample config/data.
10. Split `server.py` into route modules and service facades only after the settings, provider, and storage seams exist.

## 8. Risks and Questions for User

Risks:

- Current runtime data appears to live inside the project tree. The migration needs a cleanup step before any open-source publication.
- `server.py` and `central_store.py` are large composition modules. Refactoring them too early would create high regression risk.
- Some current UI and backend strings appear encoding-damaged. Decide whether to preserve, repair, or replace them during localization.
- Provider behavior is mixed with business rules, caching, scheduling, and persistence. Tests are needed before extraction.
- Taiwan-market behavior is useful as a plugin, but it should not remain the framework default.
- Current Gmail integration is tied to one broker workflow. Generalizing it will require a clean adapter contract and sample-only defaults.
- Query-string share tokens are not enough for broad deployment. Keep local-first scope clear.
- SQLite segmented storage may be fine for local use, but framework APIs should not expose segment file details as domain concepts.

Questions:

- Should the open-source framework keep Taiwan-market adapters as built-in optional plugins, or move them to a separate package?
- Should account ledgers remain JSON-first, move to SQLite, or support both through storage adapters?
- What should be the default sample experience: empty journal, synthetic Taiwan portfolio, or provider-free demo data?
- Should the assistant layer include only deterministic rules at first, or also define an optional AI parser/reporting interface?
- Is the target audience individual local users, family portfolios, or developers building their own market journal apps?
- Should the first public release include the existing Flask UI, or prioritize the core library and CLI with the UI as one adapter?
