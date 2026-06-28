# Desktop Product Plan

This document starts the Desktop Product Track planning layer. It is documentation only. It does not change runtime behavior, UI, data paths, provider behavior, accounting logic, import staging, desktop shell behavior, or packaging.

## Product Positioning

The desktop product should become a local-first desktop stock journal and ETF research workbench.

It is:

- A local app for personal account records, holdings review, market-data context, ETF holdings research, imports, and reviewed workflows.
- A user-owned data workbench that keeps real profile data local by default.
- A desktop product that reuses proven contracts from the web prototype while rebuilding the app shell and user flow.

It is not:

- A broker trading app.
- A cloud finance website.
- A third-party data vendor.
- Investment, tax, legal, or trading advice.

## Track Relationship

The Web Prototype Track remains the feature proving ground. It can continue to validate accounting behavior, import staging, market data status, ETF holdings snapshots, provider preview/confirm flows, corporate action planning, and demo runtime safety.

The Desktop Product Track is the final software direction. It should reuse proven concepts, contracts, core logic, and local data safety rules, but it should not directly copy the current web/mobile UI.

Promotion rule:

- Prove behavior in the web prototype.
- Stabilize it as a documented contract.
- Add tests around the contract.
- Rebuild the workflow in the desktop product with a desktop-first shell, navigation, and layout.

## Carries Over From The Web Prototype

The desktop product should carry over these durable concepts and contracts:

- Accounting contracts, including broker-style TWD trade consideration truncation.
- Account journal and holdings rebuild rules.
- Market data contracts and local market database concepts.
- ETF holdings snapshot, provider, preview, and confirmation contracts.
- Import staging philosophy: imports produce reviewed candidate data before final writes.
- Corporate action notice and settlement model.
- Local-first privacy and safety rules.
- Demo and real data separation.
- Read-first provider and plugin boundaries.

## Rebuilt For Desktop

The desktop product should rebuild these surfaces instead of copying the current web/mobile UI:

- App frame.
- Navigation.
- Overview dashboard.
- Stock and ETF detail presentation.
- Import Center.
- Provider and source management.
- Backup and recovery screens.
- Settings and logs.

The current Flask pages remain useful for validation, but they are not the desktop product UI specification.

## Navigation Model

Proposed first desktop navigation:

- Overview.
- Accounts.
- Stocks / ETFs.
- Import Center.
- Data Sources.
- Corporate Actions.
- Backup & Restore.
- Settings / Logs.

The navigation should make data safety visible: current mode, data root, demo/real status, backup state, and pending staged changes should be easy to inspect.

## Desktop Data Root Direction

The future desktop product should use an explicit app data root. Planning baseline:

```text
app_data/
  profiles/
  market_data/
  imports/
  provider_cache/
  backups/
  logs/
  config/
  demo/
```

Expected meaning:

- `profiles/`: durable account journals, notes, and profile documents.
- `market_data/`: local market and ETF research databases.
- `imports/`: uploads, staging batches, validation reports, accepted/rejected import history.
- `provider_cache/`: ignored local provider cache and diagnostics only.
- `backups/`: versioned backups and migration manifests.
- `logs/`: runtime, provider, import, migration, and diagnostic logs.
- `config/`: local product settings and provider configuration.
- `demo/`: generated or bundled demo runtime data, separate from real data.

Desktop code should not assume repository-relative `data/` for the final product.

## Safety Rules

- Real data cannot be migrated without backup and dry-run.
- Demo and real roots stay separate.
- Demo reset must never delete real data.
- Provider fetch is manual-trigger unless a future task explicitly changes it.
- Provider preview must not write until explicit confirmation.
- AI, import, plugin, and corporate action flows require staging/review before final ledger writes.
- Corporate action notices are alerts; broker/account settlements are the accounting source of truth.
- Private provider config, credentials, raw responses, account records, uploads, logs, and backups remain local and ignored.
- No broker trading API or order placement.

## Progress Categories

- Core contracts.
- Desktop shell.
- New desktop UI.
- Data root / backup.
- Real profile support.
- Provider management.
- Packaging / exe.

## Desktop v0 Definition

Desktop v0 should:

- Open as a desktop window.
- Use a clear app data root.
- Show runtime and data-root status.
- Browse demo data safely.
- Keep demo and real roots separate.
- Leave real profile support blocked until backup, dry-run migration, and data-root rules are ready.

## Non-Goals For This Stage

- No packaging.
- No installer.
- No auto updater.
- No cloud sync.
- No broker trading API.
- No rewriting all core logic yet.
- No real profile migration.
- No final desktop UI clone of the current web/mobile prototype.
