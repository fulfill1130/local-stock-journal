# Desktop Product Log

This log records concise Desktop Product Track decisions and handoff notes. It is documentation only.

## 2026-06-28 - Desktop Product Track Begins

Desktop Product Track planning begins.

Decisions:

- The web prototype remains the feature lab and validation surface.
- The desktop UI will be rebuilt from scratch instead of copying the current web/mobile interface.
- Proven concepts, contracts, core logic, data paths, and safety rules carry over.
- The desktop product should become a local-first stock journal and ETF research workbench, not a broker trading app or cloud finance website.

Current next focus:

- Desktop product shell.
- App data root.
- Navigation model.
- Log/progress system.
- Backup and recovery before real data migration.

Boundaries:

- No runtime behavior changed.
- No real data migration.
- No packaging or installer work.
- No provider, import staging, accounting, market data, or desktop shell behavior changes.

## 2026-06-28 - Documentation Boundaries Started

Documentation boundary organization started before desktop implementation.

Changes:

- Added Core, Web Prototype, Desktop Product, and Providers documentation sections.
- Moved the desktop product plan and product log under `docs/desktop_product/`.
- Kept runtime source-code movement deferred.
- Kept existing web prototype code, provider behavior, import staging, accounting, and desktop shell behavior unchanged.

Next phase:

- Plan the `app_data/` data-root contract.
- Plan backup and recovery before real profile migration.
- Define desktop shell boundaries before implementing the new desktop UI.

## 2026-06-28 - Desktop Data-Root Planning Started

Desktop data-root planning started.

Decisions:

- `app_data/` is reserved as the future desktop product root.
- Current web prototype `data/` remains separate.
- Source-code and runtime path movement remains deferred.
- Real-data migration requires a future dry-run report, backup, user confirmation, clear source/target paths, and rollback notes.

Next recommended phase:

- Design the desktop shell/data-root status surface.
- Design backup and migration manifests before real profile migration.

## 2026-06-28 - Backup And Migration Planning Started

Backup/migration planning started.

Decisions:

- Migration will require dry-run, backup, confirmation, verification, and local logging.
- No real data migration is implemented yet.
- Source data must remain untouched during migration.
- Backup creation failure must block migration.

Next recommended phase:

- Desktop shell data-root status surface.
- Backup dry-run design.
