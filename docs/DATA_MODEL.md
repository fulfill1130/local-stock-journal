# Data Model

The project separates profile/account data from central market data.

## Account Data

Account data belongs to one local user profile.

Typical fields:

- Transactions.
- Dividend income records.
- Watchlist items.
- Account-specific notes.
- Import staging rows.

Transactions should be the source of truth for holdings.

Suggested transaction fields:

```text
trade_date
ticker
name
action
shares
price
fee
tax
order_no
source
note
review_status
created_at
updated_at
```

## FIFO Cost Model

The project assumes first-in-first-out cost accounting.

When selling:

- Oldest buy lots are consumed first.
- Partial lots are allowed.
- Sale fee and tax are included in realized profit calculation.

Duplicate detection should not rely only on date, ticker, shares, and price because same-day repeated trades can be valid. Broker order number, when available, is a better duplicate key.

## Dividend Income

Dividend calendar data and actual received dividend income are separate.

Dividend calendar data:

- Comes from market or ETF dividend sources.
- Helps estimate future dividend dates and payout rhythm.

Actual dividend income:

- Is entered manually.
- Uses the amount actually received by the broker account.
- Is stored by profile.
- Includes ticker, received date, and amount.

Portfolio earned amount:

```text
total_earned = realized_trading_profit + manual_dividend_income
```

## Instrument Master

The instrument master should use a stable internal ID.

Recommended table:

```sql
CREATE TABLE IF NOT EXISTS instruments (
  instrument_id TEXT PRIMARY KEY,
  ticker TEXT NOT NULL,
  market TEXT NOT NULL,
  type TEXT NOT NULL,
  name TEXT,
  yahoo_symbol TEXT,
  listing_date TEXT,
  delisting_date TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  source TEXT,
  created_at TEXT,
  updated_at TEXT,
  UNIQUE(ticker, market)
);
```

Rules:

- Do not use Chinese or display name as a primary key.
- Do not create a new instrument only because the name changed.
- Name changes should be tracked in history.
- Delisted instruments should remain in the master so old transactions still resolve.

## Name History

```sql
CREATE TABLE IF NOT EXISTS instrument_name_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  instrument_id TEXT NOT NULL,
  old_name TEXT,
  new_name TEXT,
  effective_date TEXT,
  detected_at TEXT NOT NULL,
  source TEXT,
  note TEXT
);
```

Purpose:

- Preserve rename events.
- Keep historical OHLCV tied to the same instrument.
- Avoid losing data when a display name changes.

## Aliases

```sql
CREATE TABLE IF NOT EXISTS instrument_aliases (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  instrument_id TEXT NOT NULL,
  alias_type TEXT NOT NULL,
  alias_value TEXT NOT NULL,
  source TEXT,
  is_active INTEGER DEFAULT 1,
  created_at TEXT,
  note TEXT
);
```

Alias examples:

- `old_ticker`
- `old_name`
- `yahoo_symbol`
- `twse_code`
- `tpex_code`
- `manual_alias`

## OHLCV Daily

Official daily OHLCV should use `instrument_id + date` as the primary key.

```sql
CREATE TABLE IF NOT EXISTS ohlcv_daily (
  instrument_id TEXT NOT NULL,
  date TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  volume INTEGER,
  value REAL,
  source TEXT NOT NULL,
  adjusted INTEGER DEFAULT 0,
  created_at TEXT,
  updated_at TEXT,
  PRIMARY KEY (instrument_id, date)
);
```

Rules:

- Official daily data should not be overwritten by Yahoo auxiliary data.
- If auxiliary data is needed, store it separately or mark its source clearly.

## Quotes

```sql
CREATE TABLE IF NOT EXISTS quotes (
  instrument_id TEXT PRIMARY KEY,
  price REAL,
  change REAL,
  change_pct REAL,
  quote_date TEXT,
  quote_time TEXT,
  source TEXT,
  updated_at TEXT
);
```

The dashboard should read `quotes` for current or latest known prices.

## Intraday Data

