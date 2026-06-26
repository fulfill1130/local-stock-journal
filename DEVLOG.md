# Developer Log

This log records public-facing development notes for `stock_daily_helper`.

The project exists because personal investing records deserve a local, reviewable journal instead of a pile of broker PDFs, screenshots, spreadsheets, and disconnected notes. The goal is a local-first stock journal and personal investment research dashboard: records first, analysis second.

This project has no trading permissions, does not connect to broker trading APIs, and is not investment advice. It is an early draft under active development and is not production-ready.

## 2026-06-27 - Platform Foundations And Workbench Direction

This development session moved the project further from a single local dashboard toward a local-first stock workbench/platform. The web prototype remains the proving ground, while more shared layers are becoming reusable by a future desktop product.

Completed highlights:

- Added a demo-only embedded desktop server harness.
- Added a minimal `DesktopShell` protocol/interface.
- Added an optional `pywebview` desktop shell implementation.
- Added the `desktop-demo` CLI command for the optional demo desktop shell.
- Matched broker-style TWD trade consideration truncation for buy/sell accounting.
- Added backend Import Staging core validation and file-based staging batches.
- Added Import Staging API routes for creating and reading batches.
- Added a minimal Import Staging review UI.
- Added runtime/data-root visibility and duplicate port safety for local development.
- Added a read-only market data status API.
- Added a dashboard market data status card showing local data freshness.

Important boundaries:

- Desktop work is still demo-only and not packaged as an `.exe`.
- No `son` or `mom` real data migration was performed.
- Import staging does not write final ledger records yet.
- Gmail/OAuth, crop UI, source adapters, and plugin execution are not implemented yet.
- Market data status is read-only and does not refresh data.

Why this matters:

- The app is starting to separate account journal, market data, import staging, runtime safety, and desktop-shell concerns.
- The same safer backend contracts can support both the Web Prototype Track and the future Desktop Product Track.
- New visibility around runtime roots and market-data freshness should make local testing less ambiguous.

Next direction:

- Add an explicit import staging confirmation flow before final ledger writes.
- Add AI/Gmail/PDF source adapters later, after staging and review boundaries are stable.
- Design safer backup, validation, and rebuild workflows before any real profile migration.
- Explore desktop packaging later, after demo-only desktop behavior and data-root contracts are stable.

## 2026-06-26 - Initial Public Draft

The first public draft focuses on safety, deterministic demo usage, core accounting behavior, and local K-line visualization.

Completed highlights:

- Synthetic demo mode with fake demo tickers and fake account data.
- Safe `demo_runtime/` separation from private `data/`.
- FIFO cost tracking and accounting regression coverage.
- Manual dividend records kept separate from market dividend calendar data.
- Single-instrument detail page with local K-line/OHLCV charts.
- Cost line, buy markers, and ex-dividend markers on the K-line view.
- Public README, MIT LICENSE, security/privacy notes, disclaimer, and release checklist.

Near-term direction:

- AI-assisted broker PDF/image import.
- Import staging before final ledger writes.
- Market data bootstrap flow for new users.
- Clearer app-style entry points for demo and private local use.

Long-term direction:

- Desktop/app shell for a more natural local-first experience.
- Plugin system for external open-source analysis tools.
- Read-only plugin permissions by default, with explicit review before ledger writes.

This draft is intentionally conservative. The app should help users understand and organize their own records without silently changing confirmed ledgers or implying trading advice.
