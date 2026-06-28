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