```sql
CREATE TABLE IF NOT EXISTS ohlcv_intraday_15m (
  instrument_id TEXT NOT NULL,
  datetime TEXT NOT NULL,
  open REAL,
  high REAL,
  low REAL,
  close REAL,
  volume INTEGER,
  source TEXT NOT NULL,
  created_at TEXT,
  PRIMARY KEY (instrument_id, datetime)
);
```

```sql
CREATE TABLE IF NOT EXISTS quote_snapshots_15m (
  instrument_id TEXT NOT NULL,
  snapshot_time TEXT NOT NULL,
  price REAL,
  change REAL,
  change_pct REAL,
  source TEXT,
  created_at TEXT,
  PRIMARY KEY (instrument_id, snapshot_time)
);
```

## After-Close Quotes

```sql
CREATE TABLE IF NOT EXISTS after_close_quotes (
  instrument_id TEXT NOT NULL,
  quote_date TEXT NOT NULL,
  price REAL,
  change REAL,
  change_pct REAL,
  source TEXT,
  created_at TEXT,
  PRIMARY KEY (instrument_id, quote_date)
);
```

After-close quotes must not overwrite official daily OHLCV close values.

## Health Summary

```sql
CREATE TABLE IF NOT EXISTS instrument_health_summary (
  instrument_id TEXT PRIMARY KEY,
  daily_rows INTEGER DEFAULT 0,
  first_daily_date TEXT,
  last_daily_date TEXT,
  expected_start_date TEXT,
  expected_end_date TEXT,
  history_status TEXT,
  recent_data_ok INTEGER DEFAULT 0,
  missing_month_count INTEGER DEFAULT 0,
  first_missing_month TEXT,
  missing_months_json TEXT,
  last_checked_at TEXT,
  last_success_at TEXT,
  last_error TEXT,
  retry_count INTEGER DEFAULT 0,
  next_retry_at TEXT,
  manual_review_required INTEGER DEFAULT 0,
  updated_at TEXT
);
```

Supported `history_status` values:

```text
ok
recent_ok_partial_history
new_listing
partial_old_missing
recent_missing
broken
symbol_problem
delisted_candidate
delisted
manual_review
```

## Issues

```sql
CREATE TABLE IF NOT EXISTS market_data_issues (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  instrument_id TEXT,
  issue_type TEXT NOT NULL,
  severity TEXT NOT NULL,
  message TEXT,
  first_seen_at TEXT,
  last_seen_at TEXT,
  retry_count INTEGER DEFAULT 0,
  resolved_at TEXT,
  resolution_note TEXT
);
```

Issue examples:

- `missing_month`
- `recent_missing`
- `official_no_data`
- `yahoo_failed`
- `symbol_problem`
- `name_changed`
- `delisted_candidate`
- `parse_error`
- `rate_limited`
- `manual_review`

## Corporate Actions

Corporate actions are manual records.

For splits:

- Effective date.
- Multiplier.

Effect:

- Buy lots before the effective date have their shares multiplied.
- Per-share cost is divided.
- Total cost remains unchanged.

## Recommended Indexes

```sql
CREATE INDEX IF NOT EXISTS idx_instruments_ticker_market
ON instruments(ticker, market);

CREATE INDEX IF NOT EXISTS idx_instruments_status
ON instruments(status);

CREATE INDEX IF NOT EXISTS idx_ohlcv_daily_instrument_date
ON ohlcv_daily(instrument_id, date);

CREATE INDEX IF NOT EXISTS idx_quotes_updated
ON quotes(updated_at);

CREATE INDEX IF NOT EXISTS idx_health_status
ON instrument_health_summary(history_status);

CREATE INDEX IF NOT EXISTS idx_health_retry
ON instrument_health_summary(next_retry_at);

CREATE INDEX IF NOT EXISTS idx_issues_instrument
ON market_data_issues(instrument_id);

CREATE INDEX IF NOT EXISTS idx_issues_unresolved
ON market_data_issues(resolved_at);
```

