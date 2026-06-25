# Security and Privacy

This repository is intended to contain source code, documentation, tests, and synthetic examples for a local stock journal framework. Real operating data belongs outside version control.

## Never Commit

Do not commit:

- OAuth credentials, API keys, access tokens, refresh tokens, passwords, or private keys.
- `.env` files or local configuration files containing secrets.
- Broker statements, trade confirmations, screenshots, PDFs, spreadsheets, or email attachments.
- Local SQLite databases, quote caches, generated market data, upload libraries, or runtime profile files.
- Personal holdings, transaction ledgers, watchlists, dividend income records, or account notes.
- Broker account identifiers, order numbers, real private network addresses, personal names, or family profile names.
- Logs, generated reports, backups, downloaded binaries, or temporary files.

Use synthetic sample data only. Fake names, fake tickers, fake orders, and fake account values are acceptable when examples are needed.

## Local Runtime Data

Runtime directories such as `data/`, `profiles/`, `uploads/`, `output/`, and `backups/` are private by default. Keep them ignored unless a file is explicitly designed as a safe example.

If a local file is useful for documentation or tests, sanitize it first and place it under a clearly named sample or fixture path.

## Network Exposure

Recommended:

- Run on `127.0.0.1` by default.
- Use trusted private networks or VPNs only when accessing from another device.
- Treat query-string share tokens as a local convenience, not public internet security.

Avoid:

- Public internet exposure.
- Router port forwarding.
- Hosting real account data on an untrusted server.

## Email and Documents

Email integrations should use read-only scopes where possible. They must not send, delete, forward, or mutate mail automatically.

Downloaded documents must stay local, be deduplicated by stable metadata and file hash, and enter an import review workflow before any data is written to a final ledger.

## AI and Parsing

AI-assisted parsing is optional and must be treated as sensitive processing:

- Send only the minimum required document or extracted text.
- Cache by file hash to avoid repeated uploads.
- Log parse status without storing full private document text.
- Require user review before writing parsed rows to confirmed transactions.

## Logs and Backups

Logs should help diagnose local issues without exposing private data. Avoid logging full document text, tokens, passwords, account identifiers, or complete broker order details.

Before schema migrations, back up private runtime data locally. Do not commit those backups.
