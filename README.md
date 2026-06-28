# Local Stock Journal

A local-first stock journal and personal investment research dashboard.

`stock_daily_helper` is a local-first stock journal and personal investment research dashboard.

The project is built around user-owned records: transactions, lots, cost basis, dividends, notes, documents, and local market data history. Analysis views such as dashboards, K-line charts, indicators, and assistant/parser workflows are secondary tools for reviewing those records.

This project is **not investment advice**. It cannot place trades, does not connect to broker trading APIs, and is not an automated trading system.

## What It Does

- Tracks manually entered buy/sell transactions.
- Rebuilds holdings, FIFO lots, cost basis, realized profit, and unrealized profit/loss.
- Records manual dividend income separately from market dividend calendar data.
- Maintains a local central instrument and market-data database.
- Shows account dashboards and single-instrument detail pages.
- Supports local K-line/OHLCV review from cached data.
- Provides upload and import-staging surfaces for broker documents.
- Includes provider framework foundations and synthetic sample market data.

## Safety Boundaries

- No brokerage order placement.
- No default connection to broker trading APIs.
- No financial, investment, tax, or legal advice.
- No public internet exposure recommended.
- No real credentials, broker PDFs, screenshots, ledgers, SQLite databases, logs, or backups should be committed.

See [Security and Privacy](docs/SECURITY_AND_PRIVACY.md) and [Disclaimer](docs/DISCLAIMER.md).

For development notes and project direction, see [Developer Log](DEVLOG.md), [Documentation Index](docs/README.md), [Framework Direction](docs/FRAMEWORK_DIRECTION.md), and [Development Tracks](docs/DEVELOPMENT_TRACKS.md).

For Codex task routing, read `AGENTS.md` first if present, then [Codex Context Routing](docs/CODEX_CONTEXT.md), then only the targeted docs needed for the task.

## Local Data Ownership

Runtime data is intended to stay on the user's machine. Local directories such as `data/`, `profiles/`, `uploads/`, `output/`, and `backups/` are ignored by Git because they may contain private holdings, documents, market caches, and logs.

The public repository should contain source code, tests, docs, and synthetic examples only.

## Project Structure Direction

The project is moving toward three top-level areas. These folders are placeholders for future separation; no runtime source code has been moved yet.

- [web_stock_machine/](web_stock_machine/) - future home for the web prototype / Flask stock machine.
- [desktop_stock_machine/](desktop_stock_machine/) - future home for the desktop stock machine product.
- [market_database/](market_database/) - future home for market/research data layer concepts.

The current root runtime remains the legacy web prototype/reference. `main` has the `web-prototype-demo-v1` tag as a reference snapshot, and `desktop-rebuild` is the branch for desktop rebuild work.

The web prototype remains the feature lab. The desktop product will rebuild its shell, navigation, layout, and UI from scratch under `desktop_stock_machine/`. Market/research data belongs in a separate boundary from personal account journals and private profile data.

Runtime/source movement is deferred. Future tasks should use [Codex Context Routing](docs/CODEX_CONTEXT.md) for targeted document reading before moving docs or source code.

## Fresh-User Setup

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

Run tests:

```powershell
python -m unittest discover -s tests -v
```

Start the local server:

```powershell
python src/main.py serve
```

Open the local app:

```text
http://127.0.0.1:8787/
```

Do not expose the app directly to the public internet. If you bind to a LAN, VPN, or Tailscale address, treat it as a private local deployment and verify your firewall rules.

## Optional Providers And Credentials

Market data, Gmail, broker-document import, and AI/OCR workflows are optional integrations. Users are responsible for provider credentials, provider terms, rate limits, and data redistribution rights.

Credential files such as `config/gmail_credentials.json`, `config/gmail_token.json`, `.env`, and API keys must remain local and ignored. Tests and synthetic sample-data checks should not require live credentials or external API calls.

## Demo And Sample Data

Synthetic market CSV files are available under:

- `sample_data/market/quotes.csv`
- `sample_data/market/ohlcv_daily.csv`
- `sample_data/profiles/demo/state.json`

Generate or refresh them with:

```powershell
python scripts/create_demo_data.py
```

The generated data is deterministic and fully synthetic. It includes fake demo tickers, fake prices, fake transactions, and a fake dividend record. It is for testing and illustration only, not investment advice.

