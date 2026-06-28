# Legacy Web Prototype

## Purpose

The current root runtime is the legacy web stock machine prototype.

It remains runnable as a demo and reference implementation. It proved workflows such as account journal records, ETF holdings display, provider preview/confirm, CSV import, import staging, market data status, and corporate-action planning.

It is not the final desktop product architecture.

## Current Root Runtime Meaning

These root-level folders currently support the existing web prototype and should not be physically moved in this task:

- `src/`
- `scripts/`
- `tests/`
- `sample_data/`
- `config/`

The current runtime layout is path-sensitive and should be treated as the legacy web prototype/reference until a dedicated migration task changes it.

## Desktop Product Rule

Do not directly migrate the web UI into `desktop_stock_machine/`.

Do not treat Flask templates, Flask static assets, or the current mobile/web layout as the final desktop UI. The desktop product will rebuild shell, navigation, layout, and UI from scratch.

Reuse concepts, contracts, and safety rules. Do not inherit the web UI structure by default.

## Source Movement Rule

`src/` is currently path-sensitive.

Do not move `src/` without a dedicated compatibility plan. Read [Path Dependency Audit](../docs/PATH_DEPENDENCY_AUDIT.md) before any future path migration.

## Reference Value

The legacy web prototype can be used to inspect working behavior and validated workflows.

New desktop work should copy only deliberately selected concepts or logic after review. It should not copy the web app frame, navigation, page layout, or Flask static/template assumptions by default.

## Safety

- Real data stays ignored and private.
- `demo_runtime/` stays separate from real runtime data.
- `market_database/` is not personal account storage.
- Desktop real profile support requires future data-root, backup, dry-run, confirmation, and verification rules.
