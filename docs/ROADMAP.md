# Roadmap

This roadmap focuses on stability, privacy, and scalability before adding advanced analysis.

## Near Term

### Stabilize Mobile Access

- Improve failure messages for phone connections.
- Detect server offline versus frontend fetch failure.
- Avoid repeated server restarts during debugging.
- Document private-network access setup.

### Move Status Cards

- Move market update status cards out of the main account dashboard.
- Keep them in database operation logs.
- Keep the account dashboard focused on portfolio state.

### Add Account Page Split

- Page 1: portfolio summary and holdings.
- Page 2: stock details.
- Add top-level switching between pages.

### Fix Flat Price Display

- Flat price change should display white `+0.00%`.
- It should not display `N/A`.

### Improve Official Daily Sync

- Detect holidays and non-trading days.
- Request latest valid trading day when appropriate.
- Avoid false failure states on market holidays.

## Medium Term

### Upload Library First

- Store PDFs and screenshots reliably.
- Avoid duplicate uploads.
- Add parse status and retry controls.
- Keep parsing separate from final transaction writing.

### Staging Import Flow

- Parse documents into staging rows.
- Show duplicates and conflicts.
- Let the user confirm before writing final transactions.

### Optional AI Parser

- Add an AI parser only as an optional backend.
- Send files or extracted text for JSON conversion.
- Cache parse results by file hash.
- Avoid repeated paid calls.

### Better Historical Backfill

- Use listing dates.
- Check missing months.
- Process one instrument or one bounded batch per cycle.
- Prioritize recent missing data.
- Skip delisted instruments.

## Long Term

### Full Taiwan Market Database

- Import all listed stocks, OTC stocks, and ETFs.
- Keep database pages paginated.
- Read precomputed summaries.
- Avoid frontend loading all OHLCV data.

### Data Quality Console

- Show unresolved issues.
- Allow manual status changes.
- Allow delisted/manual review marking.
- Show missing month lists.

### Corporate Action Support

- Track stock splits and reverse splits.
- Support cost adjustment rules.
- Preserve historical lots and adjusted display logic.

### Advanced Analysis

- Add technical indicators only after the data layer is stable.
- Future indicators may include KD, RSI, MA, and AI-generated summaries.
- Analysis should read local data and never modify raw records.

## Non-Goals

- No automatic trading.
- No brokerage trading API integration.
- No public hosted portfolio service.
- No financial advice engine.

