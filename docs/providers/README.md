# Providers And Data Sources

Providers are optional data-source adapters. They translate local files, issuer pages, or configured HTTP sources into normalized market/research data.

Provider rules:

- Provider fetch is manual-trigger unless a future task explicitly changes it.
- ETF holdings providers must preview and validate before confirmation.
- Accepted ETF holdings snapshots are written only through the existing storage helper.
- No scheduler or page-open fetch should be added without an explicit future task.
- No provider secrets, API keys, tokens, cookies, private URLs, headers, cache files, or raw responses belong in the repository.
- CSV import remains the fallback when provider config is missing, a ticker is unsupported, or source quality is unclear.
- Third-party sources are research inputs, not redistributed data.
- Providers must not create transactions, lots, account holdings, or final ledger records.

Current related document:

- [Market Data Providers](../MARKET_DATA_PROVIDERS.md)

Future source-code separation may introduce provider modules under a shared/core boundary, but no runtime source files are moved yet.
