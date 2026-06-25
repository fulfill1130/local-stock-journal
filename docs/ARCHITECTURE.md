# Architecture

`stock_daily_helper` is a local-first dashboard composed of five major parts:

1. Account dashboard.
2. Central instrument database.
3. Market data collectors.
4. Data health and issue tracking.
5. Import pipeline for broker documents.

The application is intended to run on a trusted local machine and be accessed from trusted private devices.

## Core Principles

- Account data and market data are separated.
- External APIs are not called when opening normal dashboard pages.
- Background jobs collect market data and write local snapshots.
- Frontend pages read local data and precomputed summaries.
- One bad ticker, API failure, or import error should not break the whole system.
- Errors should be recorded in local logs or issue tables, not only printed to the console.

## Components

### Account Dashboard

The account dashboard reads profile-specific transaction data and local market quotes.

Responsibilities:

- Show portfolio summary.
- Show realized trading profit.
- Show manually entered dividend income.
- Show current holdings.
- Provide buy/sell entry.
- Provide document upload/import entry points.

It should not call external market data APIs directly.

### Account Stock Detail

The stock detail page is intended to hold deeper per-instrument information that would otherwise make the main dashboard too crowded.

Responsibilities:

- Show detailed position data.
- Show batch/lifecycle information.
- Link to historical market data.
- Show dividend summary where available.

### Central Instrument Database

The central database is shared by all account profiles.

Responsibilities:

- Maintain one stable instrument master.
- Store quote and OHLCV data.
- Store instrument health summaries.
- Store market data issues.
- Support filtering, pagination, and detail pages.

The central database should use stable internal IDs, not display names, as primary keys.

### Market Data Collectors

Collectors are responsible only for data collection and storage.

Typical sources:

- TWSE official data.
- TPEx official data.
- Yahoo Finance.
- yfinance.

Collectors should not perform investment logic.

### Data Health Checker

The health checker reads local market data and writes a compact summary.

Responsibilities:

- Determine whether recent data exists.
- Detect old missing months.
- Detect newly listed instruments.
- Detect possible delisting or symbol problems.
- Update the `instrument_health_summary` table.

The database page should read these summaries instead of scanning all OHLCV rows on every page load.

### Issue Tracker

The issue tracker records data problems in structured form.

Examples:

- Missing month.
- Recent missing data.
- Official source returned no data.
- Yahoo failed.
- Symbol problem.
- Possible delisting.
- Parse error.
- Rate limit.
- Manual review required.

Repeated errors should update the existing issue instead of creating infinite duplicates.

### Upload Library

The upload library stores broker PDFs or screenshots for later processing.

The recommended flow is:

1. Upload and store the original file.
2. Extract or parse later.
3. Produce structured staging rows.
4. Ask the user to review.
5. Write confirmed rows to account transactions.

## Scheduling Model

Typical background jobs:

- Intraday quote snapshots during market hours.
- After-close quote capture.
- Official daily OHLCV sync.
- Slow historical backfill.
- Email attachment check/download.
- Cleanup jobs.

Jobs should be independently recoverable. A failure in one job should not stop unrelated jobs.

## Deployment Model

Recommended:

- Run locally on a trusted machine.
- Access from the same machine through `127.0.0.1`.
- Optionally access from trusted private devices through a private VPN or private network.

Not recommended:

- Exposing the server directly to the public internet.
- Hosting account data on an untrusted server.
- Sharing OAuth credentials, broker PDFs, or local databases.

