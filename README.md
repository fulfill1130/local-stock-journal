# Desktop Stock Machine

A local-first desktop stock journal and ETF research workbench.

This repository is now centered on the new desktop product under
[`desktop_stock_machine/`](desktop_stock_machine/). The legacy web prototype is
kept as a reference track, not the main product UI.

The desktop product is designed for user-owned local records: account journals,
holdings review, ETF research, market-data context, import staging, backup
safety, and future external tool adapters.

This project is **not investment advice**. It cannot place trades, does not
connect to broker trading APIs, and is not an automated trading system.

## Current Desktop Status

- New standalone desktop skeleton lives in `desktop_stock_machine/`.
- Static desktop UI shell lives in `desktop_stock_machine/frontend/`.
- The UI shell is a clean rebuild and does not copy the legacy Flask web UI.
- Desktop data-root wiring is planned next.
- External adapter contracts are planned next.
- Real profile support, migration, provider fetches, plugin execution, and
  packaging are not implemented yet.

## Run The Desktop Skeleton

From the repository root:

```powershell
python desktop_stock_machine/run_dev.py
```

This prints desktop startup/status information. It does not start a server, open
a window, create `app_data/`, migrate data, call providers, or load private
configuration.

## Run Desktop Tests

```powershell
python -m unittest discover -s desktop_stock_machine/tests -v
```

## View The Static UI Shell

Open this file in a browser:

```text
desktop_stock_machine/frontend/index.html
```

On Windows, you can also double-click:

```text
desktop_stock_machine/open_ui.cmd
```

The UI is static HTML/CSS/JavaScript. It has no npm, no bundler, no external CDN,
no backend calls, and no file writes.

## Build The Desktop EXE

```powershell
python -m pip install -r requirements-desktop.txt
powershell -ExecutionPolicy Bypass -File desktop_stock_machine/build_exe.ps1
```

The executable is created at:

```text
output/desktop_exe/dist/DesktopStockMachine.exe
```

The `.exe` packages the UI shell only. User data, databases, provider cache,
logs, backups, local config, and future `app_data/` contents stay outside the
executable.

## Track Layout

- [`desktop_stock_machine/`](desktop_stock_machine/) - main desktop product
  direction.
- [`web_stock_machine/`](web_stock_machine/) - legacy web prototype reference
  track.
- [`market_database/`](market_database/) - future market/research data concepts.

The web prototype snapshot is preserved by the `web-prototype-demo-v1` tag. A
`web-prototype-demo` branch points to that same reference snapshot so the old
web draft remains easy to find without being the project homepage.

## Safety Boundaries

- No brokerage order placement.
- No broker trading API integration.
- No financial, investment, tax, or legal advice.
- No public internet exposure recommended.
- No real credentials, broker PDFs, screenshots, ledgers, SQLite databases,
  logs, or backups should be committed.
- Desktop real-data migration must require dry-run, backup, confirmation, and
  verification.
- `market_database/` is for market/research data concepts, not personal trades,
  cost basis, private profiles, or portfolio storage.

Runtime data is intended to stay on the user's machine. Local directories such
as `data/`, `demo_runtime/`, `app_data/`, `profiles/`, `uploads/`, `output/`,
and `backups/` are ignored because they may contain private holdings, documents,
market caches, screenshots, and logs.

## Legacy Web Prototype

The root `src/` runtime remains the legacy Flask web prototype/reference. It is
not the final desktop architecture and should not be copied into
`desktop_stock_machine/` by default.

For reference-only web prototype commands, use the `web-prototype-demo` branch
or the `web-prototype-demo-v1` tag.

## Documentation

- [Codex Context Routing](docs/CODEX_CONTEXT.md)
- [Desktop Product Track](docs/desktop_product/README.md)
- [Desktop Data Root](docs/desktop_product/DATA_ROOT.md)
- [Desktop Backup And Migration](docs/desktop_product/BACKUP_MIGRATION.md)
- [Storage Boundaries](docs/core/STORAGE_BOUNDARIES.md)
- [Legacy Web Prototype](web_stock_machine/LEGACY_WEB_PROTOTYPE.md)
- [Security and Privacy](docs/SECURITY_AND_PRIVACY.md)
- [Disclaimer](docs/DISCLAIMER.md)

## License

MIT. See [LICENSE](LICENSE).
