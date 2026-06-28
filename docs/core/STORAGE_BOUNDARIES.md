# Storage Boundaries

This document defines shared storage boundaries for Core, the Web Prototype Track, and the Desktop Product Track. It is documentation only and does not move runtime code.

## Boundary Definition

Core contracts define how data is read and written.

The Web Prototype and Desktop Product are clients of core/storage concepts. UI layers must not own accounting rules, market data persistence rules, or reviewed-write policy. UI layers must not bypass staging/review flows.

Shared core logic should not depend on Flask, templates, JavaScript, pywebview, desktop shell lifecycle, web routes, or desktop navigation.

## Source Of Truth Categories

Account journal / confirmed ledger data:

- User-confirmed transactions.
- User-confirmed cash movements.
- User-confirmed dividend records.
- Future user-confirmed corporate action settlements.

Derived holdings and cost basis:

- Rebuildable holdings.
- FIFO lots.
- Realized and unrealized profit/loss.
- Derived account summaries.

Market data snapshots:

- OHLCV history.
- Quotes.
- Market-data health summaries.
- Exchange/provider market metadata.

ETF holdings snapshots:

- Confirmed ETF component snapshots.
- Snapshot metadata such as source, as-of date, status, and notes.
- Components and weights used for research display.

Provider cache:

- Temporary provider fetch diagnostics or cache.
- Not a source of truth.
- Not committed.

Import staging data:

- Candidate rows.
- Validation reports.
- Source metadata.
- Review state before final writes.

Corporate action notices:

- Market/provider/company announcements.
- Alerts and theoretical calculations only.
- Not accounting source of truth.

Corporate action settlements:

- User/broker-confirmed actual settlement results.
- May affect accounting only after explicit confirmation.

Logs/config/backups:

- Runtime logs and diagnostics.
- Local config.
- Backup archives and manifests.
- Local/private unless explicitly sanitized as examples.

## Track Separation

The web prototype currently uses its existing runtime data paths.

The desktop product will use `app_data/`.

Core/storage contracts should work for both, but the two tracks must not silently share writable databases. Desktop implementation must define root selection, locking, backup, and migration behavior before real writes.

## Safe Write Policy

Import, AI, plugin, provider, and corporate action outputs cannot directly write confirmed ledger data.

Preview, staging, and explicit confirmation are required.

ETF provider output can only become an ETF holdings snapshot after explicit confirmation.

Corporate action notices do not alter accounting. Corporate action settlements require a confirmed user/broker result before any accounting effect.

## Future Implementation Guidance

Future code may be organized into:

```text
src/core/
src/web_app/
src/desktop_app/
src/shared/
```

Do not move runtime code in this task.

Future refactors should be small and test-covered. They should introduce storage boundaries gradually, keep existing behavior stable, and avoid broad rewrites.
