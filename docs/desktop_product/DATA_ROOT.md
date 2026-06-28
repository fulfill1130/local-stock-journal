# Desktop Data Root

This document defines the future Desktop Product data-root plan. It is documentation only. It does not create `app_data/`, wire runtime paths, migrate profile data, or change desktop shell behavior.

## Purpose

The desktop product must use an explicit app data root.

Desktop app data must not be mixed with the current web prototype `data/` folder. The app data root should be visible and understandable to the user so they can tell where real profiles, market data, imports, backups, logs, local config, and demo data live.

The desktop product is local-first and private by default. It should not use cloud sync by default.

## Proposed Root

```text
app_data/
```

`app_data/` is reserved for future desktop local runtime data. It must not be committed to Git. It must not be used until a future implementation task explicitly creates and wires it.

## Proposed Layout

```text
app_data/
  profiles/
    son/
    mom/
  market_data/
  imports/
    staging/
    archived/
  provider_cache/
  backups/
  logs/
  config/
  demo/
```

## Folder Responsibilities

- `profiles/`: real user profile and account data.
- `market_data/`: shared local market and research databases, including ETF holdings and market snapshots.
- `imports/staging/`: preview and import staging data before confirmed writes.
- `imports/archived/`: archived import files or normalized import records after review.
- `provider_cache/`: temporary provider cache and diagnostics; never a source of truth.
- `backups/`: backup archives created before migration or risky writes.
- `logs/`: desktop runtime logs and diagnostic logs.
- `config/`: local desktop configuration; no secrets committed.
- `demo/`: future desktop demo data root, separate from real profiles.

## Relationship To Existing Folders

- `data/`: current web prototype/private runtime data. It is not the final desktop data root.
- `demo_runtime/`: current generated demo runtime. It is not the final desktop data root.
- `sample_data/`: public synthetic fixtures and demo seeds. It can be committed.
- `config/providers.local.json`: ignored local provider configuration.
- `data/provider_cache/`: existing ignored provider cache path.

The desktop product may later read from or migrate selected data from current web prototype paths, but only through an explicit future migration task.

## Desktop v0 Rule

Desktop v0 may browse demo data.

Desktop v0 must show data-root and runtime status clearly.

Real profile support must wait until backup and dry-run rules are implemented. There must be no silent migration from `data/` to `app_data/`.

## Migration Rule

Migration from old web prototype `data/` to desktop `app_data/` must be a future explicit task.

For the required safety workflow, see [Desktop Backup And Migration Plan](BACKUP_MIGRATION.md).

Migration must require:

- Dry-run report.
- Backup creation.
- User confirmation.
- Clear source path and target path.
- Rollback notes.

Migration must not run automatically on app startup.

## Write Access Rule

All writes must go through core/storage APIs or explicit storage helpers.

The web prototype and desktop product must not directly write the same database independently. Avoid concurrent writers to the same SQLite files. Future implementation must define lock and lifecycle rules before real writes.

## Provider Rule

Provider fetch remains manual-trigger unless a future task explicitly changes it.

Provider cache is not a source of truth. Confirmed ETF holdings snapshots live in `market_data/`. Raw provider responses must not be committed.

## Backup Rule

Create backups before:

- Migration.
- Destructive schema changes.
- Bulk import confirmation.

Backups stay local. Backup contents must not be committed.

## Git And Privacy Rule

- `app_data/` is ignored.
- Backups are ignored.
- Logs are ignored unless sanitized test logs are explicitly created.
- Provider cache is ignored.
- Local config is ignored.
- User profile data must not be committed.
