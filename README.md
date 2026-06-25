# stock_daily_helper

A local-first stock accounting and decision-support dashboard for personal or family use.

The project tracks manually entered stock transactions, portfolio cost, realized profit, dividend income, and market data. It does **not** connect to brokerage trading APIs and does **not** place orders.

## Features

- Multi-profile portfolio dashboard.
- Manual buy/sell transaction tracking.
- FIFO-based cost and realized profit calculation.
- Manual dividend income records.
- Central instrument master for stocks and ETFs.
- Local market data storage with health summaries.
- Background market data refresh jobs.
- Upload library for broker PDFs or screenshots.
- Import staging workflow for future OCR/AI-assisted parsing.
- Local web UI designed for desktop and mobile browsers.

## Quick Start

Install dependencies:

```powershell
pip install -r requirements.txt
```

Start the local server:

```powershell
python src/main.py serve
```

Open:

```text
http://127.0.0.1:8787/
```

To expose the dashboard to trusted private devices, bind the server to a private network interface:

```powershell
python src/main.py serve --host <private-network-ip> --port 8787
```

Do not expose this application directly to the public internet.

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Data Model](docs/DATA_MODEL.md)
- [Import Pipeline](docs/IMPORT_PIPELINE.md)
- [Roadmap](docs/ROADMAP.md)
- [Security and Privacy](docs/SECURITY_AND_PRIVACY.md)
- [Disclaimer](docs/DISCLAIMER.md)

## Common Pages

Routes may vary by local configuration, but the main page groups are:

- Account dashboard: `/account/<profile>`
- Account stock detail: `/account/<profile>/stocks`
- Central database: `/database`
- Dividend database: `/database/dividends`
- Operation logs: `/database/logs`
- Upload library: `/database/uploads`

## Common Commands

Server:

```powershell
python src/main.py serve
```

Market database:

```powershell
python src/main.py migrate-market-db
python src/main.py rebuild-health-summary
python src/main.py check-market-db
python src/main.py sync-official-daily
python src/main.py cleanup-market-data
```

Gmail or email attachment import, when configured:

```powershell
python src/main.py gmail-check --limit 10
python src/main.py gmail-download --profile <profile>
python src/main.py gmail-download --profile <profile> --all-missing
```

Some command names may differ as the project evolves. Inspect `src/main.py` for the current CLI.

## Privacy Boundary

This repository should not include:

- OAuth credentials or tokens.
- Broker statements.
- Screenshots of private account data.
- Local database files containing real holdings.
- Real private network IP addresses.
- Personal account names or broker account identifiers.

See [Security and Privacy](docs/SECURITY_AND_PRIVACY.md).

## Financial Disclaimer

This tool is for personal record keeping and decision support only. It is not financial advice and not an automated trading system. See [Disclaimer](docs/DISCLAIMER.md).

