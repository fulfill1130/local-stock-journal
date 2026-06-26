# Desktop Data Architecture

This document freezes the planning baseline for future Desktop Product Track storage. It is documentation only. It does not implement the desktop app, migration, or new runtime paths.

## Current Data Architecture

Current web prototype paths:

- `data/`: private normal-mode runtime root.
- `demo_runtime/`: ignored generated demo runtime root.
- `sample_data/`: committed synthetic source fixtures.
- `data/profiles/<profile>/state.json`: profile state JSON for local profiles such as `son` and `mom`.
- `demo_runtime/profiles/demo/state.json`: generated demo profile state.
- `data/market_data/{etf,twse,tpex}.sqlite`: segmented market SQLite files.
- `demo_runtime/market_data/{etf,twse,tpex}.sqlite`: generated synthetic demo market SQLite files.
- `data/central.sqlite`: legacy market database migration source.
- `data/quotes_cache.json`: local quote cache.
- `demo_runtime/quotes_cache.json`: generated demo quote cache.
- `data/uploads/<profile>/<year>/<month>/`: uploaded private documents.
- `data/refresh_log.json`: refresh log.
- `data/cleanup_market_data.log`: cleanup command log.
- `*.sqlite.bak_<timestamp>`: current ad hoc SQLite migration backups.

Current notes:

- Profile state JSON is the durable account journal today.
- Market SQLite files store market data, health data, operation logs, uploaded document metadata, and Gmail receipt metadata.
- Demo runtime is generated from `sample_data/` and guarded by `.demo_runtime`.
- Import staging and plugin output stores are not implemented yet.

## Data Classifications

Durable accounting data:

- Profile settings.
- Transactions.
- FIFO lots.
- Holdings and derived cost state.
- Cash movements.
- Actual received dividend records.
- Watchlists and account notes.

Durable private documents:

- Uploaded broker PDFs, screenshots, and images.
- Upload metadata.
- Gmail attachment receipts.
- Any future redacted or cropped source files retained for import review.

Rebuildable market/cache data:

- Quote cache.
- OHLCV history that can be rebuilt from configured providers or sample fixtures.
- Intraday snapshots.
- After-close quotes.
- Market-data health summaries.
- Update status rows.
- Operation logs.

Generated demo data:

- Everything under `demo_runtime/`.
- Data generated from `sample_data/`.
- Synthetic profile, market SQLite files, and quote cache.

Import staging data:

- Pasted AI result JSON.
- Validation reports.
- Candidate transactions, dividend movements, and cash movements.
- Optional redacted/cropped source files.
- User review state.

Plugin input/output data:

- Exported JSON snapshots sent to plugins.
- Plugin research notes.
- Plugin staging proposals.
- Plugin warnings and metadata.

Logs:

- Refresh logs.
- Operation logs.
- Import validation logs.
- Migration logs.
- Plugin execution logs.

Backups:

- Profile state snapshots.
- Uploaded document copies or references.
- Market DB snapshots when needed.
- Migration manifests and validation reports.

## Future Desktop Data Root

The future desktop product should use a dedicated app data root:

```text
app_data/
  profiles/
    <profile>/
      journal.json
      notes/
      documents/
  market_data/
    etf.sqlite
    twse.sqlite
    tpex.sqlite
  imports/
    uploads/
    staging/
      <batch_id>/
        batch.json
        source_metadata.json
        validation_report.json
    accepted/
    rejected/
  plugins/
    installed/
    manifests/
  plugin_outputs/
    <profile>/
      research_notes/
      staging_proposals/
  backups/
    <timestamp>/
      manifest.json
      profiles/
      market_data/
      imports/
  logs/
  cache/
    quotes_cache.json
    refresh_log.json
  demo/
    runtime/
```

Rules:

- Real data and demo data must use separate roots.
- Demo reset logic must never delete real user data.
- Demo data is resettable.
- Real accounting data is durable.
- Desktop code should not assume repository-relative `data/`.
- Paths stored inside data files should be relative to the app data root where practical.

## Migration Safety Rules

Migration from current `son` or `mom` profile data must be a separate dry-run command.

Rules:

- Never run migration automatically on app startup.
- Backup before migration.
- Copy first, transform second.
- Never transform source files in place.
- Write a migration report.
- Validate profile JSON shape before migration.
- Rebuild holdings from transactions and compare totals.
- Require a versioned schema marker before real migration.
- Require user review before committing migrated data as the active desktop data root.
- Keep a rollback path that restores the pre-migration backup.

Recommended migration report fields:

- Source root.
- Target root.
- Started and finished timestamps.
- Schema versions.
- Files copied.
- Files skipped.
- Profile validation results.
- Accounting comparison results.
- Warnings.
- Errors.
- Backup path.
- Rollback instructions.

## Import Staging Storage

Future import staging should live under:

```text
app_data/imports/staging/<batch_id>/
  batch.json
  source_metadata.json
  validation_report.json
  redacted_source_optional.*
```

Rules:

- `batch.json` stores normalized candidate rows.
- `source_metadata.json` stores source type, broker label, hash, filename, and user-provided notes.
- `validation_report.json` stores missing fields, suspicious values, duplicate candidates, and reconciliation notes.
- Optional redacted/cropped source files may be retained only when the user chooses to keep them.
- Accepted rows should be copied into the account journal only after explicit confirmation.
- Rejected rows should remain reviewable or be safely discardable.

## Plugin Storage

Future plugin storage should keep plugin execution separate from durable accounting data.

Rules:

- Plugins receive exported JSON snapshots only.
- Plugins do not receive direct `journal.json` or SQLite paths.
- Plugin manifests live under `app_data/plugins/manifests/`.
- Installed plugin files live under `app_data/plugins/installed/`.
- Plugin outputs go to `app_data/plugin_outputs/<profile>/`.
- Plugin outputs are proposals or research notes, not final ledger writes.
- Ledger-related plugin suggestions must become staging proposals first.

Recommended plugin output folders:

```text
app_data/plugin_outputs/<profile>/
  research_notes/
  staging_proposals/
```

## Known Risks

- No multi-writer lock exists yet for profile JSON writes.
- Profile JSON currently contains both confirmed ledger data and derived holdings/lots.
- Market DBs mix rebuildable market data with metadata and log tables.
- Current upload paths may need app-data-root-relative migration.
- Normal mode still has hardcoded `son` and `mom` assumptions.
- No unified backup/restore format exists yet.
- No import staging store exists yet.
- No plugin sandbox or permission manager exists yet.

## Smallest Next Implementation Step

Before implementing desktop runtime paths, add a versioned backup manifest contract and tests for generating a dry-run migration report from synthetic/demo data only.
