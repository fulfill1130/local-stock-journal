# Development Tracks

`Local Stock Journal` will evolve through two related tracks: a web prototype track for proving workflows quickly, and a desktop product track for a future app-style local product.

This document is planning only. It does not change runtime behavior.

## Web Prototype Track

The current Flask/web app continues as the feature proving ground.

Purpose:

- Build useful functionality before polishing product UI.
- Test accounting, import staging, market data, K-line, and plugin concepts quickly.
- Keep the app local-first and safe while workflows are still experimental.
- Validate features in the web prototype before promoting them to the desktop product.

Non-goals for now:

- Polished consumer UI.
- Full mobile optimization.
- Native desktop packaging.
- Broad plugin execution or external tool orchestration.

Mobile support is not a priority in this track right now. The priority is proving durable workflows and data contracts.

## Desktop Product Track

The future goal is a Windows desktop-style app or `.exe`-style local product.

The Desktop Product Track planning layer has started. See [Desktop Product Plan](DESKTOP_PRODUCT_PLAN.md) and [Desktop Product Log](DESKTOP_PRODUCT_LOG.md).

The desktop framework should be designed around:

- Stable local data directories.
- Clear module boundaries.
- Explicit backup and migration flows.
- Plugin safety and permission boundaries.
- Demo/synthetic data as the first-run experience.

For the planning baseline, see [Desktop Data Architecture](DESKTOP_DATA_ARCHITECTURE.md).

The first implementation step is a demo-only embedded desktop server harness that can wrap the current Flask app for a future shell. It is not a desktop window, installer, or packaged app yet.

For the shell/container boundary, see [Desktop Shell Interface](DESKTOP_SHELL_INTERFACE.md).

The desktop app should start with demo data, not private account data. Real local profiles such as `son` or `mom` should only be migrated after:

- Local backups.
- Schema validation.
- Dry-run migration checks.
- User review of what will be copied or transformed.
- A clear rollback path.

## Shared Contracts

Stable workflows should become shared contracts before they are promoted from web prototype to desktop product.

Shared contracts include:

- Import staging JSON.
- Plugin input/output JSON.
- Corporate action notice and settlement schema. See [Corporate Actions Specification](CORPORATE_ACTIONS_SPEC.md).
- Market data schema.
- Account journal schema.
- Backup and migration format.

These contracts should be documented, tested, and versioned where practical.

## Promotion Rules

- Experimental features start in the web prototype.
- Useful workflows are tested against synthetic demo data first.
- Stable workflows become documented shared contracts.
- Shared contracts get validation tests before desktop adoption.
- Only then should the workflow be implemented in the desktop product.

The desktop product should not inherit unstable UI shortcuts or implicit web-only assumptions.

## Safety Rules

- No trading permissions.
- No broker trading API integration.
- No automatic order placement.
- AI, import, and plugin outputs must not directly write final ledger records.
- Import and AI outputs must enter staging and human review first.
- Plugins are read-first and permission-limited by default.
- Private runtime data must stay outside Git.
- Real data migration requires backups, validation, and dry-run checks.

The shared direction is conservative by design: prove workflows in the web prototype, promote only stable contracts, and keep the future desktop product local-first and ledger-safe.
