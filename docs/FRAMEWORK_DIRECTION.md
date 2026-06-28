# Framework Direction

`Local Stock Journal` is evolving from a local web dashboard into a local-first stock workbench.

The current app started as a practical dashboard for private portfolio records. The intended direction is broader: a modular local workbench for keeping account records, reviewing instruments, staging imports, managing local market data, and connecting read-first analysis tools without giving them control over the user's ledger.

This project is not investment advice, has no trading permissions, and does not connect to broker trading APIs.

## Intended Modules

### Account Journal

The account journal is the durable record system. It should manage transactions, FIFO lots, dividends, notes, documents, and account-specific history. Confirmed journal records should be explicit, reviewable, and protected from silent rewrites.

### Instrument Research

Instrument research should help users inspect one stock or ETF at a time. It should use local market data, K-line/OHLCV history, and overlays such as cost line, buy markers, and dividend markers to explain the user's own position and history.

### Import Assistant

The import assistant should support PDFs, images, OCR, and AI-assisted extraction. Its job is to turn messy broker documents into staged candidate records. Import and AI results must go through staging and human review before anything becomes a confirmed ledger write. See [Import Staging Specification](IMPORT_STAGING_SPEC.md).

### Market Data Manager

The market data manager should help users bootstrap instruments, inspect data health, choose providers, and control refresh settings. Public demos and tests should work from synthetic local data. Live providers should stay optional and user-controlled.

### App Shell

The app shell should provide clearer app-style entry points for demo mode, private local use, account pages, research pages, imports, and settings. UI details may change as the shell evolves; the durable boundary is the local journal and reviewed data flow.

For current documentation boundaries, see [Documentation Index](README.md), [Web Prototype Track](web_prototype/README.md), and [Desktop Product Track](desktop_product/README.md).

### Plugin Layer

The plugin layer is a future extension point for external open-source analysis tools, market data adapters, importers, reports, and assistant rules. Plugins should be read-first and permission-limited by default. Any plugin that proposes ledger changes should produce reviewable staged output instead of writing directly. See [Plugin System Draft](PLUGIN_SYSTEM_DRAFT.md).

## Current Public Draft

The current public draft focuses on:

- Synthetic demo mode.
- Safe `demo_runtime/` separation from private `data/`.
- Core accounting behavior and FIFO cost tracking.
- Local single-instrument K-line visualization.
- Cost line, buy markers, and ex-dividend markers.
- Public safety documentation and release hygiene.

It is an early draft under active development, not a production-ready finance app.

## Safety Boundaries

- No trading permissions.
- No broker trading API integration.
- No financial, investment, tax, or legal advice.
- No silent ledger mutation from imports, AI tools, or plugins.
- Import and AI results must enter staging first.
- Plugins must be permission-limited and read-first unless the user explicitly reviews and accepts a proposed write.
- Private runtime data belongs under ignored local directories, not in Git.

The framework should make the safe path the default: local data, synthetic demos, reviewed imports, clear source labels, and no hidden automation that changes financial records.
