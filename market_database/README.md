# Market Database

Purpose:

- Future home for market/research data layer concepts.
- Boundary for market data, ETF research data, provider contracts, schemas, and synthetic fixtures.

What belongs here:

- Market data schema and storage concepts.
- ETF holdings snapshot concepts.
- Market snapshots, source adapters, provider contracts, and source-quality notes.
- Synthetic fixtures or examples when explicitly safe to commit.

What must not belong here:

- Personal account journals.
- User trades, lots, cost basis, private profiles, or real portfolio data.
- Broker documents, credentials, provider secrets, local config, raw provider responses, logs, backups, or cache files.
- Any final ledger write flow.

Current status:

- Placeholder/future home only.
- No market database source code or runtime data has been moved yet.
- Existing market data logic and files remain in the current source/runtime layout until a future planned migration.
- `market_database/` is for market/research data concepts only.
- Provider cache is not a source of truth.
- Confirmed ETF holdings snapshots are research data, not personal ledger data.

What currently lives elsewhere:

- Current market data code remains in the existing `src/` layout.
- Current provider docs remain under `docs/providers/` and `docs/MARKET_DATA_PROVIDERS.md`.
- Current runtime market databases remain in ignored local runtime folders.

Current related docs:

- [Providers And Data Sources](../docs/providers/README.md)
- [Market Data Providers](../docs/MARKET_DATA_PROVIDERS.md)
- [Data Model](../docs/DATA_MODEL.md)
- [Storage Boundaries](../docs/core/STORAGE_BOUNDARIES.md)

What may move here later:

- Market/research data schemas, provider contracts, source adapter docs, and synthetic fixtures after planned separation tasks.
- Market data source-quality notes and ETF holdings research-data docs.

Source/runtime movement is deferred.
