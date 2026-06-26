# Developer Log

This log records public-facing development notes for `stock_daily_helper`.

The project exists because personal investing records deserve a local, reviewable journal instead of a pile of broker PDFs, screenshots, spreadsheets, and disconnected notes. The goal is a local-first stock journal and personal investment research dashboard: records first, analysis second.

This project has no trading permissions, does not connect to broker trading APIs, and is not investment advice. It is an early draft under active development and is not production-ready.

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