Prepare an isolated generated demo runtime directory with:

```powershell
python scripts/prepare_demo_runtime.py --reset
```

`sample_data/` is committed synthetic fixture data. `demo_runtime/` is generated from `sample_data/`, ignored by Git, and safe to delete/recreate when it contains the `.demo_runtime` sentinel. Real private runtime data belongs under `data/` and must never be committed.

Run the read-only synthetic demo server with:

```powershell
python src/main.py serve-demo --check
python src/main.py serve-demo
```

The demo server uses `demo_runtime/` only, serves the `demo` profile, disables background refresh jobs, and blocks write/import/refresh actions. It does not use real `data/`.

An optional desktop demo shell is available for local experiments. It is demo-only, requires optional desktop dependencies, and is not packaged as an `.exe` yet:

```powershell
pip install -r requirements-desktop.txt
python src/main.py desktop-demo
```

### Profile Defaults

Normal/private mode currently uses local runtime profiles such as `son` and `mom`. These are private local profiles created under `data/`; they are not demo data and should not be committed.

Public users should start with the synthetic demo flow first. Demo mode uses only the `demo` profile from `demo_runtime/`. Future work may make normal/private profiles fully configurable.

## What Currently Works

- Core local Flask app.
- Profile ledger loading and accounting calculations.
- Manual transaction and dividend record flows.
- Local market database and health summaries.
- Account overview dashboard.
- Single-instrument detail page with local K-line chart, MA overlays, cost line, buy markers, and ex-dividend markers.
- Provider foundation types, registry, yfinance quote adapter, and local CSV provider.
- Unit test suite for accounting and provider foundations.

## Experimental Or In Migration

- Provider framework is not fully wired into runtime dashboard flows.
- Demo/sample mode configuration exists as a foundation, but the complete demo app flow is still a TODO.
- Gmail broker-statement ingestion is local and optional, not a generic public default.
- OCR/AI parsing workflows should remain staged and user-reviewed before ledger writes.
- Plugin/tool assistant architecture is still evolving.

## Common Commands

Server:

```powershell
python src/main.py serve
```

Local development server safety:

- Run only one dashboard server per port.
- For phone testing on the same network, use:

```powershell
python src/main.py serve --host 0.0.0.0 --port 8787
```

- Do not run `127.0.0.1:8787` and `0.0.0.0:8787` servers at the same time.
- Use `GET /api/runtime-info` to confirm the active `project_root`, `data_root`/`runtime_root`, and mode.

Demo server:

```powershell
python scripts/create_demo_data.py
python scripts/prepare_demo_runtime.py --reset
python src/main.py serve-demo --check
python src/main.py serve-demo
```

Optional desktop demo shell:

```powershell
pip install -r requirements-desktop.txt
python src/main.py desktop-demo
```

Market database utilities:

```powershell
python src/main.py migrate-market-db
python src/main.py rebuild-health-summary
python src/main.py check-market-db
python src/main.py sync-official-daily
python src/main.py cleanup-market-data
```

Optional Gmail or email attachment import, after local credentials are configured:

```powershell
python src/main.py gmail-check --limit 10
python src/main.py gmail-download --profile <profile>
python src/main.py gmail-download --profile <profile> --all-missing
```

Some command names may change as the migration continues. Inspect `src/main.py` for the current CLI.

## Documentation

- [Product Vision](docs/PRODUCT_VISION.md)
- [Codex Context Routing](docs/CODEX_CONTEXT.md)
- [Documentation Index](docs/README.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Data Model](docs/DATA_MODEL.md)
- [Core Contracts](docs/core/README.md)
- [Web Prototype Track](docs/web_prototype/README.md)
- [Desktop Product Track](docs/desktop_product/README.md)
- [Providers and Data Sources](docs/providers/README.md)
- [Market Data Providers](docs/MARKET_DATA_PROVIDERS.md)
- [Import Pipeline](docs/IMPORT_PIPELINE.md)
- [Roadmap](docs/ROADMAP.md)
- [Security and Privacy](docs/SECURITY_AND_PRIVACY.md)
- [Disclaimer](docs/DISCLAIMER.md)
- [Public Release Checklist](docs/PUBLIC_RELEASE_CHECKLIST.md)

## License

MIT. See [LICENSE](LICENSE).
