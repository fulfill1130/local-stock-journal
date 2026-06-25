# Stock Detail Page Requirements

Page 2 is the single-instrument detail and research page for an account. Page 1 remains the account overview dashboard. Page 2 must not expand every holding into full detail at once; it should let the user choose one stock or ETF and focus the page on that selected instrument.

## Purpose

- Show detailed stock or ETF information for one selected ticker at a time.
- Support account review, transaction review, dividend review, K-line inspection, and assistant/plugin analysis for the selected instrument.
- Avoid duplicating the account dashboard or rendering all holdings in full detail.
- Keep the page local-first and read-oriented by default.

## Selection Behavior

- Provide one unified ticker/name search box.
- The search box should accept ticker code, Chinese name, or English name.
- Search local account data and the local central instrument database first.
- Do not call external APIs on page open or during default local search.
- User can select any held, watched, or searched instrument.
- Allow switching between held positions, watchlist/favorite instruments, and central database search results.
- Default to the previously selected ticker when possible.
- If no previous selection exists, default to the first current holding, then the first watchlist item.
- Preserve the selected ticker across refreshes when it still exists in holdings, watchlist, or local search results.
- If the selected ticker disappears, fall back safely and show an empty state when no instruments exist.

Selection results should be grouped:

1. My holdings
2. Watchlist / favorites
3. Search results from central instrument database

## Instrument States

Every selected instrument should have one of these states:

- `held`: The ticker exists in the selected account's current holdings.
- `watchlist`: The ticker is saved to the selected account's watchlist/favorites but is not currently held.
- `search_only`: The ticker exists in the central instrument database or local search results but is not held or watched by the selected account.

State-specific behavior:

- Held instruments show account-specific cost, shares, market value, unrealized P/L, P/L %, actual received dividends, lots, and transactions.
- Watchlist instruments show market data, dividends, K-line, data health, target/watch notes, and assistant/plugin analysis, but no account P/L.
- Search-only instruments show market data, dividends, K-line, data health, and optional notes when local data exists, but no account P/L.
- Users can add search-only instruments to watchlist/favorites.
- Users can later create a transaction from the selected instrument; the transaction flow must remain explicit and reviewed.

## Required Sections

### Header

Display ticker, name, type, main price, official close, after-close price, data time, and source badges.

The header should distinguish:

- Main selected display price.
- Official daily close.
- After-close quote.
- Quote or data timestamp.
- Source and freshness.

### My Holding Summary

Show account-specific position data:

- Shares.
- Average cost.
- Cost value.
- Market value.
- Unrealized P/L.
- Unrealized P/L percentage.
- Portfolio weight within the account.
- Break-even price when available or computable.

Watchlist-only instruments should show a clear non-held state instead of fake holding metrics.

Search-only instruments should also show a clear non-held state and should not display account P/L fields.

### Lot And Transaction History

Show lots and account transaction history for the selected ticker only:

- Open lots.
- Closed or partially consumed lots.
- Buy/sell transactions.
- Fees and taxes.
- Realized P/L where applicable.
- Corporate action context when present.

### Dividend History

Show both estimated/scheduled dividend data and actual received dividend records, clearly separated:

- Dividend schedule or forecast from market/dividend providers.
- Actual received dividends from the account ledger.
- Ex-dividend date, payout date, amount per share, and received cash when available.

### K-Line / OHLCV Chart

Show a local K-line or OHLCV chart for the selected instrument using existing local OHLCV rows first.

The chart should expose the selected date range, OHLCV values, source, and whether rows are official, fallback, adjusted, stale, or missing.

### ETF Holdings

For ETFs only, show ETF component holdings when an optional ETF holdings provider is configured.

If no provider is configured or no local data is available, show a clear unavailable state. Do not call an external provider just because the page opened.

### Market Data Health And Source

Show local data health for the selected instrument:

- Latest official daily row.
- Latest quote/cache row.
- Latest after-close quote.
- Missing history status.
- Source, timestamp, freshness, and known issues.
- Whether manual review is required.

### Assistant / Plugin Analysis

Provide a section for optional assistant and plugin output:

- Deterministic rule notes.
- Technical indicator summaries.
- Dividend or risk notes.
- External tool adapter output.
- AI summaries, when explicitly enabled.

Assistant output must be labeled as analysis, not financial advice.

## Data Sources

- Account ledger: shares, lots, transactions, cost basis, realized P/L, actual dividend income, notes, and account-specific settings.
- Central market database: instrument metadata, source records, health summaries, issues, corporate actions, quotes, after-close quotes, and operation status.
- Local OHLCV: K-line chart data, official daily close, historical price range, and indicator inputs.
- Dividend database: dividend schedule, market dividend events, payout estimates, and provider-sourced dividend records.
- ETF holdings provider: optional ETF components, component weights, sector allocation, and provider timestamp.
- Plugin/assistant output: analysis sections, indicators, report snippets, parser notes, and third-party adapter results.

## Safety Rules

- No external API call on page open.
- Unified search must query local account data and the local central instrument database first.
- Read local cached or precomputed data first.
- External refreshes must be explicit user actions or scheduled jobs, not passive page rendering.
- ETF holdings providers must be optional and replaceable.
- Analysis tools must not write confirmed transactions.
- Page 2 must not mutate ledger data unless the user explicitly performs a ledger action.
- AI or parser output must go to staging or review before it can affect confirmed ledger records.
- After-close quotes remain separate from official daily close and should not silently overwrite it.
- Provider failures should not break the whole page when local cached data can still be shown.

## MVP

The first implementation should stay small:

- Ticker selector for holdings and watchlist items.
- Unified ticker/name search over holdings, watchlist, and local central instrument records.
- Selected holding summary.
- Transaction lots for the selected ticker.
- Actual dividend records from the account ledger.
- Local K-line from existing OHLCV rows.
- Data health and source display.

The MVP should reuse existing `/account` state and local market data where practical, without broad route or storage refactors.

## Future Version

Later versions can add:

- Technical indicators such as moving averages, volume, RSI, MACD, and volatility.
- ETF component weights and top holdings.
- Sector allocation.
- External GitHub tool adapters for indicators, ETF holdings, reports, or specialized providers.
- AI summaries for selected-instrument review, dividend notes, transaction history explanation, and anomaly detection.
- Configurable plugin panels.
- Saved per-instrument notes and research checklists.

## Open Questions

- Should Page 2 include watchlist-only tickers in the same selector as holdings, or use tabs/filters?
- Should search results include all central instruments by default, or only instruments with local OHLCV/quote data?
- Should default selection prioritize largest market value, latest changed position, or first holding?
- Which time ranges should the K-line MVP support first?
- Should actual dividend records be shown as a table, timeline, or summary plus drill-down?
- Which ETF holdings provider should be the first optional adapter?
- Should Page 2 support explicit user-triggered refresh actions, or stay read-only for the first pass?
- Should plugin/assistant sections be hidden until configured, or shown as empty placeholders?
