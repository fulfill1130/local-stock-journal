# Desktop Backup And Migration Plan

This document defines the safety contract for future desktop backup and migration work. It is documentation only. It does not implement migration code, create backups, copy data, change schemas, or migrate real profiles.

## Purpose

Future desktop migration must be explicit, reviewable, and reversible.

Migration means moving or copying selected existing web prototype/private runtime data into the future desktop `app_data/` root. This document is a safety contract, not an implementation.

Migration must never run automatically on startup. Migration must never be silent.

## Non-Goals

- No migration code in this task.
- No backup archive creation in this task.
- No data copying in this task.
- No schema changes in this task.
- No real profile migration in this task.
- No provider fetches in this task.
- No cloud sync.

## Source And Target Concepts

Possible source:

- Existing web prototype private data paths such as `data/`.

Future target:

- `app_data/`.
- `app_data/profiles/` for real account/profile data.
- `app_data/market_data/` for market/research databases.
- `app_data/imports/` for import staging/archive data.
- `app_data/provider_cache/` for temporary provider cache.
- `app_data/backups/` for local backup archives.
- `app_data/logs/` for desktop logs.
- `app_data/config/` for local desktop configuration.
- `app_data/demo/` for future desktop demo data.

`sample_data/` remains public synthetic data and is not a migration source for private user data.

## Migration Principles

- Explicit user action required.
- Explicit source path required.
- Explicit target `app_data/` path required.
- Dry-run required before any write.
- Backup required before any write.
- Confirmation required after dry-run and backup.
- No overwrite without explicit confirmation.
- No deletion of old source data during migration.
- No automatic cleanup of source data.
- Rollback notes must be produced.
- Migration must be logged locally.
- Migration results must be understandable to non-developer users.

## Required Migration Workflow

1. Select source path.
2. Select or confirm target `app_data/` path.
3. Scan source safely.
4. Produce dry-run report.
5. Create backup.
6. Ask for user confirmation.
7. Copy or transform data.
8. Verify migrated data.
9. Produce migration summary.
10. Keep old source data untouched.

## Dry-Run Report Requirements

The dry-run report should include:

- Source path.
- Target path.
- Detected data categories.
- Detected profiles, if any.
- Candidate database files.
- Candidate market data files.
- Candidate import staging files.
- Candidate provider config files.
- Candidate provider cache files.
- Files that will be copied.
- Files that will be transformed.
- Files that will be skipped.
- Target files that already exist.
- Overwrite risks.
- Estimated file count and size.
- Warnings.
- Blockers.

The dry-run report must not print private trade details, tokens, cookies, raw provider responses, or full sensitive file contents.

## Backup Requirements

- Backup must be created before any migration write.
- Backup should include enough data to restore the pre-migration state.
- Backup should include a manifest.
- Backup filename should include timestamp and scope.
- Backup should stay local.
- Backup must not be committed to Git.
- Backup should be stored under `app_data/backups/` or another user-confirmed local path.
- Backup creation failure must block migration.

## Verification Requirements

After migration, future implementation should verify:

- Expected files exist.
- SQLite files can be opened.
- Required tables exist.
- Basic row counts can be read.
- Profile directories are present.
- Market data databases are present if migrated.
- No source files were deleted.
- Migration summary can be written.

## Rollback Requirements

- Migration should generate rollback notes.
- Rollback should explain what was copied or created.
- If future code supports automated restore, it must restore from backup only after confirmation.
- Failed migration must leave source data untouched.
- Partial target writes must be reported clearly.

## Data Category Policy

- Confirmed account journal / ledger data: highest safety, backup required, never inferred.
- Derived holdings/cost basis: can be rebuilt from ledger when possible.
- Market data snapshots: can be copied, but are not private ledger.
- ETF holdings snapshots: can be copied as research data.
- Provider cache: not source of truth; should usually not migrate unless needed.
- Import staging: migrate carefully; unfinished imports should remain clearly marked.
- Local provider config: may contain private source settings; must be handled carefully and never committed.
- Logs: usually not migrated unless user explicitly asks.
- Demo data: must stay separate from real profiles.

## Concurrency And Locking

- Migration should not run while the web prototype or desktop runtime is writing the same files.
- Future implementation should detect active runtime or lock files if possible.
- Avoid concurrent SQLite writers.
- Migration should operate with the app in a controlled state.

## User-Facing Desktop Requirements

Future desktop UI should show:

- Current data root.
- Source path.
- Target path.
- Backup path.
- Dry-run status.
- Migration status.
- Warnings/blockers.
- Clear confirmation step.
- Final summary.

## Git And Privacy Rules

- `app_data/` is ignored.
- Backups are ignored.
- Logs are ignored unless sanitized test logs are explicitly created.
- Provider cache is ignored.
- Local config is ignored.
- No user profile data in repo.
- No private reports committed.
- Test fixtures must be synthetic.

## Future Implementation Tasks

These are future work and are not implemented now:

- `DESKTOP-BACKUP-MANIFEST-1`
- `DESKTOP-MIGRATION-DRY-RUN-1`
- `DESKTOP-BACKUP-CREATE-1`
- `DESKTOP-MIGRATION-EXECUTE-1`
- `DESKTOP-MIGRATION-VERIFY-1`
- `DESKTOP-RESTORE-FROM-BACKUP-1`
- `DESKTOP-MIGRATION-UI-1`
