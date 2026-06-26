# Desktop Shell Interface

This document defines the planning baseline for a future desktop shell. It is documentation only. It does not add `pywebview`, Tauri, Electron, packaging, file dialogs, plugin execution, or normal private desktop mode.

## Purpose

The Desktop Shell Interface is a framework-neutral contract between the app core and desktop UI/container technologies.

The goal is to let the project prototype a desktop shell with `pywebview` first, and later move to Tauri with a Python sidecar if that becomes the better product direction, without rewriting account, market data, import, or plugin logic.

The shell should be a container around the local-first app core, not a second business-logic implementation.

## Current Layering

Planned layers:

- Desktop Shell Interface: lifecycle, window, user messages, file selection, and shell/container permissions.
- Desktop Server Harness: the demo-only embedded server that starts Flask from a validated `demo_runtime/`.
- Flask Core: `create_app`, routes, demo mode, profile pages, local APIs, and safety blocks.
- Account Journal layer: transactions, FIFO lots, holdings, dividends, notes, and ledger safety rules.
- Market Data layer: local quote cache, OHLCV SQLite files, source labels, and refresh policies.
- Import layer: future file selection, staging batches, validation reports, and reviewed ledger writes.
- Plugin layer: future read-first snapshots, isolated execution, and research/proposal outputs.
- Desktop data root: future `app_data/` layout, with real data separated from demo data.

The current implemented desktop-adjacent piece is the demo-only server harness. It is not a desktop window or packaged app.

## v0 Demo Shell Capabilities

The first shell implementation should stay demo-only.

Required capabilities:

- Start the demo desktop server from a validated `demo_runtime/`.
- Stop the demo desktop server cleanly.
- Expose `base_url` and `url` for the local app.
- Open the main desktop window at the demo URL.
- Handle window close by shutting down the embedded server.
- Show startup, shutdown, and error messages in user-readable language.
- Bind only to local loopback through the server harness.
- Refuse to start when `demo_runtime/.demo_runtime` is missing.

Non-runtime guidance:

- The shell should not read or migrate `data/`.
- The shell should not enable normal `son` or `mom` profiles.
- The shell should not enable refresh, import, or write actions in demo mode.

## v1 Import Capabilities

Import-related shell capabilities should only support staging, not final ledger writes.

Planned capabilities:

- Select PDF, image, or text files.
- Select a folder.
- Copy or register selected files into `app_data/imports/staging/<batch_id>/`.
- Reveal the staging folder in the system file explorer.
- Preserve source metadata for review.
- Support optional redacted or cropped source files.
- Pass validated staging batches to the app core for user review.
- Never write directly to the final account ledger.

The shell may help with file selection and local filesystem convenience, but validation and ledger acceptance remain app-core workflows.

## Future Plugin Capabilities

Plugin-related shell capabilities should stay read-first and permission-limited.

Planned capabilities:

- List plugin manifests.
- Export read-only JSON snapshots for selected scopes.
- Run plugins as isolated subprocesses.
- Collect plugin outputs as proposals or research notes.
- Store outputs under plugin output directories.
- Show plugin warnings and requested permissions before execution.
- Never give plugins direct `journal.json` or SQLite file paths.
- Never let plugin output become a confirmed ledger write without staging and human review.

Plugin execution is not part of the current implementation.

## Implementation Options

### pywebview first prototype

`pywebview` is the preferred first prototype path because it keeps the shell Python-native, can wrap a localhost URL, and avoids introducing a second large packaging ecosystem while the contracts are still moving.

Best use:

- Validate lifecycle: start server, open window, stop server.
- Validate demo-only desktop entry.
- Add simple desktop file dialog experiments later.

Risks:

- Packaging behavior needs separate testing.
- Native-webview differences may affect UI polish.
- Long-term installer and update experience may be limited.

### Tauri plus Python sidecar long term

Tauri with a Python sidecar remains a possible long-term product direction. It may offer a stronger desktop app shell, installer story, and native integration once the data contracts, import staging, and plugin boundaries are stable.

Best use later:

- Product-grade desktop shell.
- Stronger native commands and permission boundaries.
- Clear separation between UI shell and Python app core.

Risks:

- More cross-language complexity.
- Sidecar packaging and update rules must be designed carefully.
- Data-root and process-lifecycle contracts must be stable before adoption.

### Electron not first

Electron is not preferred for the first implementation step because it adds Node/package complexity, a larger runtime footprint, and another app stack before the desktop contracts are proven.

Electron may be reconsidered only if a later requirement clearly depends on its ecosystem.

## Explicit Non-goals

- No mobile support yet.
- No normal `son` or `mom` desktop mode yet.
- No real data migration yet.
- No plugin execution yet.
- No file dialog implementation yet.
- No broker trading API.
- No automatic order placement.
- No direct AI, import, or plugin writes to the final ledger.
- No packaged `.exe` yet.
- No desktop replacement for the Flask core business logic.

## Safety Rules

- Demo shell starts from synthetic demo data first.
- Real user data and demo data use separate roots.
- Demo reset logic must never delete real user data.
- The shell must not grant trading permissions.
- Import results must enter staging before ledger writes.
- Plugin outputs must remain research notes or staging proposals.
- File-system access should be explicit and scoped to the user action.
- Local server binding should stay on loopback unless a separate reviewed feature changes that.

## Relationship To Existing Documents

- [Development Tracks](DEVELOPMENT_TRACKS.md) defines the web prototype and desktop product tracks.
- [Desktop Data Architecture](DESKTOP_DATA_ARCHITECTURE.md) defines future data roots and migration safety rules.
- [Import Staging Specification](IMPORT_STAGING_SPEC.md) defines reviewed import batches.
- [Plugin System Draft](PLUGIN_SYSTEM_DRAFT.md) defines read-first plugin boundaries.
