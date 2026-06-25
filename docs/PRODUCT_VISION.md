# Product Vision

`stock_daily_helper` is a local-first stock journal and assistant framework.

Its core identity is a stock record system first and an analysis toolkit second. The ledger, documents, notes, and market data history are the durable product. Charts, indicators, assistant summaries, and automation should help users understand their own records, but must never replace the user's judgment or become trading automation.

## What The System Should Do

- Help users keep accurate local records of buys, sells, cash movements, dividends, documents, notes, and portfolio history.
- Preserve cost basis, realized profit, dividend income, and historical context in a reviewable journal.
- Provide clear dashboards, K-line views, indicators, health checks, and source badges from local or configured market data.
- Keep broker statements, screenshots, PDFs, OCR output, and AI parser output in a staged review flow before ledger changes.
- Support multiple accounts or profiles through configuration instead of hardcoded private defaults.
- Let developers add market providers, broker importers, assistant rules, reports, and UI extensions through small adapters or plugins.

## What The System Must Never Do

- Place trades or connect to brokerage trading APIs by default.
- Treat assistant output, indicators, or signals as financial advice.
- Silently rewrite transaction history, cost basis, dividends, or confirmed ledger entries.
- Commit or publish private ledgers, broker documents, OAuth tokens, credentials, local databases, private IPs, or generated runtime files.
- Require live API keys, paid data, or network access for tests, demos, or the basic sample experience.
- Let provider failures break the whole dashboard when cached or partial data can be shown safely.

## Local-First Data Ownership

Users own their data. The default architecture should keep journals, documents, market caches, logs, and settings on the user's machine. Any external service use must be explicit, configurable, and replaceable.

Runtime data should stay out of source control. Sample data must be synthetic. The project should remain useful offline through local CSV/demo providers and deterministic tests.

## Market Data Provider Principles

Market data should flow through capability-based providers for quotes, daily OHLCV, dividends, corporate actions, instrument lookup, and calendars.

Provider rows should carry source, provider ID, timestamps, freshness, adjustment status, quality, and structured issues. Primary or official data should not be overwritten by fallback data without clear source separation. Refresh jobs should respect calendars, market hours, rate limits, and backoff rules.

## Plugin And Assistant Principles

Plugins should package optional adapters without changing framework code. A plugin may add market providers, broker import rules, document parsers, assistant rules, reports, UI options, or external GitHub-hosted tool adapters.

Assistant tools should explain, summarize, extract, and stage. They should not mutate confirmed ledgers unless the user reviews and accepts the proposed change. AI parser output belongs in import staging first.

## Ledger Safety Rules

- Confirmed ledger writes must be explicit and reviewable.
- Duplicate detection and stable transaction IDs should guard imports.
- Corporate actions should be recorded as events, not hidden rewrites.
- Estimated dividends and actual received dividends must remain separate.
- Historical records for delisted or renamed instruments must remain resolvable.
- Tests should cover accounting behavior before refactoring storage or runtime flows.

## Future Direction

The framework should grow toward:

- K-line views and technical indicators over provider-neutral OHLCV data.
- Configurable assistant rules for journal review, risk notes, dividend tracking, and report generation.
- Optional AI-assisted parsing for broker PDFs, screenshots, and statements, always staged for review.
- External adapter packages, including GitHub-hosted tools for market data, importers, indicators, and reports.
- A clean demo/sample mode using synthetic local data with no credentials or private records.

## Open-Source Positioning

The open-source project should be a practical local stock journal framework for individuals, families, and developers building their own private market journal tools.

The public core should be provider-neutral, testable without network access, conservative about ledger mutation, and clear that it is not financial advice and not an automated trading system.
